from __future__ import annotations

import asyncio
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class CampaignManager(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self.hass = hass
        self.state = "idle"
        self.queue: list[str] = []
        self.current: str | None = None
        self.done: list[str] = []
        self.failed: list[str] = []

    async def _async_update_data(self) -> dict:
        return self._build_data()

    def _build_data(self) -> dict:
        total = len(self.queue) + len(self.done) + len(self.failed) + (1 if self.current else 0)
        finished = len(self.done) + len(self.failed)
        return {
            "state": self.state,
            "current": self.current,
            "queue": list(self.queue),
            "done": list(self.done),
            "failed": list(self.failed),
            "finished": finished,
            "total": total,
        }

    async def _push_state(self) -> None:
        self.async_set_updated_data(self._build_data())

    async def start(self) -> None:
        if self.state == "running":
            return

        updates = []
        for entity_id in self.hass.states.async_entity_ids("update"):
            state = self.hass.states.get(entity_id)
            if entity_id.startswith("update.") and state and state.state == "on":
                updates.append(entity_id)

        self.queue = updates
        self.done = []
        self.failed = []
        self.current = None
        self.state = "running" if self.queue else "idle"
        await self._push_state()

        if self.queue:
            self.hass.async_create_task(self._run())

    async def _run(self) -> None:
        while self.queue:
            self.current = self.queue.pop(0)
            await self._push_state()

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
                _LOGGER.exception("Update failed for %s", self.current)
                self.failed.append(self.current)

            self.current = None
            await self._push_state()

        self.state = "idle"
        await self._push_state()
