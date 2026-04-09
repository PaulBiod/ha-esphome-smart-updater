from __future__ import annotations
from homeassistant import config_entries
from .const import DOMAIN

class ESPHomeSmartUpdaterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        return self.async_create_entry(title="ESPHome Smart Updater", data={})

    @staticmethod
    def async_get_options_flow(config_entry):
        return ESPHomeSmartUpdaterOptionsFlow(config_entry)

class ESPHomeSmartUpdaterOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        return self.async_create_entry(title="", data={})
