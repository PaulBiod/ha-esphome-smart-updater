import asyncio
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN


class CampaignManager(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant):
        super().__init__(hass, logger=None, name=DOMAIN)
        self.hass = hass

        # state
        self.state = "idle"
        self.queue = []
        self.current = None

    async def start(self):
        if self.state != "idle":
            return

        self.state = "running"

        # récupère les updates ESPHome
        updates = [
            entity_id
            for entity_id in self.hass.states.async_entity_ids("update")
            if entity_id.startswith("update.")
            and self.hass.states.get(entity_id).state == "on"
        ]

        self.queue = updates

        self.hass.loop.create_task(self._run())

    async def _run(self):
        while self.queue:
            self.current = self.queue.pop(0)

            await self.hass.services.async_call(
                "update",
                "install",
                {"entity_id": self.current},
                blocking=True,
            )

            # wait simple (on fera mieux après)
            await asyncio.sleep(5)

        self.state = "done"
        self.current = None