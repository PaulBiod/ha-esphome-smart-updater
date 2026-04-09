from homeassistant.components.sensor import SensorEntity
from .coordinator import CampaignManager, DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    manager: CampaignManager = hass.data[DOMAIN]

    async_add_entities([
        StateSensor(manager),
        CurrentSensor(manager),
    ], True)


class StateSensor(SensorEntity):
    def __init__(self, manager):
        self.manager = manager
        self._attr_name = "ESPHome Smart Updater State"

    @property
    def state(self):
        return "running" if self.manager.running else "idle"


class CurrentSensor(SensorEntity):
    def __init__(self, manager):
        self.manager = manager
        self._attr_name = "ESPHome Smart Updater Current"

    @property
    def state(self):
        return self.manager.current or "none"
