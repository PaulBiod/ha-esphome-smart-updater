from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    DOMAIN,
    SERVICE_CLEAR_REPORT,
    SERVICE_PAUSE_CAMPAIGN,
    SERVICE_RESUME_CAMPAIGN,
    SERVICE_START_CAMPAIGN,
    SERVICE_STOP_CAMPAIGN,
)
from .coordinator import CampaignManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "button", "binary_sensor"]
SERVICE_PREVIEW_CAMPAIGN = "preview_campaign"


def _get_manager(hass: HomeAssistant) -> CampaignManager | None:
    managers: dict[str, CampaignManager] = hass.data.get(DOMAIN, {})
    if not managers:
        return None
    return next(iter(managers.values()), None)


async def _async_handle_start(call: ServiceCall) -> None:
    hass: HomeAssistant = call.hass  # type: ignore[attr-defined]
    manager = _get_manager(hass)
    if manager is None:
        _LOGGER.warning("No ESPHome Smart Updater manager available for start_campaign")
        return
    await manager.async_start()


async def _async_handle_pause(call: ServiceCall) -> None:
    hass: HomeAssistant = call.hass  # type: ignore[attr-defined]
    manager = _get_manager(hass)
    if manager is None:
        _LOGGER.warning("No ESPHome Smart Updater manager available for pause_campaign")
        return
    await manager.async_pause()


async def _async_handle_resume(call: ServiceCall) -> None:
    hass: HomeAssistant = call.hass  # type: ignore[attr-defined]
    manager = _get_manager(hass)
    if manager is None:
        _LOGGER.warning("No ESPHome Smart Updater manager available for resume_campaign")
        return
    await manager.async_resume(manual=True)


async def _async_handle_stop(call: ServiceCall) -> None:
    hass: HomeAssistant = call.hass  # type: ignore[attr-defined]
    manager = _get_manager(hass)
    if manager is None:
        _LOGGER.warning("No ESPHome Smart Updater manager available for stop_campaign")
        return
    await manager.async_stop()


async def _async_handle_clear_report(call: ServiceCall) -> None:
    hass: HomeAssistant = call.hass  # type: ignore[attr-defined]
    manager = _get_manager(hass)
    if manager is None:
        _LOGGER.warning("No ESPHome Smart Updater manager available for clear_report")
        return
    await manager.async_clear_report()


async def _async_handle_preview(call: ServiceCall) -> None:
    hass: HomeAssistant = call.hass  # type: ignore[attr-defined]
    manager = _get_manager(hass)
    if manager is None:
        _LOGGER.warning("No ESPHome Smart Updater manager available for preview_campaign")
        return
    entity_ids = call.data.get("entity_ids")
    await manager.async_preview(entity_ids=entity_ids)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    manager: CampaignManager | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)

    if manager is None:
        return

    await manager._async_refresh_pending_updates()
    await manager._async_save()
    manager._notify()


def _ensure_services_registered(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_START_CAMPAIGN):
        return

    hass.services.async_register(DOMAIN, SERVICE_START_CAMPAIGN, _async_handle_start)
    hass.services.async_register(DOMAIN, SERVICE_PAUSE_CAMPAIGN, _async_handle_pause)
    hass.services.async_register(DOMAIN, SERVICE_RESUME_CAMPAIGN, _async_handle_resume)
    hass.services.async_register(DOMAIN, SERVICE_STOP_CAMPAIGN, _async_handle_stop)
    hass.services.async_register(DOMAIN, SERVICE_CLEAR_REPORT, _async_handle_clear_report)
    hass.services.async_register(DOMAIN, SERVICE_PREVIEW_CAMPAIGN, _async_handle_preview)


def _remove_services(hass: HomeAssistant) -> None:
    for service_name in (
        SERVICE_START_CAMPAIGN,
        SERVICE_PAUSE_CAMPAIGN,
        SERVICE_RESUME_CAMPAIGN,
        SERVICE_STOP_CAMPAIGN,
        SERVICE_CLEAR_REPORT,
        SERVICE_PREVIEW_CAMPAIGN,
    ):
        if hass.services.has_service(DOMAIN, service_name):
            hass.services.async_remove(DOMAIN, service_name)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager = CampaignManager(hass, entry)
    await manager.async_initialize()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = manager

    _ensure_services_registered(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    manager: CampaignManager | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if manager is not None:
        await manager.async_shutdown()

    if DOMAIN in hass.data and not hass.data[DOMAIN]:
        _remove_services(hass)
        hass.data.pop(DOMAIN)

    return unload_ok
