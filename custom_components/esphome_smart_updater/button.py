from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([ESPHomeSmartUpdaterStartButton(hass, entry)])


class ESPHomeSmartUpdaterStartButton(ButtonEntity):
    _attr_name = "ESPHome Smart Updater Start"
    _attr_unique_id = "esphome_smart_updater_start"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry

    async def async_press(self) -> None:
        manager = self.hass.data[DOMAIN][self.entry.entry_id]
        await manager.start()
