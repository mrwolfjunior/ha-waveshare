"""Config Flow and Options Flow for Waveshare Relay integration.

ConfigFlow:   sets up the bridge connection (host, port, slave IDs, scan interval).
OptionsFlow:  manages the list of virtual devices (lights and covers).
              Accessed via Settings → Integrations → Waveshare Relay → Configure.
"""
from __future__ import annotations

import uuid
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_DEVICES,
    CONF_HOST,
    CONF_PORT,
    CONF_PULSE_MS,
    CONF_RELAY_CLOSE,
    CONF_RELAY_INDEX,
    CONF_RELAY_OPEN,
    CONF_SCAN_INTERVAL,
    CONF_SENSOR_REGISTER,
    CONF_SENSOR_SLAVE,
    CONF_SLAVE_RELAY,
    CONF_SLAVE_SENSOR,
    CONF_TILT_MS,
    DEFAULT_PORT,
    DEFAULT_PULSE_MS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE_RELAY,
    DEFAULT_SLAVE_SENSOR,
    DEFAULT_TILT_MS,
    DEVICE_TYPE_COVER,
    DEVICE_TYPE_LIGHT,
    DOMAIN,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _int_selector(min_v: int = 0, max_v: int = 65535) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(min=min_v, max=max_v, step=1, mode=NumberSelectorMode.BOX)
    )


def _text_selector() -> TextSelector:
    return TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT))


# ---------------------------------------------------------------------------
# ConfigFlow — bridge setup
# ---------------------------------------------------------------------------

class WaveshareConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial integration setup (bridge parameters)."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            # Test connection
            from .modbus_client import WaveshareModbusClient
            client = WaveshareModbusClient(user_input[CONF_HOST], int(user_input[CONF_PORT]))
            try:
                await client.connect()
                await client.disconnect()
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                # Persist as integers
                data = {
                    CONF_HOST: user_input[CONF_HOST],
                    CONF_PORT: int(user_input[CONF_PORT]),
                    CONF_SLAVE_RELAY: int(user_input[CONF_SLAVE_RELAY]),
                    CONF_SLAVE_SENSOR: int(user_input[CONF_SLAVE_SENSOR]),
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                }
                return self.async_create_entry(
                    title=f"{user_input[CONF_HOST]}:{int(user_input[CONF_PORT])}",
                    data=data,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): _text_selector(),
                vol.Required(CONF_PORT, default=DEFAULT_PORT): _int_selector(1, 65535),
                vol.Required(CONF_SLAVE_RELAY, default=DEFAULT_SLAVE_RELAY): _int_selector(1, 247),
                vol.Required(CONF_SLAVE_SENSOR, default=DEFAULT_SLAVE_SENSOR): _int_selector(1, 247),
                vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): _int_selector(1, 300),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> "WaveshareOptionsFlow":
        return WaveshareOptionsFlow(config_entry)


# ---------------------------------------------------------------------------
# OptionsFlow — device management
# ---------------------------------------------------------------------------

class WaveshareOptionsFlow(config_entries.OptionsFlow):
    """Manage lights and covers inside the integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry
        # Work on a mutable copy
        self._options: dict[str, Any] = dict(config_entry.options)
        self._options.setdefault(CONF_DEVICES, [])
        self._editing_id: str | None = None

    # ------------------------------------------------------------------
    # Main menu
    # ------------------------------------------------------------------

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        devices: list[dict] = self._options.get(CONF_DEVICES, [])
        menu_options = ["add_device"]
        if devices:
            menu_options.append("manage_devices")
        menu_options.append("save")
        return self.async_show_menu(step_id="init", menu_options=menu_options)

    async def async_step_save(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        return self.async_create_entry(title="", data=self._options)

    # ------------------------------------------------------------------
    # Add device — step 1: type + name
    # ------------------------------------------------------------------

    async def async_step_add_device(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            self._new_type = user_input[CONF_DEVICE_TYPE]
            self._new_name = user_input[CONF_DEVICE_NAME]
            if self._new_type == DEVICE_TYPE_LIGHT:
                return await self.async_step_add_light()
            return await self.async_step_add_cover()

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_TYPE): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=DEVICE_TYPE_LIGHT, label="💡 Luce"),
                            SelectOptionDict(value=DEVICE_TYPE_COVER, label="🪟 Tapparella"),
                        ],
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Required(CONF_DEVICE_NAME): _text_selector(),
            }
        )
        return self.async_show_form(step_id="add_device", data_schema=schema)

    # ------------------------------------------------------------------
    # Add light — step 2a
    # ------------------------------------------------------------------

    async def async_step_add_light(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            device = {
                CONF_DEVICE_ID: str(uuid.uuid4()),
                CONF_DEVICE_TYPE: DEVICE_TYPE_LIGHT,
                CONF_DEVICE_NAME: self._new_name,
                CONF_RELAY_INDEX: int(user_input[CONF_RELAY_INDEX]),
                CONF_SENSOR_SLAVE: int(user_input[CONF_SENSOR_SLAVE]),
                CONF_SENSOR_REGISTER: int(user_input[CONF_SENSOR_REGISTER]),
                CONF_PULSE_MS: int(user_input[CONF_PULSE_MS]),
            }
            self._options[CONF_DEVICES].append(device)
            return await self.async_step_init()

        default_slave = self._config_entry.data.get(CONF_SLAVE_SENSOR, DEFAULT_SLAVE_SENSOR)
        schema = vol.Schema(
            {
                vol.Required(CONF_RELAY_INDEX): _int_selector(0, 31),
                vol.Required(CONF_SENSOR_SLAVE, default=default_slave): _int_selector(1, 247),
                vol.Required(CONF_SENSOR_REGISTER): _int_selector(0, 65535),
                vol.Required(CONF_PULSE_MS, default=DEFAULT_PULSE_MS): _int_selector(100, 32767 * 100),
            }
        )
        return self.async_show_form(step_id="add_light", data_schema=schema)

    # ------------------------------------------------------------------
    # Add cover — step 2b
    # ------------------------------------------------------------------

    async def async_step_add_cover(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            device = {
                CONF_DEVICE_ID: str(uuid.uuid4()),
                CONF_DEVICE_TYPE: DEVICE_TYPE_COVER,
                CONF_DEVICE_NAME: self._new_name,
                CONF_RELAY_OPEN: int(user_input[CONF_RELAY_OPEN]),
                CONF_RELAY_CLOSE: int(user_input[CONF_RELAY_CLOSE]),
                CONF_PULSE_MS: int(user_input[CONF_PULSE_MS]),
                CONF_TILT_MS: int(user_input[CONF_TILT_MS]),
            }
            self._options[CONF_DEVICES].append(device)
            return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Required(CONF_RELAY_OPEN): _int_selector(0, 31),
                vol.Required(CONF_RELAY_CLOSE): _int_selector(0, 31),
                vol.Required(CONF_PULSE_MS, default=DEFAULT_PULSE_MS): _int_selector(100, 32767 * 100),
                vol.Required(CONF_TILT_MS, default=DEFAULT_TILT_MS): _int_selector(100, 32767 * 100),
            }
        )
        return self.async_show_form(step_id="add_cover", data_schema=schema)

    # ------------------------------------------------------------------
    # Manage existing devices
    # ------------------------------------------------------------------

    async def async_step_manage_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        devices: list[dict] = self._options.get(CONF_DEVICES, [])

        if not devices:
            return await self.async_step_init()

        if user_input is not None:
            self._editing_id = user_input[CONF_DEVICE_ID]
            action = user_input.get("action")
            if action == "delete":
                self._options[CONF_DEVICES] = [
                    d for d in devices if d[CONF_DEVICE_ID] != self._editing_id
                ]
                self._editing_id = None
                return await self.async_step_init()
            # Edit — route to the right edit step
            device = next((d for d in devices if d[CONF_DEVICE_ID] == self._editing_id), None)
            if device and device[CONF_DEVICE_TYPE] == DEVICE_TYPE_LIGHT:
                return await self.async_step_edit_light()
            return await self.async_step_edit_cover()

        device_options = [
            SelectOptionDict(
                value=d[CONF_DEVICE_ID],
                label=f"{d[CONF_DEVICE_NAME]} ({'💡' if d[CONF_DEVICE_TYPE] == DEVICE_TYPE_LIGHT else '🪟'})",
            )
            for d in devices
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): SelectSelector(
                    SelectSelectorConfig(
                        options=device_options, mode=SelectSelectorMode.LIST
                    )
                ),
                vol.Required("action", default="edit"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value="edit", label="✏️ Modifica"),
                            SelectOptionDict(value="delete", label="🗑️ Elimina"),
                        ],
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="manage_devices", data_schema=schema)

    # ------------------------------------------------------------------
    # Edit light
    # ------------------------------------------------------------------

    async def async_step_edit_light(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        devices: list[dict] = self._options[CONF_DEVICES]
        device = next((d for d in devices if d[CONF_DEVICE_ID] == self._editing_id), None)
        if device is None:
            return await self.async_step_init()

        if user_input is not None:
            device.update(
                {
                    CONF_DEVICE_NAME: user_input[CONF_DEVICE_NAME],
                    CONF_RELAY_INDEX: int(user_input[CONF_RELAY_INDEX]),
                    CONF_SENSOR_SLAVE: int(user_input[CONF_SENSOR_SLAVE]),
                    CONF_SENSOR_REGISTER: int(user_input[CONF_SENSOR_REGISTER]),
                    CONF_PULSE_MS: int(user_input[CONF_PULSE_MS]),
                }
            )
            self._editing_id = None
            return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_NAME, default=device[CONF_DEVICE_NAME]): _text_selector(),
                vol.Required(CONF_RELAY_INDEX, default=device[CONF_RELAY_INDEX]): _int_selector(0, 31),
                vol.Required(CONF_SENSOR_SLAVE, default=device[CONF_SENSOR_SLAVE]): _int_selector(1, 247),
                vol.Required(CONF_SENSOR_REGISTER, default=device[CONF_SENSOR_REGISTER]): _int_selector(0, 65535),
                vol.Required(CONF_PULSE_MS, default=device[CONF_PULSE_MS]): _int_selector(100, 32767 * 100),
            }
        )
        return self.async_show_form(step_id="edit_light", data_schema=schema)

    # ------------------------------------------------------------------
    # Edit cover
    # ------------------------------------------------------------------

    async def async_step_edit_cover(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        devices: list[dict] = self._options[CONF_DEVICES]
        device = next((d for d in devices if d[CONF_DEVICE_ID] == self._editing_id), None)
        if device is None:
            return await self.async_step_init()

        if user_input is not None:
            device.update(
                {
                    CONF_DEVICE_NAME: user_input[CONF_DEVICE_NAME],
                    CONF_RELAY_OPEN: int(user_input[CONF_RELAY_OPEN]),
                    CONF_RELAY_CLOSE: int(user_input[CONF_RELAY_CLOSE]),
                    CONF_PULSE_MS: int(user_input[CONF_PULSE_MS]),
                    CONF_TILT_MS: int(user_input[CONF_TILT_MS]),
                }
            )
            self._editing_id = None
            return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_NAME, default=device[CONF_DEVICE_NAME]): _text_selector(),
                vol.Required(CONF_RELAY_OPEN, default=device[CONF_RELAY_OPEN]): _int_selector(0, 31),
                vol.Required(CONF_RELAY_CLOSE, default=device[CONF_RELAY_CLOSE]): _int_selector(0, 31),
                vol.Required(CONF_PULSE_MS, default=device[CONF_PULSE_MS]): _int_selector(100, 32767 * 100),
                vol.Required(CONF_TILT_MS, default=device[CONF_TILT_MS]): _int_selector(100, 32767 * 100),
            }
        )
        return self.async_show_form(step_id="edit_cover", data_schema=schema)
