from __future__ import annotations

import asyncio
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class CampaignManager(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,
        )

        self.hass = hass
        self.state = "idle"
        self.queue: list[str] = []
        self.current: str | None = None
        self.done: list[str] = []
        self.failed: list[str] = []

        self.async_set_updated_data(self._data())

    def _data(self) -> dict:
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

    def _push(self) -> None:
        self.async_set_updated_data(self._data())

    async def start(self) -> None:
        if self.state == "running":
            return

        updates = [
            entity_id
            for entity_id in self.hass.states.async_entity_ids("update")
            if entity_id.startswith("update.")
            and self.hass.states.get(entity_id)
            and self.hass.states.get(entity_id).state == "on"
        ]

        max_items = 1
        updates = updates[:max_items]

        _LOGGER.warning("ESU found %s update(s): %s", len(updates), updates)

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
                _LOGGER.exception("Update failed for %s", self.current)
                self.failed.append(self.current)

            self.current = None
            self._push()

        self.state = "idle"
        self._push()
