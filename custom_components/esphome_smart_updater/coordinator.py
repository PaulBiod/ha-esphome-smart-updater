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
            update_interval=None,  # 👈 IMPORTANT
        )

        self.hass = hass
        self.state = "idle"
        self.queue = []
        self.current = None
        self.done = []
        self.failed = []

    async def start(self):
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

        self.async_set_updated_data({})

        if self.queue:
            self.hass.async_create_task(self._run())

    async def _run(self):
        while self.queue:
            self.current = self.queue.pop(0)
            self.async_set_updated_data({})

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
            self.async_set_updated_data({})

        self.state = "idle"
        self.async_set_updated_data({})
