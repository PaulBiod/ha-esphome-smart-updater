from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_CPU_SENSOR,
    CONF_DELAY_MAX,
    CONF_DELAY_MIN,
    CONF_LOAD_SENSOR,
    CONF_MAX_ITEMS,
    CONF_TEMP_SENSOR,
    CONF_THROTTLE,
    CONF_TIMEOUT,
    DEFAULT_DELAY_MAX,
    DEFAULT_DELAY_MIN,
    DEFAULT_MAX_ITEMS,
    DEFAULT_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


class CampaignManager:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry

        self._listeners: list[Callable[[], None]] = []
        self._task: asyncio.Task | None = None
        self._shutdown = False

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

    async def async_shutdown(self) -> None:
        self._shutdown = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def add_listener(self, callback: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(callback)

        def remove() -> None:
            if callback in self._listeners:
                self._listeners.remove(callback)

        return remove

    def _push(self) -> None:
        for callback in list(self._listeners):
            callback()

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

        return result

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
        if self.state in ("running", "paused"):
            return

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

        self.state = "running"
        self._push()

        self._task = self.hass.async_create_task(self._run())

    async def async_pause(self) -> None:
        if self.state == "running":
            self.pause_requested = True
            self._push()

    async def async_resume(self) -> None:
        if self.state != "paused":
            return

        self.pause_requested = False
        self.stop_requested = False
        self.state = "running"
        self._push()

        self._task = self.hass.async_create_task(self._run())

    async def async_stop(self) -> None:
        if self.state in ("running", "paused"):
            self.stop_requested = True
            if self.state == "paused":
                await self._finish_and_reset(stopped=True)
            else:
                self._push()

    async def _run(self) -> None:
        timeout_s = int(self._get_option(CONF_TIMEOUT, DEFAULT_TIMEOUT))

        while self.remaining and not self._shutdown:
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
                    await self._delay_between_items()
                continue

            start_wait = time.time()
            success = False

            while not self._shutdown:
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
                await self._delay_between_items()

        if not self._shutdown:
            await self._finish_and_reset(stopped=False)

    async def _delay_between_items(self) -> None:
        self.delay_s = self._compute_delay()
        self._push()
        await asyncio.sleep(self.delay_s)

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

        self._push()

    def campaign_attributes(self) -> dict:
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
        }
