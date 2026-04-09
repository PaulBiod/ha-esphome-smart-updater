from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    coordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([
        ESUStateSensor(coordinator),
        ESUCurrentSensor(coordinator),
        ESUProgressSensor(coordinator),
    ])


class BaseSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)


class ESUStateSensor(BaseSensor):
    _attr_name = "ESPHome Smart Updater State"
    _attr_unique_id = "esu_state"

    @property
    def native_value(self):
        return self.coordinator.data.get("state")


class ESUCurrentSensor(BaseSensor):
    _attr_name = "ESPHome Smart Updater Current"
    _attr_unique_id = "esu_current"

    @property
    def native_value(self):
        return self.coordinator.data.get("current")


class ESUProgressSensor(BaseSensor):
    _attr_name = "ESPHome Smart Updater Progress"
    _attr_unique_id = "esu_progress"
    _attr_native_unit_of_measurement = "%"

    @property
    def native_value(self):
        finished = self.coordinator.data.get("finished", 0)
        total = self.coordinator.data.get("total", 0)
        return 0 if total == 0 else round((finished / total) * 100)

    @property
    def extra_state_attributes(self):
        return self.coordinator.data
