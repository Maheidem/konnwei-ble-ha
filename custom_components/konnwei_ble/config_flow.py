"""Config flow for KONNWEI BLE Battery Monitor."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOCAL_NAME_PREFIX,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

CONF_UPDATE_INTERVAL = "update_interval"


class KonnweiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle config flow for KONNWEI BLE Battery Monitor."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle a Bluetooth discovery."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {
            "name": discovery_info.name or "KONNWEI",
        }
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm a Bluetooth discovery."""
        assert self._discovery_info is not None

        if user_input is not None:
            return self.async_create_entry(
                title=self._discovery_info.name or "KONNWEI Battery Monitor",
                data={CONF_ADDRESS: self._discovery_info.address},
            )

        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": self._discovery_info.name or "KONNWEI",
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle user-initiated setup (manual selection)."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()

            # Find the name for this address
            all_discoveries = async_discovered_service_info(self.hass, connectable=True)
            name = "KONNWEI Battery Monitor"
            for info in all_discoveries:
                if info.address == address:
                    name = info.name or name
                    break

            return self.async_create_entry(title=name, data={CONF_ADDRESS: address})

        # Build list of discovered KONNWEI devices
        all_discoveries = async_discovered_service_info(self.hass, connectable=True)
        konnwei_devices: dict[str, str] = {}

        for info in all_discoveries:
            if info.name and info.name.upper().startswith(LOCAL_NAME_PREFIX):
                configured = {
                    entry.unique_id
                    for entry in self.hass.config_entries.async_entries(DOMAIN)
                }
                if info.address not in configured:
                    konnwei_devices[info.address] = (
                        f"{info.name} ({info.address})"
                    )

        if not konnwei_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_ADDRESS): vol.In(konnwei_devices)}
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow handler."""
        return KonnweiOptionsFlow(config_entry)


class KonnweiOptionsFlow(OptionsFlow):
    """Handle options for KONNWEI BLE Battery Monitor."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UPDATE_INTERVAL, default=current_interval
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL),
                    ),
                }
            ),
        )
