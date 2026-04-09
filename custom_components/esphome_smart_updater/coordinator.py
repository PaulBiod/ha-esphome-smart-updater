from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .const import (
    CONF_CPU_SENSOR,
    CONF_DELAY_MAX,
    CONF_DELAY_MIN,
    CONF_LOAD_SENSOR,
    CONF_MAX_ITEMS,
    CONF_RESTORE_RESUME_DELAY,
    CONF_TEMP_SENSOR,
    CONF_THROTTLE,
    CONF_TIMEOUT,
    DEFAULT_DELAY_MAX,
    DEFAULT_DELAY_MIN,
    DEFAULT_MAX_ITEMS,
    DEFAULT_RESTORE_RESUME_DELAY,
    DEFAULT_TIMEOUT,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


class CampaignManager:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry

        self._listeners: list[Callable[[], None]] = []
        self._task: asyncio.Task | None = None
        self._save_task: asyncio.Task | None = None
        self._restore_resume_task: asyncio.Task | None = None
        self._pending_refresh_task: asyncio.Task | None = None
        self._shutdown = False
        self._run_id = 0

        self._store = Store[dict[str, Any]](
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY}_{entry.entry_id}",
        )

        self.state = "idle"
        self.queue: list[str] = []
        self.remaining: list[str] = []
        self.done: list[str] = []
        self.failed: list[str] = []
        self.skipped: list[str] = []

        self.current = ""
        self.current_update_entity = ""

        self.total = 0
        self.index = 0
        self.start_ts = 0
        self.end_ts = 0
        self.duration_s = 0
        self.avg_duration_s = 0
        self.eta_s = 0
        self.delay_s = int(self._get_option(CONF_DELAY_MIN, DEFAULT_DELAY_MIN))

        self.pause_requested = False
        self.stop_requested = False
        self.last_error = ""

        self.cpu = None
        self.temp = None
        self.load_1m = None

        self.restored_after_restart = False
        self.resume_at_ts = 0
        self._waiting_ha_started = False

    async def async_initialize(self) -> None:
        await self._async_restore_state()
        self._start_pending_refresh_loop()

    async def async_shutdown(self) -> None:
        self._shutdown = True
        await self._cancel_restore_resume_task()
        await self._cancel_run_task()
        await self._cancel_pending_refresh_task()

        if self._save_task and not self._save_task.done():
            try:
                await self._save_task
            except asyncio.CancelledError:
                pass

        await self._async_save_state()

    async def _cancel_run_task(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _cancel_restore_resume_task(self) -> None:
        if self._restore_resume_task and not self._restore_resume_task.done():
            self._restore_resume_task.cancel()
            try:
                await self._restore_resume_task
            except asyncio.CancelledError:
                pass
        self._restore_resume_task = None

    async def _cancel_pending_refresh_task(self) -> None:
        if self._pending_refresh_task and not self._pending_refresh_task.done():
            self._pending_refresh_task.cancel()
            try:
                await self._pending_refresh_task
            except asyncio.CancelledError:
                pass
        self._pending_refresh_task = None

    def _start_pending_refresh_loop(self) -> None:
        if self._pending_refresh_task and not self._pending_refresh_task.done():
            return
        self._pending_refresh_task = self.hass.async_create_task(self._pending_refresh_loop())

    async def _pending_refresh_loop(self) -> None:
        try:
            while not self._shutdown:
                self._push()
                await asyncio.sleep(15)
        except asyncio.CancelledError:
            raise

    def _run_active(self) -> bool:
        return self._task is not None and not self._task.done()

    def _schedule_run(self) -> None:
        if self._shutdown or self._run_active():
            return
        self._run_id += 1
        run_id = self._run_id
        self._task = self.hass.async_create_task(self._run(run_id))

    def add_listener(self, callback: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(callback)

        def remove() -> None:
            if callback in self._listeners:
                self._listeners.remove(callback)

        return remove

    def _push(self) -> None:
        for callback in list(self._listeners):
            callback()
        self._schedule_save()

    def _schedule_save(self) -> None:
        if self._shutdown:
            return
        if self._save_task and not self._save_task.done():
            return
        self._save_task = self.hass.async_create_task(self._async_save_state())

    async def _async_save_state(self) -> None:
        try:
            await self._store.async_save(self._snapshot())
        except Exception:
            _LOGGER.exception("Failed to save ESU state")

    async def _async_restore_state(self) -> None:
        try:
            data = await self._store.async_load()
        except Exception:
            _LOGGER.exception("Failed to restore ESU state")
            return

        if not data:
            return

        self._apply_snapshot(data)

        if self.state in ("running", "paused"):
            current = self.current_update_entity or self.current
            if current and current not in self.remaining and current not in self.done and current not in self.failed:
                self.remaining.insert(0, current)

            self.current = ""
            self.current_update_entity = ""
            self.pause_requested = False
            self.stop_requested = False
            self.state = "paused"
            self.last_error = "restored_after_restart"
            self.restored_after_restart = True
            self.resume_at_ts = int(time.time()) + int(
                self._get_option(CONF_RESTORE_RESUME_DELAY, DEFAULT_RESTORE_RESUME_DELAY)
            )

            self._push()
            self._schedule_restore_resume_after_ha_started()
            return

        self._update_metrics()
        self._push()

    def _schedule_restore_resume_after_ha_started(self) -> None:
        if self.hass.is_running:
            self._restore_resume_task = self.hass.async_create_task(self._async_delayed_restore_resume())
            return

        self._waiting_ha_started = True

        async def _on_started(_: Event) -> None:
            self._waiting_ha_started = False
            self._restore_resume_task = self.hass.async_create_task(self._async_delayed_restore_resume())

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _on_started)

    async def _async_delayed_restore_resume(self) -> None:
        try:
            while not self._shutdown:
                remaining = self.resume_at_ts - int(time.time())
                if remaining <= 0:
                    break
                self._push()
                await asyncio.sleep(min(5, remaining))

            if self._shutdown:
                return

            if (
                self.state == "paused"
                and self.restored_after_restart
                and self.remaining
                and not self.stop_requested
                and not self._run_active()
            ):
                await self.async_resume(from_restore=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Failed delayed restore resume")
        finally:
            self._restore_resume_task = None

    def _snapshot(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "queue": list(self.queue),
            "remaining": list(self.remaining),
            "done": list(self.done),
            "failed": list(self.failed),
            "skipped": list(self.skipped),
            "current": self.current,
            "current_update_entity": self.current_update_entity,
            "total": self.total,
            "index": self.index,
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "duration_s": self.duration_s,
            "avg_duration_s": self.avg_duration_s,
            "eta_s": self.eta_s,
            "delay_s": self.delay_s,
            "pause_requested": self.pause_requested,
            "stop_requested": self.stop_requested,
            "last_error": self.last_error,
            "cpu": self.cpu,
            "temp": self.temp,
            "load_1m": self.load_1m,
            "restored_after_restart": self.restored_after_restart,
            "resume_at_ts": self.resume_at_ts,
        }

    def _apply_snapshot(self, data: dict[str, Any]) -> None:
        self.state = str(data.get("state", "idle"))
        self.queue = list(data.get("queue", []))
        self.remaining = list(data.get("remaining", []))
        self.done = list(data.get("done", []))
        self.failed = list(data.get("failed", []))
        self.skipped = list(data.get("skipped", []))

        self.current = str(data.get("current", ""))
        self.current_update_entity = str(data.get("current_update_entity", ""))

        self.total = int(data.get("total", 0) or 0)
        self.index = int(data.get("index", 0) or 0)
        self.start_ts = int(data.get("start_ts", 0) or 0)
        self.end_ts = int(data.get("end_ts", 0) or 0)
        self.duration_s = int(data.get("duration_s", 0) or 0)

        avg_duration_s = data.get("avg_duration_s", 0)
        try:
            self.avg_duration_s = float(avg_duration_s or 0)
        except (TypeError, ValueError):
            self.avg_duration_s = 0

        self.eta_s = int(data.get("eta_s", 0) or 0)
        self.delay_s = int(data.get("delay_s", self._get_option(CONF_DELAY_MIN, DEFAULT_DELAY_MIN)) or 0)

        self.pause_requested = bool(data.get("pause_requested", False))
        self.stop_requested = bool(data.get("stop_requested", False))
        self.last_error = str(data.get("last_error", ""))

        self.cpu = data.get("cpu")
        self.temp = data.get("temp")
        self.load_1m = data.get("load_1m")

        self.restored_after_restart = bool(data.get("restored_after_restart", False))
        self.resume_at_ts = int(data.get("resume_at_ts", 0) or 0)

    def _get_option(self, key: str, default):
        return self.entry.options.get(key, default)

    def _get_float_state(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        st = self.hass.states.get(entity_id)
        if st is None:
            return None
        try:
            return float(st.state)
        except (TypeError, ValueError):
            return None

    def _find_esphome_updates(self) -> list[str]:
        ent_reg = er.async_get(self.hass)
        result: list[str] = []

        for entity_id in self.hass.states.async_entity_ids("update"):
            st = self.hass.states.get(entity_id)
            reg_entry = ent_reg.async_get(entity_id)

            if st is None or reg_entry is None:
                continue
            if st.state != "on":
                continue
            if reg_entry.platform != "esphome":
                continue

            result.append(entity_id)

        result.sort()
        return result

    @property
    def pending_updates_count(self) -> int:
        return len(self.pending_updates_entities())

    def pending_updates_entities(self) -> list[str]:
        return self._find_esphome_updates()

    def _compute_delay(self) -> int:
        delay_min = int(self._get_option(CONF_DELAY_MIN, DEFAULT_DELAY_MIN))
        delay_max = int(self._get_option(CONF_DELAY_MAX, DEFAULT_DELAY_MAX))
        throttle = bool(self._get_option(CONF_THROTTLE, False))

        if not throttle:
            self.cpu = None
            self.temp = None
            self.load_1m = None
            return delay_min

        cpu = self._get_float_state(self._get_option(CONF_CPU_SENSOR, ""))
        temp = self._get_float_state(self._get_option(CONF_TEMP_SENSOR, ""))
        load = self._get_float_state(self._get_option(CONF_LOAD_SENSOR, ""))

        self.cpu = cpu
        self.temp = temp
        self.load_1m = load

        if cpu is None and temp is None and load is None:
            return delay_min

        stress_cpu = (cpu / 100.0) if cpu is not None else 0.0
        stress_load = (load / 4.0) if load is not None else 0.0
        stress_temp = (((temp - 50.0) / 25.0) if temp is not None and temp > 50 else 0.0)

        stress = max(stress_cpu, stress_load, stress_temp)
        stress = max(0.0, min(1.0, stress))

        target_delay = int(delay_min + stress * (delay_max - delay_min))
        prev_delay = self.delay_s or delay_min

        if target_delay > prev_delay:
            return min(delay_max, target_delay)

        smooth = int(prev_delay * 0.7 + target_delay * 0.3)
        return max(delay_min, min(delay_max, smooth))

    async def async_start(self) -> None:
        if self.state in ("running", "paused") or self._run_active():
            return

        await self._cancel_restore_resume_task()

        updates = self._find_esphome_updates()
        max_items = int(self._get_option(CONF_MAX_ITEMS, DEFAULT_MAX_ITEMS))

        if max_items > 0:
            updates = updates[:max_items]

        if not updates:
            self.last_error = "no_updates_detected"
            self.state = "idle"
            self._push()
            return

        self.queue = list(updates)
        self.remaining = list(updates)
        self.done = []
        self.failed = []
        self.skipped = []

        self.current = ""
        self.current_update_entity = ""
        self.total = len(updates)
        self.index = 0
        self.start_ts = int(time.time())
        self.end_ts = 0
        self.duration_s = 0
        self.avg_duration_s = 0
        self.eta_s = 0
        self.delay_s = int(self._get_option(CONF_DELAY_MIN, DEFAULT_DELAY_MIN))

        self.pause_requested = False
        self.stop_requested = False
        self.last_error = ""
        self.restored_after_restart = False
        self.resume_at_ts = 0

        self.state = "running"
        self._push()
        self._schedule_run()

    async def async_pause(self) -> None:
        if self.state == "running":
            await self._cancel_restore_resume_task()
            self.pause_requested = True
            self.restored_after_restart = False
            self.resume_at_ts = 0
            self._push()

    async def async_resume(self, from_restore: bool = False) -> None:
        if self.state != "paused" or self._run_active():
            return

        await self._cancel_restore_resume_task()

        self.pause_requested = False
        self.stop_requested = False
        self.state = "running"
        self.restored_after_restart = from_restore
        self.resume_at_ts = 0
        self._push()
        self._schedule_run()

    async def async_stop(self) -> None:
        if self.state in ("running", "paused"):
            await self._cancel_restore_resume_task()
            self.stop_requested = True
            self.restored_after_restart = False
            self.resume_at_ts = 0
            if self.state == "paused":
                await self._finish_and_reset(stopped=True)
            else:
                self._push()

    async def _run(self, run_id: int) -> None:
        timeout_s = int(self._get_option(CONF_TIMEOUT, DEFAULT_TIMEOUT))

        try:
            while self.remaining and not self._shutdown:
                if run_id != self._run_id:
                    return

                current = self.remaining[0]
                self.current = current
                self.current_update_entity = current
                self.index += 1
                self._push()

                try:
                    await self.hass.services.async_call(
                        "update",
                        "install",
                        {"entity_id": current},
                        blocking=True,
                    )
                except Exception as exc:
                    _LOGGER.exception("ESU install call failed for %s", current)
                    self.failed.append(current)
                    self.last_error = f"install_call_failed: {exc.__class__.__name__}"
                    self.remaining = self.remaining[1:]
                    self.current = ""
                    self.current_update_entity = ""
                    self._update_metrics()
                    self._push()

                    if await self._handle_pause_stop():
                        return

                    if self.remaining:
                        await self._delay_between_items(run_id)
                    continue

                start_wait = time.time()
                success = False

                while not self._shutdown:
                    if run_id != self._run_id:
                        return

                    st = self.hass.states.get(current)

                    if st is not None and st.state == "off":
                        success = True
                        break

                    if time.time() - start_wait > timeout_s:
                        break

                    await asyncio.sleep(5)

                if success:
                    self.done.append(current)
                    self.last_error = ""
                else:
                    self.failed.append(current)
                    self.last_error = "timeout_or_still_on"

                self.remaining = self.remaining[1:]
                self.current = ""
                self.current_update_entity = ""
                self._update_metrics()
                self._push()

                if await self._handle_pause_stop():
                    return

                if self.remaining:
                    await self._delay_between_items(run_id)

            if not self._shutdown and run_id == self._run_id:
                await self._finish_and_reset(stopped=False)
        finally:
            if self._task and asyncio.current_task() is self._task:
                self._task = None

    async def _delay_between_items(self, run_id: int) -> None:
        self.delay_s = self._compute_delay()
        self._push()

        remaining = self.delay_s
        while remaining > 0 and not self._shutdown:
            if run_id != self._run_id:
                return
            await asyncio.sleep(min(1, remaining))
            remaining -= 1

    async def _handle_pause_stop(self) -> bool:
        if self.stop_requested:
            await self._finish_and_reset(stopped=True)
            return True

        if self.pause_requested:
            self.state = "paused"
            self._push()
            return True

        return False

    def _update_metrics(self) -> None:
        if not self.start_ts:
            return

        self.duration_s = int(time.time()) - self.start_ts
        processed = len(self.done) + len(self.failed) + len(self.skipped)

        if processed > 0:
            self.avg_duration_s = round(self.duration_s / processed, 1)
            self.eta_s = int(len(self.remaining) * self.avg_duration_s)
        else:
            self.avg_duration_s = 0
            self.eta_s = 0

    async def _finish_and_reset(self, stopped: bool) -> None:
        self.end_ts = int(time.time())
        self.duration_s = (self.end_ts - self.start_ts) if self.start_ts else 0

        title = "ESPHome OTA"
        ok = len(self.done)
        ko = len(self.failed)
        sk = len(self.skipped)

        status = "⏹ Campagne arrêtée" if stopped else (
            "❌ Campagne terminée avec erreurs" if ko > 0 else "✅ Campagne terminée avec succès"
        )

        failed_names = []
        for entity_id in self.failed:
            st = self.hass.states.get(entity_id)
            failed_names.append(st.name if st else entity_id)

        message_lines = [
            status,
            "",
            f"Durée totale : {self.duration_s}s",
            f"Réussis : {ok}",
            f"Échecs : {ko}",
            f"Skipped : {sk}",
        ]

        if failed_names:
            message_lines.extend(["", "Appareils en échec :"])
            message_lines.extend([f"- {name}" for name in failed_names])

        if self.last_error:
            message_lines.extend(["", f"Dernière erreur : {self.last_error}"])

        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": title,
                "message": "\n".join(message_lines),
            },
            blocking=True,
        )

        self.state = "idle"
        self.queue = []
        self.remaining = []
        self.done = []
        self.failed = []
        self.skipped = []
        self.current = ""
        self.current_update_entity = ""
        self.total = 0
        self.index = 0
        self.start_ts = 0
        self.end_ts = 0
        self.duration_s = 0
        self.avg_duration_s = 0
        self.eta_s = 0
        self.delay_s = 0
        self.pause_requested = False
        self.stop_requested = False
        self.last_error = ""
        self.cpu = None
        self.temp = None
        self.load_1m = None
        self.restored_after_restart = False
        self.resume_at_ts = 0
        self._waiting_ha_started = False

        self._push()

    def campaign_attributes(self) -> dict[str, Any]:
        return {
            "queue": list(self.queue),
            "remaining": list(self.remaining),
            "done": list(self.done),
            "failed": list(self.failed),
            "skipped": list(self.skipped),
            "current": self.current,
            "current_update_entity": self.current_update_entity,
            "total": self.total,
            "index": self.index,
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "duration_s": self.duration_s,
            "avg_duration_s": self.avg_duration_s,
            "eta_s": self.eta_s,
            "delay_s": self.delay_s,
            "pause_requested": self.pause_requested,
            "stop_requested": self.stop_requested,
            "last_error": self.last_error,
            "cpu": self.cpu,
            "temp": self.temp,
            "load_1m": self.load_1m,
            "restored_after_restart": self.restored_after_restart,
            "resume_at_ts": self.resume_at_ts,
            "run_active": self._run_active(),
            "waiting_ha_started": self._waiting_ha_started,
        }
