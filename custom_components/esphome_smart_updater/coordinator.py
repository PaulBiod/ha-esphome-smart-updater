from __future__ import annotations

import asyncio
import time
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later

from .const import DOMAIN, DEFAULT_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class CampaignManager:
    def __init__(self, hass: HomeAssistant, entry):
        self.hass = hass
        self.entry = entry

        self.state = "idle"
        self.queue = []
        self.done = []
        self.failed = []
        self.current = None

        self.start_ts = None
        self.delay = 5

        self.pause_requested = False
        self.stop_requested = False

        self.listeners = []

    # ========= listeners =========
    def add_listener(self, cb):
        self.listeners.append(cb)

    def push(self):
        for cb in self.listeners:
            cb()

    # ========= options =========
    def get_option(self, key, default):
        return self.entry.options.get(key, default)

    # ========= start =========
    async def start(self):
        if self.state == "running":
            return

        self.queue = self._find_updates()[:1]
        self.done = []
        self.failed = []
        self.current = None

        self.start_ts = time.time()

        if not self.queue:
            return

        self.state = "running"
        self.push()

        self.hass.async_create_task(self._run())

    # ========= pause =========
    async def pause(self):
        self.pause_requested = True

    async def resume(self):
        if self.state == "paused":
            self.state = "running"
            self.pause_requested = False
            self.push()
            self.hass.async_create_task(self._run())

    async def stop(self):
        self.stop_requested = True

    # ========= worker =========
    async def _run(self):
        while self.queue:

            if self.stop_requested:
                break

            if self.pause_requested:
                self.state = "paused"
                self.push()
                return

            self.current = self.queue.pop(0)
            self.push()

            timeout = self.get_option("timeout", DEFAULT_TIMEOUT)
            start = time.time()

            try:
                await self.hass.services.async_call(
                    "update",
                    "install",
                    {"entity_id": self.current},
                    blocking=False,
                )
            except Exception:
                self.failed.append(self.current)
                continue

            # ===== wait finish =====
            while True:
                state = self.hass.states.get(self.current)

                if not state:
                    break

                in_progress = state.attributes.get("in_progress")

                if not in_progress:
                    break

                if time.time() - start > timeout:
                    _LOGGER.warning("timeout %s", self.current)
                    self.failed.append(self.current)
                    break

                await asyncio.sleep(5)

            self.done.append(self.current)
            self.current = None
            self.push()

            # ===== throttle =====
            delay_min = self.get_option("delay_min", 5)
            delay_max = self.get_option("delay_max", 60)

            self.delay = min(delay_max, max(delay_min, self.delay))
            await asyncio.sleep(self.delay)

        self.state = "idle"
        self.current = None
        self.push()

    # ========= find updates =========
    def _find_updates(self):
        result = []

        for s in self.hass.states.async_all("update"):
            if s.state != "on":
                continue

            if s.attributes.get("device_class") != "firmware":
                continue

            result.append(s.entity_id)

        return result

    # ========= computed =========
    def progress(self):
        total = len(self.done) + len(self.failed) + len(self.queue) + (1 if self.current else 0)
        if total == 0:
            return 0
        return round((len(self.done) + len(self.failed)) / total * 100)

    def eta(self):
        if not self.start_ts:
            return 0

        elapsed = time.time() - self.start_ts
        done = len(self.done)

        if done == 0:
            return 0

        avg = elapsed / done
        remaining = len(self.queue)

        return int(avg * remaining)
