from homeassistant import config_entries
import voluptuous as vol

from .const import DOMAIN, DEFAULT_TIMEOUT


class FlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return self.async_create_entry(title="ESPHome Smart Updater", data={})

    async def async_get_options_flow(self, entry):
        return OptionsFlow(entry)


class OptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry):
        self.entry = entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional("timeout", default=600): int,
                vol.Optional("throttle", default=True): bool,
                vol.Optional("delay_min", default=5): int,
                vol.Optional("delay_max", default=60): int,
            })
        )
