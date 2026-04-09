from .coordinator import CampaignManager, DOMAIN

async def async_setup_entry(hass, entry):
    manager = CampaignManager(hass)
    hass.data[DOMAIN] = manager
    return True

async def async_unload_entry(hass, entry):
    hass.data.pop(DOMAIN)
    return True
