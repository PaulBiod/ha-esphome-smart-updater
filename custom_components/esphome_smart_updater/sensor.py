from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CAMPAIGN_SENSOR_UNIQUE_ID,
    DOMAIN,
    PENDING_UPDATES_SENSOR_UNIQUE_ID,
    PROGRESS_SENSOR_UNIQUE_ID,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    manager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            ESPHomeSmartUpdaterCampaignSensor(manager),
            ESPHomeSmartUpdaterPendingUpdatesSensor(manager),
            ESPHomeSmartUpdaterProgressSensor(manager),
        ]
    )


class _BaseESUSensor(SensorEntity):
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


class ESPHomeSmartUpdaterCampaignSensor(_BaseESUSensor):
    _attr_name = "ESPHome Smart Updater Campaign"
    _attr_unique_id = CAMPAIGN_SENSOR_UNIQUE_ID
    _attr_icon = "mdi:upload-network"

    @property
    def native_value(self):
        return self.manager.state

    @property
    def extra_state_attributes(self):
        return self.manager.campaign_attributes()


class ESPHomeSmartUpdaterPendingUpdatesSensor(_BaseESUSensor):
    _attr_name = "ESPHome Smart Updater Pending Updates"
    _attr_unique_id = PENDING_UPDATES_SENSOR_UNIQUE_ID
    _attr_icon = "mdi:update"

    @property
    def native_value(self):
        return self.manager.pending_updates_count

    @property
    def extra_state_attributes(self):
        entities = self.manager.pending_updates_entities()
        return {
            "pending_updates": entities,
            "total": len(entities),
        }


class ESPHomeSmartUpdaterProgressSensor(_BaseESUSensor):
    _attr_name = "ESPHome Smart Updater Progress"
    _attr_unique_id = PROGRESS_SENSOR_UNIQUE_ID
    _attr_icon = "mdi:progress-check"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        total = int(self.manager.total or 0)
        done = len(self.manager.done or [])
        if total <= 0:
            return 0
        return round((done / total) * 100)

    @property
    def extra_state_attributes(self):
        total = int(self.manager.total or 0)
        done = len(self.manager.done or [])
        failed = len(self.manager.failed or [])
        skipped = len(self.manager.skipped or [])
        current = self.manager.current_update_entity or ""
        processed = done + failed + skipped
        return {
            "done_count": done,
            "failed_count": failed,
            "skipped_count": skipped,
            "processed_count": processed,
            "total": total,
            "current_update_entity": current,
        }
