"""Binary sensor platform for Waveshare Relay.

Reads digital input state from the N4DIH32 board (FC03 holding registers).
One binary sensor is created automatically for each light device so that
the state is also accessible as a standalone entity (e.g. for automations).
"""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
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
    CONF_SENSOR_REGISTER,
    CONF_SENSOR_SLAVE,
    CONF_SLAVE_SENSOR,
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
    """Create one binary sensor per light device (mirrors the sensor register)."""
    coordinator: WaveshareCoordinator = hass.data[DOMAIN][entry.entry_id]
    devices = entry.options.get(CONF_DEVICES, [])

    entities = [
        WaveshareBinarySensor(coordinator, entry, dev)
        for dev in devices
        if dev.get(CONF_DEVICE_TYPE) == DEVICE_TYPE_LIGHT
    ]
    async_add_entities(entities)


class WaveshareBinarySensor(CoordinatorEntity[WaveshareCoordinator], BinarySensorEntity):
    """Binary sensor that mirrors a digital input register (N4DIH32)."""

    _attr_has_entity_name = True
    _attr_should_poll = False

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
        self._sensor_slave: int = device_cfg.get(
            CONF_SENSOR_SLAVE,
            entry.data.get(CONF_SLAVE_SENSOR, DEFAULT_SLAVE_SENSOR),
        )
        self._sensor_register: int = device_cfg[CONF_SENSOR_REGISTER]

        # Unique ID distinct from the light entity (suffix _state)
        self._attr_unique_id = f"{entry.entry_id}_{self._device_id}_state"
        self._attr_name = f"{device_cfg[CONF_DEVICE_NAME]} Stato"

    @property
    def device_info(self) -> DeviceInfo:
        # Attach to the same device as the light (same identifiers)
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
        )

    @property
    def is_on(self) -> bool:
        return self.coordinator.get_sensor_state(
            self._sensor_slave, self._sensor_register
        )
