from homeassistant.components.button import ButtonEntity
from .coordinator import CampaignManager, DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    manager: CampaignManager = hass.data[DOMAIN]

    async_add_entities([StartButton(manager)], True)


class StartButton(ButtonEntity):
    def __init__(self, manager):
        self.manager = manager
        self._attr_name = "ESPHome Smart Updater Start"

    async def async_press(self):
        await self.manager.start()
