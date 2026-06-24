"""Light platform for Waveshare Relay.

Each light maps to:
  - One relay on slave_relay (command via Flash ON)
  - One holding register on slave_sensor (state read)

Turn on/off logic: check current state first, pulse only if needed.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_DEVICES,
    CONF_PULSE_MS,
    CONF_RELAY_INDEX,
    CONF_SENSOR_REGISTER,
    CONF_SENSOR_SLAVE,
    CONF_SLAVE_SENSOR,
    DEFAULT_PULSE_MS,
    DEFAULT_SLAVE_SENSOR,
    DEVICE_TYPE_LIGHT,
    DOMAIN,
)
from .coordinator import WaveshareCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up light entities from options device list."""
    coordinator: WaveshareCoordinator = hass.data[DOMAIN][entry.entry_id]
    devices = entry.options.get(CONF_DEVICES, [])

    entities = [
        WaveshareLight(coordinator, entry, dev)
        for dev in devices
        if dev.get(CONF_DEVICE_TYPE) == DEVICE_TYPE_LIGHT
    ]
    async_add_entities(entities)


class WaveshareLight(CoordinatorEntity[WaveshareCoordinator], LightEntity):
    """Represents a light controlled by a single relay with hardware pulse."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    # Required by HA: declare that this is a simple on/off light (no color/brightness)
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(
        self,
        coordinator: WaveshareCoordinator,
        entry: ConfigEntry,
        device_cfg: dict,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._cfg = device_cfg
        self._device_id: str = device_cfg[CONF_DEVICE_ID]
        self._relay_index: int = device_cfg[CONF_RELAY_INDEX]
        self._sensor_slave: int = device_cfg.get(
            CONF_SENSOR_SLAVE,
            entry.data.get(CONF_SLAVE_SENSOR, DEFAULT_SLAVE_SENSOR),
        )
        self._sensor_register: int = device_cfg[CONF_SENSOR_REGISTER]
        self._pulse_ms: int = device_cfg.get(CONF_PULSE_MS, DEFAULT_PULSE_MS)

        self._attr_unique_id = f"{entry.entry_id}_{self._device_id}"
        self._attr_name = device_cfg[CONF_DEVICE_NAME]

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=self._cfg[CONF_DEVICE_NAME],
            manufacturer="Waveshare",
            model="Relay 32CH (Light)",
            via_device=(DOMAIN, f"hub_{self._entry.entry_id}"),
        )

    @property
    def is_on(self) -> bool:
        """State from the digital input board (N4DIH32)."""
        return self.coordinator.get_sensor_state(
            self._sensor_slave, self._sensor_register
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on: pulse relay only if light is currently OFF."""
        if not self.is_on:
            await self.coordinator.async_flash_on(self._relay_index, self._pulse_ms)
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.debug("%s already ON — skipping pulse", self.name)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off: pulse relay only if light is currently ON."""
        if self.is_on:
            await self.coordinator.async_flash_on(self._relay_index, self._pulse_ms)
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.debug("%s already OFF — skipping pulse", self.name)
