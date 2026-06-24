"""Cover platform for Waveshare Relay.

Each cover (blind/shutter) uses two relays:
  - relay_open:  triggers open movement (hardware pulse)
  - relay_close: triggers close movement (hardware pulse)

Position is reported as a fixed 50 (unknown) because physical remote
controls can operate the blinds independently of HA, making any
position estimate unreliable.

Tilt action sends a longer pulse to fully open/close slats.
"""
from __future__ import annotations

import logging

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
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
    CONF_RELAY_CLOSE,
    CONF_RELAY_OPEN,
    CONF_TILT_MS,
    DEFAULT_PULSE_MS,
    DEFAULT_TILT_MS,
    DEVICE_TYPE_COVER,
    DOMAIN,
)
from .coordinator import WaveshareCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up cover entities from options device list."""
    coordinator: WaveshareCoordinator = hass.data[DOMAIN][entry.entry_id]
    devices = entry.options.get(CONF_DEVICES, [])

    entities = [
        WavshareCover(coordinator, entry, dev)
        for dev in devices
        if dev.get(CONF_DEVICE_TYPE) == DEVICE_TYPE_COVER
    ]
    async_add_entities(entities)


class WavshareCover(CoordinatorEntity[WaveshareCoordinator], CoverEntity):
    """Represents a motorised blind/shutter controlled by two relay pulses."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = CoverDeviceClass.BLIND

    # Position reported as fixed 50 so HA always shows open/close arrows.
    # Real position is unknown (physical remotes can change it).
    _attr_current_cover_position = 50
    _attr_current_cover_tilt_position = 50
    _attr_is_closed = None  # Unknown

    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_TILT_POSITION
    )

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
        self._relay_open: int = device_cfg[CONF_RELAY_OPEN]
        self._relay_close: int = device_cfg[CONF_RELAY_CLOSE]
        self._pulse_ms: int = device_cfg.get(CONF_PULSE_MS, DEFAULT_PULSE_MS)
        self._tilt_ms: int = device_cfg.get(CONF_TILT_MS, DEFAULT_TILT_MS)

        self._attr_unique_id = f"{entry.entry_id}_{self._device_id}"
        self._attr_name = device_cfg[CONF_DEVICE_NAME]

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=self._cfg[CONF_DEVICE_NAME],
            manufacturer="Waveshare",
            model="Relay 32CH (Cover)",
            via_device=(DOMAIN, f"hub_{self._entry.entry_id}"),
        )

    # ------------------------------------------------------------------
    # Cover commands
    # ------------------------------------------------------------------

    async def async_open_cover(self, **kwargs: object) -> None:
        """Send open pulse."""
        _LOGGER.debug("Opening cover %s (relay %d, %dms)", self.name, self._relay_open, self._pulse_ms)
        await self.coordinator.async_flash_on(self._relay_open, self._pulse_ms)

    async def async_close_cover(self, **kwargs: object) -> None:
        """Send close pulse."""
        _LOGGER.debug("Closing cover %s (relay %d, %dms)", self.name, self._relay_close, self._pulse_ms)
        await self.coordinator.async_flash_on(self._relay_close, self._pulse_ms)

    async def async_stop_cover(self, **kwargs: object) -> None:
        """Stop is not supported by the relay hardware — no-op."""
        _LOGGER.debug("Stop requested for %s — relay hardware has no stop command", self.name)

    async def async_set_cover_tilt_position(self, **kwargs: object) -> None:
        """Open or close slats with a long pulse based on tilt value.

        tilt_position == 0   → fully close slats (long close pulse)
        tilt_position == 100 → fully open slats  (long open pulse)
        Any other value is ignored (no intermediate tilt supported).
        """
        tilt: int = kwargs.get("tilt_position", 50)
        if tilt == 0:
            _LOGGER.debug("Tilting closed %s (%dms)", self.name, self._tilt_ms)
            await self.coordinator.async_flash_on(self._relay_close, self._tilt_ms)
        elif tilt == 100:
            _LOGGER.debug("Tilting open %s (%dms)", self.name, self._tilt_ms)
            await self.coordinator.async_flash_on(self._relay_open, self._tilt_ms)
        else:
            _LOGGER.debug(
                "Intermediate tilt %d requested for %s — only 0/100 supported",
                tilt,
                self.name,
            )
