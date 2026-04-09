from __future__ import annotations

import asyncio
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)


class CampaignManager:
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.state = "idle"
        self.queue: list[str] = []
        self.current: str | None = None
        self.done: list[str] = []
        self.failed: list[str] = []
        self._listeners = []

    def add_listener(self, cb) -> None:
        self._listeners.append(cb)

    def _push(self) -> None:
        for cb in self._listeners:
            cb()

    async def start(self) -> None:
        if self.state == "running":
            return

        ent_reg = er.async_get(self.hass)
        updates: list[str] = []

        for eid in self.hass.states.async_entity_ids("update"):
            st = self.hass.states.get(eid)
            entry = ent_reg.async_get(eid)

            if not st or st.state != "on" or not entry:
                continue
            if entry.platform != "esphome":
                continue

            updates.append(eid)

        updates = updates[:3]
        _LOGGER.warning("ESU ESPHome queue: %s", updates)

        self.queue = updates
        self.done = []
        self.failed = []
        self.current = None
        self.state = "running" if self.queue else "idle"
        self._push()

        if self.queue:
            self.hass.async_create_task(self._run())

    async def _run(self) -> None:
        while self.queue:
            self.current = self.queue.pop(0)
            self._push()

            try:
                await self.hass.services.async_call(
                    "update",
                    "install",
                    {"entity_id": self.current},
                    blocking=True,
                )
                await asyncio.sleep(5)
                self.done.append(self.current)
            except Exception:
                _LOGGER.exception("ESU update failed for %s", self.current)
                self.failed.append(self.current)

            self.current = None
            self._push()

        self.state = "idle"
        self._push()
