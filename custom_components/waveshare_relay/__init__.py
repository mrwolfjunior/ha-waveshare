"""Home Assistant integration entry point for Waveshare Relay.

Lifecycle:
  async_setup_entry   → connects coordinator, forwards to platforms
  async_unload_entry  → disconnects, unloads platforms
  Options listener    → triggers reload on device list changes
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import CONF_HOST, CONF_PORT, DOMAIN
from .coordinator import WaveshareCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.COVER, Platform.BINARY_SENSOR]

# Stable hub identifier = "hub_<entry_id>"
def _hub_identifier(entry: ConfigEntry) -> str:
    return f"hub_{entry.entry_id}"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Waveshare Relay from a config entry."""
    coordinator = WaveshareCoordinator(hass, entry)

    # Initial data fetch (connect + first poll)
    try:
        await coordinator.client.connect()
    except Exception as exc:  # noqa: BLE001
        _LOGGER.error("Cannot connect to Waveshare bridge: %s", exc)
        # Don't abort — coordinator will retry on next poll
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Register the bridge as a hub device so via_device in child entities resolves correctly
    registry = dr.async_get(hass)
    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, _hub_identifier(entry))},
        name=f"Waveshare Bridge ({entry.data[CONF_HOST]}:{entry.data[CONF_PORT]})",
        manufacturer="Waveshare",
        model="Ethernet/RS485 Modbus Bridge",
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload integration when options (device list) change
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entry when options are updated (devices added/removed/edited)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: WaveshareCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.client.disconnect()
    return unload_ok
