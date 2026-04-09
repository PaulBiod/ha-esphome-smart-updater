from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    CONF_CPU_SENSOR,
    CONF_DELAY_MAX,
    CONF_DELAY_MIN,
    CONF_LOAD_SENSOR,
    CONF_MAX_ITEMS,
    CONF_TEMP_SENSOR,
    CONF_THROTTLE,
    CONF_TIMEOUT,
    DEFAULT_DELAY_MAX,
    DEFAULT_DELAY_MIN,
    DEFAULT_MAX_ITEMS,
    DEFAULT_TIMEOUT,
    DOMAIN,
)


class ESPHomeSmartUpdaterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        return self.async_create_entry(
            title="ESPHome Smart Updater",
            data={},
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return ESPHomeSmartUpdaterOptionsFlow(config_entry)


class ESPHomeSmartUpdaterOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = dict(self.config_entry.options)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_TIMEOUT, default=options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)): int,
                    vol.Optional(CONF_MAX_ITEMS, default=options.get(CONF_MAX_ITEMS, DEFAULT_MAX_ITEMS)): int,
                    vol.Optional(CONF_THROTTLE, default=options.get(CONF_THROTTLE, False)): bool,
                    vol.Optional(CONF_DELAY_MIN, default=options.get(CONF_DELAY_MIN, DEFAULT_DELAY_MIN)): int,
                    vol.Optional(CONF_DELAY_MAX, default=options.get(CONF_DELAY_MAX, DEFAULT_DELAY_MAX)): int,
                    vol.Optional(CONF_CPU_SENSOR, default=options.get(CONF_CPU_SENSOR, "")): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor", multiple=False)
                    ),
                    vol.Optional(CONF_TEMP_SENSOR, default=options.get(CONF_TEMP_SENSOR, "")): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor", multiple=False)
                    ),
                    vol.Optional(CONF_LOAD_SENSOR, default=options.get(CONF_LOAD_SENSOR, "")): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor", multiple=False)
                    ),
                }
            ),
        )
