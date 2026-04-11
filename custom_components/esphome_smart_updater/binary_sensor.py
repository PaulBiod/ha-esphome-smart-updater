from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BINARY_SENSOR_CURRENT_ERROR_VISIBLE_UNIQUE_ID,
    BINARY_SENSOR_LAST_DEVICE_RUNNING_UNIQUE_ID,
    BINARY_SENSOR_PAUSE_INFO_VISIBLE_UNIQUE_ID,
    BINARY_SENSOR_PAUSE_REQUESTED_UNIQUE_ID,
    BINARY_SENSOR_REPORT_AVAILABLE_UNIQUE_ID,
    BINARY_SENSOR_STOP_REQUESTED_UNIQUE_ID,
    BINARY_SENSOR_THROTTLE_ENABLED_UNIQUE_ID,
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
            ESUReportAvailableBinarySensor(manager),
            ESUThrottleEnabledBinarySensor(manager),
            ESUPauseRequestedBinarySensor(manager),
            ESUStopRequestedBinarySensor(manager),
            ESULastDeviceRunningBinarySensor(manager),
            ESUPauseInfoVisibleBinarySensor(manager),
            ESUCurrentErrorVisibleBinarySensor(manager),
        ]
    )


class _BaseESUBinarySensor(BinarySensorEntity):
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


class ESUReportAvailableBinarySensor(_BaseESUBinarySensor):
    _attr_name = "ESPHome Smart Updater Report Available"
    _attr_unique_id = BINARY_SENSOR_REPORT_AVAILABLE_UNIQUE_ID
    _attr_icon = "mdi:file-document-check"

    @property
    def is_on(self):
        return self.manager.report_available


class ESUThrottleEnabledBinarySensor(_BaseESUBinarySensor):
    _attr_name = "ESPHome Smart Updater Throttle Enabled"
    _attr_unique_id = BINARY_SENSOR_THROTTLE_ENABLED_UNIQUE_ID
    _attr_icon = "mdi:speedometer"

    @property
    def is_on(self):
        return self.manager.throttle_enabled


class ESUPauseRequestedBinarySensor(_BaseESUBinarySensor):
    _attr_name = "ESPHome Smart Updater Pause Requested"
    _attr_unique_id = BINARY_SENSOR_PAUSE_REQUESTED_UNIQUE_ID
    _attr_icon = "mdi:pause-circle"

    @property
    def is_on(self):
        return self.manager.pause_requested


class ESUStopRequestedBinarySensor(_BaseESUBinarySensor):
    _attr_name = "ESPHome Smart Updater Stop Requested"
    _attr_unique_id = BINARY_SENSOR_STOP_REQUESTED_UNIQUE_ID
    _attr_icon = "mdi:stop-circle"

    @property
    def is_on(self):
        return self.manager.stop_requested


class ESULastDeviceRunningBinarySensor(_BaseESUBinarySensor):
    _attr_name = "ESPHome Smart Updater Last Device Running"
    _attr_unique_id = BINARY_SENSOR_LAST_DEVICE_RUNNING_UNIQUE_ID
    _attr_icon = "mdi:playlist-check"

    @property
    def is_on(self):
        remaining = self.manager.remaining or []
        current = self.manager.current_update_entity
        total = int(self.manager.total or 0)
        index = int(self.manager.index or 0)
        state = getattr(self.manager, "state", "idle")

        if state != "running" or not current:
            return False

        if len(remaining) == 0:
            return True

        return total > 0 and index >= total

class ESUPauseInfoVisibleBinarySensor(_BaseESUBinarySensor):
    _attr_name = "ESPHome Smart Updater Pause Info Visible"
    _attr_unique_id = BINARY_SENSOR_PAUSE_INFO_VISIBLE_UNIQUE_ID
    _attr_icon = "mdi:information-outline"

    @property
    def is_on(self):
        if self.manager.state != "paused":
            return False

        if self.manager.waiting_ha_started:
            return True

        resume_at_ts = int(getattr(self.manager, "resume_at_ts", 0) or 0)
        return resume_at_ts > 0


class ESUCurrentErrorVisibleBinarySensor(_BaseESUBinarySensor):
    _attr_name = "ESPHome Smart Updater Current Error Visible"
    _attr_unique_id = BINARY_SENSOR_CURRENT_ERROR_VISIBLE_UNIQUE_ID
    _attr_icon = "mdi:alert-outline"

    @property
    def is_on(self):
        if self.manager.state not in ("running", "paused"):
            return False

        current_error = str(getattr(self.manager, "current_error", "") or "").strip()
        if current_error:
            return True

        recent_errors = getattr(self.manager, "recent_errors", None) or []
        return any(str(item or "").strip() for item in recent_errors)

