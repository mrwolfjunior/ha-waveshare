"""DataUpdateCoordinator for Waveshare Relay integration.

Polls both the relay board (slave 1, FC01 coils) and the digital input
board (slave 2, FC03 holding registers) on a configurable interval.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_DEVICES,
    CONF_DEVICE_TYPE,
    CONF_SCAN_INTERVAL,
    CONF_SENSOR_REGISTER,
    CONF_SENSOR_SLAVE,
    CONF_SLAVE_RELAY,
    CONF_SLAVE_SENSOR,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE_RELAY,
    DEFAULT_SLAVE_SENSOR,
    DEVICE_TYPE_LIGHT,
    DOMAIN,
)
from .modbus_client import WaveshareModbusClient

_LOGGER = logging.getLogger(__name__)


class WaveshareCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that owns the TCP connection and polls both boards."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self._entry = entry
        self._slave_relay: int = entry.data.get(CONF_SLAVE_RELAY, DEFAULT_SLAVE_RELAY)
        self._slave_sensor: int = entry.data.get(CONF_SLAVE_SENSOR, DEFAULT_SLAVE_SENSOR)

        self.client = WaveshareModbusClient(
            entry.data["host"],
            entry.data["port"],
        )

    # ------------------------------------------------------------------
    # Poll
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch coils from slave_relay and holding registers from slave_sensor."""
        devices: list[dict] = self._entry.options.get(CONF_DEVICES, [])

        # Gather which (slave, register) pairs we need
        regs_by_slave: dict[int, set[int]] = defaultdict(set)
        for dev in devices:
            if dev.get(CONF_DEVICE_TYPE) == DEVICE_TYPE_LIGHT:
                slave = dev.get(CONF_SENSOR_SLAVE, self._slave_sensor)
                reg = dev.get(CONF_SENSOR_REGISTER)
                if reg is not None:
                    regs_by_slave[slave].add(reg)

        result: dict[str, Any] = {"coils": [], "sensors": {}}

        # --- FC01: read all 32 relay coils ---
        coils = await self.client.read_coils(self._slave_relay, 0, 32)
        if coils is not None:
            result["coils"] = coils
        else:
            _LOGGER.warning("Failed to read relay coils from slave %d", self._slave_relay)

        # --- FC03: read holding registers per slave ---
        for slave, reg_set in regs_by_slave.items():
            sorted_regs = sorted(reg_set)
            min_reg = sorted_regs[0]
            max_reg = sorted_regs[-1]
            count = max_reg - min_reg + 1

            registers = await self.client.read_holding_registers(slave, min_reg, count)
            if registers is not None:
                for i, addr in enumerate(range(min_reg, min_reg + count)):
                    if addr in reg_set and i < len(registers):
                        # Non-zero value → input is active (ON)
                        result["sensors"][(slave, addr)] = registers[i] != 0
            else:
                _LOGGER.warning(
                    "Failed to read holding registers from slave %d (addr %d+%d)",
                    slave, min_reg, count,
                )

        return result

    # ------------------------------------------------------------------
    # Convenience accessors used by entities
    # ------------------------------------------------------------------

    def get_relay_state(self, relay_index: int) -> bool:
        """Return current coil state for a relay (True = ON)."""
        coils: list[bool] = (self.data or {}).get("coils", [])
        if relay_index < len(coils):
            return coils[relay_index]
        return False

    def get_sensor_state(self, slave: int, register: int) -> bool:
        """Return current digital input state (True = ON)."""
        sensors: dict = (self.data or {}).get("sensors", {})
        return sensors.get((slave, register), False)

    # ------------------------------------------------------------------
    # Relay command helpers (delegated to client)
    # ------------------------------------------------------------------

    async def async_flash_on(self, relay_index: int, pulse_ms: int) -> bool:
        """Send Flash ON command on slave_relay."""
        return await self.client.flash_on(self._slave_relay, relay_index, pulse_ms)

    async def async_flash_on_slave(
        self, slave: int, relay_index: int, pulse_ms: int
    ) -> bool:
        """Send Flash ON on an explicit slave (future use)."""
        return await self.client.flash_on(slave, relay_index, pulse_ms)
