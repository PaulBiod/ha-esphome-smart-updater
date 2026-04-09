from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            ESPHomeSmartUpdaterStateSensor(coordinator),
            ESPHomeSmartUpdaterCurrentSensor(coordinator),
            ESPHomeSmartUpdaterProgressSensor(coordinator),
        ]
    )


class _BaseSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)


class ESPHomeSmartUpdaterStateSensor(_BaseSensor):
    _attr_name = "ESPHome Smart Updater State"
    _attr_unique_id = "esphome_smart_updater_state"

    @property
    def native_value(self):
        return self.coordinator.data.get("state", "idle")


class ESPHomeSmartUpdaterCurrentSensor(_BaseSensor):
    _attr_name = "ESPHome Smart Updater Current"
    _attr_unique_id = "esphome_smart_updater_current"

    @property
    def native_value(self):
        return self.coordinator.data.get("current")


class ESPHomeSmartUpdaterProgressSensor(_BaseSensor):
    _attr_name = "ESPHome Smart Updater Progress"
    _attr_unique_id = "esphome_smart_updater_progress"
    _attr_native_unit_of_measurement = "%"

    @property
    def native_value(self):
        finished = self.coordinator.data.get("finished", 0)
        total = self.coordinator.data.get("total", 0)
        return 0 if total == 0 else round((finished / total) * 100)

    @property
    def extra_state_attributes(self):
        return {
            "finished": self.coordinator.data.get("finished", 0),
            "total": self.coordinator.data.get("total", 0),
            "done": self.coordinator.data.get("done", []),
            "failed": self.coordinator.data.get("failed", []),
            "queue": self.coordinator.data.get("queue", []),
        }
