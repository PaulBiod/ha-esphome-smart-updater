from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_CPU_SENSOR,
    CONF_DELAY_MAX,
    CONF_DELAY_MIN,
    CONF_DEVICE_SELECTION_MODE,
    CONF_EXCLUDED_UPDATE_ENTITIES,
    CONF_LOAD_SENSOR,
    CONF_MAX_ITEMS,
    CONF_RESTORE_RESUME_DELAY,
    CONF_SELECTED_UPDATE_ENTITIES,
    CONF_TEMP_SENSOR,
    CONF_THROTTLE,
    CONF_TIMEOUT,
    DEFAULT_DELAY_MAX,
    DEFAULT_DELAY_MIN,
    DEFAULT_MAX_ITEMS,
    DEFAULT_RESTORE_RESUME_DELAY,
    DEFAULT_TIMEOUT,
    DEVICE_SELECTION_ALL,
    DEVICE_SELECTION_EXCLUDE,
    DEVICE_SELECTION_SELECTED,
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
        self._config_entry = config_entry
        self.options_data = {}

    def _get_esphome_update_options(self) -> list[selector.SelectOptionDict]:
        options: list[selector.SelectOptionDict] = []
        registry = er.async_get(self.hass)

        seen: set[str] = set()

        for entry in sorted(
            registry.entities.values(),
            key=lambda item: item.entity_id,
        ):
            if entry.domain != "update":
                continue
            if entry.platform != "esphome":
                continue

            entity_id = entry.entity_id
            if entity_id in seen:
                continue

            state = self.hass.states.get(entity_id)
            friendly_name = None
            if state is not None:
                friendly_name = state.attributes.get("friendly_name")

            friendly_name = (
                friendly_name
                or entry.name
                or entry.original_name
                or entity_id
            )

            options.append(
                selector.SelectOptionDict(
                    value=entity_id,
                    label=f"{friendly_name} ({entity_id})",
                )
            )
            seen.add(entity_id)

        if options:
            return options

        for entity_id in sorted(self.hass.states.async_entity_ids("update")):
            if entity_id in seen:
                continue

            state = self.hass.states.get(entity_id)
            if state is None:
                continue

            integration = (state.attributes.get("integration") or "").lower()
            if integration != "esphome":
                continue

            friendly_name = state.attributes.get("friendly_name") or entity_id
            options.append(
                selector.SelectOptionDict(
                    value=entity_id,
                    label=f"{friendly_name} ({entity_id})",
                )
            )
            seen.add(entity_id)

        return options

    def _should_open_device_scope_step(self) -> bool:
        mode = self.options_data.get(
            CONF_DEVICE_SELECTION_MODE,
            self._config_entry.options.get(CONF_DEVICE_SELECTION_MODE, DEVICE_SELECTION_ALL),
        )
        return mode in (DEVICE_SELECTION_SELECTED, DEVICE_SELECTION_EXCLUDE)

    def _clear_throttle_options(self) -> None:
        self.options_data.pop(CONF_CPU_SENSOR, None)
        self.options_data.pop(CONF_TEMP_SENSOR, None)
        self.options_data.pop(CONF_LOAD_SENSOR, None)
        self.options_data.pop(CONF_DELAY_MIN, None)
        self.options_data.pop(CONF_DELAY_MAX, None)

    async def async_step_init(self, user_input=None):
        options = dict(self._config_entry.options)

        if user_input is not None:
            self.options_data = dict(user_input)

            if self._should_open_device_scope_step():
                return await self.async_step_device_scope()

            self.options_data.pop(CONF_SELECTED_UPDATE_ENTITIES, None)
            self.options_data.pop(CONF_EXCLUDED_UPDATE_ENTITIES, None)

            if user_input.get(CONF_THROTTLE, False):
                return await self.async_step_throttle()

            self._clear_throttle_options()
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
                        CONF_DEVICE_SELECTION_MODE,
                        default=options.get(
                            CONF_DEVICE_SELECTION_MODE,
                            DEVICE_SELECTION_ALL,
                        ),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                DEVICE_SELECTION_ALL,
                                DEVICE_SELECTION_SELECTED,
                                DEVICE_SELECTION_EXCLUDE,
                            ],
                            translation_key="device_selection_mode",
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(
                        CONF_THROTTLE,
                        default=options.get(CONF_THROTTLE, False),
                    ): selector.BooleanSelector(),
                }
            ),
        )

    async def async_step_device_scope(self, user_input=None):
        options = dict(self._config_entry.options)
        mode = self.options_data.get(
            CONF_DEVICE_SELECTION_MODE,
            options.get(CONF_DEVICE_SELECTION_MODE, DEVICE_SELECTION_ALL),
        )

        if mode == DEVICE_SELECTION_SELECTED:
            return await self.async_step_select_devices_include(user_input)
        if mode == DEVICE_SELECTION_EXCLUDE:
            return await self.async_step_select_devices_exclude(user_input)

        return self.async_create_entry(title="", data=self.options_data)

    async def async_step_select_devices_include(self, user_input=None):
        return await self._async_step_device_list(
            step_id="select_devices_include",
            field_name=CONF_SELECTED_UPDATE_ENTITIES,
            remove_field=CONF_EXCLUDED_UPDATE_ENTITIES,
            user_input=user_input,
        )

    async def async_step_select_devices_exclude(self, user_input=None):
        return await self._async_step_device_list(
            step_id="select_devices_exclude",
            field_name=CONF_EXCLUDED_UPDATE_ENTITIES,
            remove_field=CONF_SELECTED_UPDATE_ENTITIES,
            user_input=user_input,
        )

    async def _async_step_device_list(self, step_id, field_name, remove_field, user_input=None):
        options = dict(self._config_entry.options)
        selector_options = self._get_esphome_update_options()
        errors = {}

        if user_input is not None:
            selected_entities = user_input.get(field_name, [])
            if not selected_entities:
                errors["base"] = (
                    "include_device_list_required"
                    if field_name == CONF_SELECTED_UPDATE_ENTITIES
                    else "exclude_device_list_required"
                )
            else:
                self.options_data[field_name] = selected_entities
                self.options_data.pop(remove_field, None)

                if self.options_data.get(CONF_THROTTLE, False):
                    return await self.async_step_throttle()

                self._clear_throttle_options()
                return self.async_create_entry(title="", data=self.options_data)

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        field_name,
                        default=self.options_data.get(field_name, options.get(field_name, [])),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=selector_options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_throttle(self, user_input=None):
        options = dict(self._config_entry.options)

        if user_input is not None:
            for key in (CONF_CPU_SENSOR, CONF_TEMP_SENSOR, CONF_LOAD_SENSOR):
                value = user_input.get(key)
                if value:
                    self.options_data[key] = value
                else:
                    self.options_data.pop(key, None)

            for key in (CONF_DELAY_MIN, CONF_DELAY_MAX):
                if key in user_input:
                    self.options_data[key] = user_input[key]

            return self.async_create_entry(title="", data=self.options_data)

        schema = vol.Schema(
            {
                vol.Optional(CONF_CPU_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", multiple=False)
                ),
                vol.Optional(CONF_TEMP_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", multiple=False)
                ),
                vol.Optional(CONF_LOAD_SENSOR): selector.EntitySelector(
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
        )

        suggested = {
            key: options[key]
            for key in (CONF_CPU_SENSOR, CONF_TEMP_SENSOR, CONF_LOAD_SENSOR)
            if options.get(key)
        }

        return self.async_show_form(
            step_id="throttle",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
        )
