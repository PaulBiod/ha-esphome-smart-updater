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
    CONF_RESTORE_RESUME_DELAY,
    CONF_TEMP_SENSOR,
    CONF_THROTTLE,
    CONF_TIMEOUT,
    DEFAULT_DELAY_MAX,
    DEFAULT_DELAY_MIN,
    DEFAULT_MAX_ITEMS,
    DEFAULT_RESTORE_RESUME_DELAY,
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
        self.options_data = {}

    async def async_step_init(self, user_input=None):
        options = dict(self.config_entry.options)

        if user_input is not None:
            self.options_data = dict(user_input)

            if user_input.get(CONF_THROTTLE, False):
                return await self.async_step_throttle()

            self.options_data.pop(CONF_CPU_SENSOR, None)
            self.options_data.pop(CONF_TEMP_SENSOR, None)
            self.options_data.pop(CONF_LOAD_SENSOR, None)
            self.options_data.pop(CONF_DELAY_MIN, None)
            self.options_data.pop(CONF_DELAY_MAX, None)

            return self.async_create_entry(title="", data=self.options_data)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_TIMEOUT,
                        default=options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=60,
                            max=3600,
                            step=30,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        CONF_MAX_ITEMS,
                        default=options.get(CONF_MAX_ITEMS, DEFAULT_MAX_ITEMS),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=50,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        CONF_RESTORE_RESUME_DELAY,
                        default=options.get(
                            CONF_RESTORE_RESUME_DELAY,
                            DEFAULT_RESTORE_RESUME_DELAY,
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=1800,
                            step=30,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                    vol.Optional(
                        CONF_THROTTLE,
                        default=options.get(CONF_THROTTLE, False),
                    ): selector.BooleanSelector(),
                }
            ),
        )

    async def async_step_throttle(self, user_input=None):
        options = dict(self.config_entry.options)

        if user_input is not None:
            self.options_data.update(user_input)
            return self.async_create_entry(title="", data=self.options_data)

        return self.async_show_form(
            step_id="throttle",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CPU_SENSOR,
                        default=options.get(CONF_CPU_SENSOR),
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor", multiple=False)
                    ),
                    vol.Optional(
                        CONF_TEMP_SENSOR,
                        default=options.get(CONF_TEMP_SENSOR),
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor", multiple=False)
                    ),
                    vol.Optional(
                        CONF_LOAD_SENSOR,
                        default=options.get(CONF_LOAD_SENSOR),
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor", multiple=False)
                    ),
                    vol.Optional(
                        CONF_DELAY_MIN,
                        default=options.get(CONF_DELAY_MIN, DEFAULT_DELAY_MIN),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=120,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                    vol.Optional(
                        CONF_DELAY_MAX,
                        default=options.get(CONF_DELAY_MAX, DEFAULT_DELAY_MAX),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=300,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                }
            ),
        )
