from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CAMPAIGN_SENSOR_UNIQUE_ID, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    manager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ESPHomeSmartUpdaterCampaignSensor(manager)])


class ESPHomeSmartUpdaterCampaignSensor(SensorEntity):
    _attr_name = "ESPHome Smart Updater Campaign"
    _attr_unique_id = CAMPAIGN_SENSOR_UNIQUE_ID
    _attr_icon = "mdi:upload-network"

    def __init__(self, manager) -> None:
        self.manager = manager
        self._remove_listener = None

    async def async_added_to_hass(self) -> None:
        self._remove_listener = self.manager.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None

    @property
    def native_value(self):
        return self.manager.state

    @property
    def extra_state_attributes(self):
        return self.manager.campaign_attributes()
