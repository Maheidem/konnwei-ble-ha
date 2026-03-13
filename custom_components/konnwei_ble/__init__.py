"""KONNWEI BLE Battery Monitor integration for Home Assistant."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant

from .const import DEFAULT_UPDATE_INTERVAL, DOMAIN
from .coordinator import KonnweiCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

CONF_UPDATE_INTERVAL = "update_interval"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up KONNWEI BLE from a config entry."""
    address: str = entry.data[CONF_ADDRESS]
    update_interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

    coordinator = KonnweiCoordinator(hass, address, update_interval)

    # Don't block setup if device is out of range — sensors start as "unavailable"
    # and populate once the device is reachable on the next poll cycle.
    await coordinator.async_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — adjust poll interval."""
    coordinator: KonnweiCoordinator = hass.data[DOMAIN][entry.entry_id]
    new_interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    coordinator.update_interval = timedelta(seconds=new_interval)
    _LOGGER.debug("KONNWEI update interval changed to %ds", new_interval)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
