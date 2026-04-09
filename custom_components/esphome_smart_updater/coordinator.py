from __future__ import annotations

import asyncio
from collections.abc import Callable
from copy import deepcopy
from datetime import timedelta
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant, callback
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
    CONF_TIMEOUT,
    DEFAULT_DELAY_MAX,
    DEFAULT_DELAY_MIN,
    DEFAULT_MAX_ITEMS,
    DEFAULT_REFRESH_INTERVAL,
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
        self.store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}")

        self._listeners: list[Callable[[], None]] = []
        self._refresh_task: asyncio.Task | None = None
        self._worker_task: asyncio.Task | None = None
        self._resume_task: asyncio.Task | None = None
        self._started_unsub = None
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
        self.delay_s = 0

        self.cpu = None
        self.temp = None
        self.load_1m = None

        self.pause_requested = False
        self.stop_requested = False
        self.waiting_ha_started = False
        self.resume_at_ts = 0
        self.last_error = ""

        self.pending_updates_count = 0
        self._pending_update_entities: list[str] = []

    async def async_initialize(self) -> None:
        await self._async_refresh_pending_updates()
        await self._async_restore()

        self._refresh_task = self.hass.loop.create_task(self._pending_refresh_loop())

        if self.hass.is_running:
            await self._async_handle_post_startup_restore()
        else:
            self._started_unsub = self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED, self._async_on_hass_started
            )

    async def async_shutdown(self) -> None:
        self._shutdown = True

        if self._started_unsub:
            self._started_unsub()
            self._started_unsub = None

        for task in (self._resume_task, self._worker_task, self._refresh_task):
            if task is not None:
                task.cancel()

        for task in (self._resume_task, self._worker_task, self._refresh_task):
            if task is not None:
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    @callback
    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        def _remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    def pending_updates_entities(self) -> list[str]:
        return list(self._pending_update_entities)

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
            "start_ts": self.start_ts or "",
            "end_ts": self.end_ts or "",
            "duration_s": self.duration_s,
            "avg_duration_s": self.avg_duration_s,
            "eta_s": self.eta_s,
            "delay_s": self.delay_s,
            "cpu": self.cpu,
            "temp": self.temp,
            "load_1m": self.load_1m,
            "pause_requested": self.pause_requested,
            "stop_requested": self.stop_requested,
            "waiting_ha_started": self.waiting_ha_started,
            "resume_at_ts": self.resume_at_ts,
            "last_error": self.last_error,
        }

    async def async_start(self) -> None:
    await self._async_refresh_pending_updates()

    max_items = int(self.entry.options.get(CONF_MAX_ITEMS, DEFAULT_MAX_ITEMS) or DEFAULT_MAX_ITEMS)
    updates = self._pending_update_entities[:max_items]

    if not updates:
        self._reset_runtime_state()
        self.last_error = "no_updates_detected"
        await self._async_save()
        self._notify()
        return

        self.state = "running"
        self.queue = list(updates)
        self.remaining = list(updates)
        self.done = []
        self.failed = []
        self.skipped = []
        self.current = ""
        self.current_update_entity = ""
        self.total = len(updates)
        self.index = 1 if updates else 0
        self.start_ts = int(time.time())
        self.end_ts = 0
        self.duration_s = 0
        self.avg_duration_s = 0
        self.eta_s = 0
        self.delay_s = self.entry.options.get(CONF_DELAY_MIN, DEFAULT_DELAY_MIN)
        self.pause_requested = False
        self.stop_requested = False
        self.waiting_ha_started = False
        self.resume_at_ts = 0
        self.last_error = ""

        await self._async_save()
        self._notify()
        self._ensure_worker()

    async def async_pause(self) -> None:
        if self.state != "running":
            return
        self.pause_requested = True
        await self._async_save()
        self._notify()

    async def async_resume(self, manual: bool = False) -> None:
        if self.state != "paused":
            return

        self.pause_requested = False
        self.stop_requested = False
        self.waiting_ha_started = False
        self.resume_at_ts = 0
        self.last_error = ""

        await self._async_refresh_pending_updates()
        await self._async_reconcile_remaining_with_pending()

        if not self.remaining:
            self._finish_campaign()
            await self._async_save()
            self._notify()
            return

        self.state = "running"
        self.current = ""
        self.current_update_entity = ""
        self.index = min(len(self.done) + len(self.failed) + len(self.skipped) + 1, self.total)
        await self._async_save()
        self._notify()
        self._ensure_worker()

    async def async_stop(self) -> None:
        if self.state not in ("running", "paused"):
            return

        self.stop_requested = True
        self.pause_requested = False

        if self.state == "paused":
            self._finish_campaign(reset_lists=True)

        await self._async_save()
        self._notify()

    async def _async_on_hass_started(self, event: Event) -> None:
        await self._async_handle_post_startup_restore()

    async def _async_handle_post_startup_restore(self) -> None:
        if self.state != "paused" or not self.waiting_ha_started:
            return

        delay = self.entry.options.get(CONF_RESTORE_RESUME_DELAY, DEFAULT_RESTORE_RESUME_DELAY)
        self.resume_at_ts = int(time.time()) + delay
        await self._async_save()
        self._notify()

        if self._resume_task is not None:
            self._resume_task.cancel()

        self._resume_task = self.hass.loop.create_task(self._async_delayed_resume(delay))

    async def _async_delayed_resume(self, delay: int) -> None:
        try:
            await asyncio.sleep(delay)
            await self.async_resume()
        except asyncio.CancelledError:
            raise

    async def _pending_refresh_loop(self) -> None:
        try:
            while not self._shutdown:
                await self._async_refresh_pending_updates()
                await asyncio.sleep(DEFAULT_REFRESH_INTERVAL)
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Error in pending refresh loop")

    async def _async_refresh_pending_updates(self) -> None:
        registry = er.async_get(self.hass)
        result: list[str] = []

        for entity_id in self.hass.states.async_entity_ids("update"):
            state = self.hass.states.get(entity_id)
            if state is None or state.state != "on":
                continue

            entry = registry.async_get(entity_id)
            if entry is None:
                continue

            if entry.platform == "esphome":
                result.append(entity_id)

        result.sort()
        self._pending_update_entities = result
        self.pending_updates_count = len(result)
        self._notify()

    async def _async_restore(self) -> None:
        data = await self.store.async_load()
        if not data:
            return

        self.state = data.get("state", "idle")
        self.queue = data.get("queue", [])
        self.remaining = data.get("remaining", [])
        self.done = data.get("done", [])
        self.failed = data.get("failed", [])
        self.skipped = data.get("skipped", [])
        self.current = ""
        self.current_update_entity = ""
        self.total = data.get("total", len(self.queue))
        self.start_ts = int(data.get("start_ts", 0) or 0)
        self.end_ts = int(data.get("end_ts", 0) or 0)
        self.duration_s = int(data.get("duration_s", 0) or 0)
        self.avg_duration_s = int(data.get("avg_duration_s", 0) or 0)
        self.eta_s = int(data.get("eta_s", 0) or 0)
        self.delay_s = int(data.get("delay_s", 0) or self.entry.options.get(CONF_DELAY_MIN, DEFAULT_DELAY_MIN))
        self.cpu = data.get("cpu")
        self.temp = data.get("temp")
        self.load_1m = data.get("load_1m")
        self.pause_requested = bool(data.get("pause_requested", False))
        self.stop_requested = bool(data.get("stop_requested", False))
        self.last_error = data.get("last_error", "")

        if self.state in ("running", "paused") and self.remaining:
            self.state = "paused"
            self.pause_requested = False
            self.stop_requested = False
            self.waiting_ha_started = True
            self.resume_at_ts = 0
            self.index = min(len(self.done) + len(self.failed) + len(self.skipped) + 1, max(self.total, 1))
        else:
            self.waiting_ha_started = False
            self.resume_at_ts = 0
            self.index = min(len(self.done) + len(self.failed) + len(self.skipped), self.total)

        self._notify()

    async def _async_reconcile_remaining_with_pending(self) -> None:
        pending = set(self._pending_update_entities)

        newly_done = [entity_id for entity_id in self.remaining if entity_id not in pending]
        still_pending = [entity_id for entity_id in self.remaining if entity_id in pending]

        if newly_done:
            for entity_id in newly_done:
                if entity_id not in self.done:
                    self.done.append(entity_id)

        self.remaining = still_pending
        self.queue = list(dict.fromkeys(self.done + self.failed + self.skipped + self.remaining))
        self.total = max(self.total, len(self.queue))
        self.index = min(len(self.done) + len(self.failed) + len(self.skipped) + (1 if self.remaining else 0), self.total)

        processed = len(self.done) + len(self.failed) + len(self.skipped)
        if processed > 0 and self.start_ts:
            self.duration_s = max(0, int(time.time()) - self.start_ts)
            self.avg_duration_s = round(self.duration_s / processed, 1)
            self.eta_s = int(len(self.remaining) * self.avg_duration_s)
        else:
            self.eta_s = 0

    def _ensure_worker(self) -> None:
        if self._worker_task is not None and not self._worker_task.done():
            return
        self._worker_task = self.hass.loop.create_task(self._async_worker())

    async def _async_worker(self) -> None:
        timeout_s = int(self.entry.options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))

        try:
            while self.state == "running" and self.remaining:
                current = self.remaining[0]

                if self.stop_requested:
                    self._finish_campaign(reset_lists=True)
                    await self._async_save()
                    self._notify()
                    return

                if self.pause_requested:
                    self.state = "paused"
                    self.current = ""
                    self.current_update_entity = ""
                    await self._async_save()
                    self._notify()
                    return

                await self._async_refresh_pending_updates()
                if current not in self._pending_update_entities:
                    if current not in self.done:
                        self.done.append(current)
                    self.remaining.pop(0)
                    await self._async_post_item_update()
                    continue

                self.current = current
                self.current_update_entity = current
                self.index = min(len(self.done) + len(self.failed) + len(self.skipped) + 1, self.total)

                self.cpu = self._read_float_sensor(CONF_CPU_SENSOR, "sensor.processor_use")
                self.temp = self._read_float_sensor(CONF_TEMP_SENSOR, "sensor.processor_temperature")
                self.load_1m = self._read_float_sensor(CONF_LOAD_SENSOR, "sensor.load_1m")

                await self._async_save()
                self._notify()

                await self.hass.services.async_call(
                    "update",
                    "install",
                    {"entity_id": current},
                    blocking=False,
                )

                success = await self._async_wait_until_off(current, timeout_s)

                if success:
                    if current not in self.done:
                        self.done.append(current)
                else:
                    if current not in self.failed:
                        self.failed.append(current)
                    self.last_error = "timeout_or_still_on"

                if self.remaining and self.remaining[0] == current:
                    self.remaining.pop(0)

                self.current = ""
                self.current_update_entity = ""

                await self._async_post_item_update()

                if self.stop_requested:
                    self._finish_campaign(reset_lists=True)
                    await self._async_save()
                    self._notify()
                    return

                if self.pause_requested:
                    self.state = "paused"
                    await self._async_save()
                    self._notify()
                    return

                if self.remaining:
                    delay = self._compute_dynamic_delay()
                    self.delay_s = delay
                    await self._async_save()
                    self._notify()
                    await asyncio.sleep(delay)

            self._finish_campaign()
            await self._async_save()
            self._notify()

        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("ESU worker crashed")
            self.state = "paused"
            self.current = ""
            self.current_update_entity = ""
            self.last_error = "worker_crashed"
            await self._async_save()
            self._notify()

    async def _async_post_item_update(self) -> None:
        await self._async_refresh_pending_updates()
        await self._async_reconcile_remaining_with_pending()

        self.duration_s = max(0, int(time.time()) - self.start_ts) if self.start_ts else 0

        processed = len(self.done) + len(self.failed) + len(self.skipped)
        if processed > 0:
            self.avg_duration_s = round(self.duration_s / processed, 1)
            self.eta_s = int(len(self.remaining) * self.avg_duration_s)
        else:
            self.avg_duration_s = 0
            self.eta_s = 0

        await self._async_save()
        self._notify()

    async def _async_wait_until_off(self, entity_id: str, timeout_s: int) -> bool:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            state = self.hass.states.get(entity_id)
            if state is None or state.state == "off":
                return True
            await asyncio.sleep(2)
        state = self.hass.states.get(entity_id)
        return state is None or state.state == "off"

    def _compute_dynamic_delay(self) -> int:
        min_delay = int(self.entry.options.get(CONF_DELAY_MIN, DEFAULT_DELAY_MIN))
        max_delay = int(self.entry.options.get(CONF_DELAY_MAX, DEFAULT_DELAY_MAX))

        cpu_now = self._read_float_sensor(CONF_CPU_SENSOR, "sensor.processor_use")
        temp_now = self._read_float_sensor(CONF_TEMP_SENSOR, "sensor.processor_temperature")
        load_now = self._read_float_sensor(CONF_LOAD_SENSOR, "sensor.load_1m")

        self.cpu = cpu_now
        self.temp = temp_now
        self.load_1m = load_now

        stress_cpu = cpu_now / 100.0
        stress_load = load_now / 4.0
        stress_temp = ((temp_now - 50) / 25.0) if temp_now > 50 else 0.0
        stress = max(stress_cpu, stress_load, stress_temp)

        target = int(min_delay + stress * (max_delay - min_delay))
        if target < min_delay:
            return min_delay
        if target > max_delay:
            return max_delay
        return target

    def _read_float_sensor(self, option_key: str, fallback_entity_id: str) -> float:
        entity_id = self.entry.options.get(option_key, fallback_entity_id)
        state = self.hass.states.get(entity_id)
        if state is None:
            return 0.0
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return 0.0

    def _finish_campaign(self, reset_lists: bool = False) -> None:
        self.state = "idle"
        self.current = ""
        self.current_update_entity = ""
        self.pause_requested = False
        self.stop_requested = False
        self.waiting_ha_started = False
        self.resume_at_ts = 0
        self.end_ts = int(time.time())
        self.index = 0
        self.eta_s = 0

        if reset_lists:
            self.queue = []
            self.remaining = []
            self.done = []
            self.failed = []
            self.skipped = []
            self.total = 0
            self.duration_s = 0
            self.avg_duration_s = 0
            self.delay_s = 0
            self.last_error = ""

    def _reset_runtime_state(self) -> None:
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
        self.cpu = None
        self.temp = None
        self.load_1m = None
        self.pause_requested = False
        self.stop_requested = False
        self.waiting_ha_started = False
        self.resume_at_ts = 0

    async def _async_save(self) -> None:
        data = deepcopy(self.campaign_attributes())
        data["state"] = self.state
        await self.store.async_save(data)
