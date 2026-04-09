from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BUTTON_PAUSE_UNIQUE_ID,
    BUTTON_RESUME_UNIQUE_ID,
    BUTTON_START_UNIQUE_ID,
    BUTTON_STOP_UNIQUE_ID,
    DOMAIN,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    manager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            ESUStartButton(manager),
            ESUPauseButton(manager),
            ESUResumeButton(manager),
            ESUStopButton(manager),
        ]
    )


class _BaseButton(ButtonEntity):
    _attr_should_poll = False

    def __init__(self, manager) -> None:
        self.manager = manager
        self._remove_listener = None

    async def async_added_to_hass(self) -> None:
        self._remove_listener = self.manager.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None


class ESUStartButton(_BaseButton):
    _attr_name = "ESU Start"
    _attr_unique_id = BUTTON_START_UNIQUE_ID
    _attr_icon = "mdi:play"

    async def async_press(self) -> None:
        await self.manager.async_start()


class ESUPauseButton(_BaseButton):
    _attr_name = "ESU Pause"
    _attr_unique_id = BUTTON_PAUSE_UNIQUE_ID
    _attr_icon = "mdi:pause"

    async def async_press(self) -> None:
        await self.manager.async_pause()


class ESUResumeButton(_BaseButton):
    _attr_name = "ESU Resume"
    _attr_unique_id = BUTTON_RESUME_UNIQUE_ID
    _attr_icon = "mdi:play"

    async def async_press(self) -> None:
        await self.manager.async_resume(manual=True)


class ESUStopButton(_BaseButton):
    _attr_name = "ESU Stop"
    _attr_unique_id = BUTTON_STOP_UNIQUE_ID
    _attr_icon = "mdi:stop"

    async def async_press(self) -> None:
        await self.manager.async_stop()
