"""Data update coordinator for KONNWEI BLE Battery Monitor."""

from __future__ import annotations

import asyncio
import logging
import struct
from datetime import timedelta
from typing import Any

from bleak import BleakClient, BleakError

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONNECT_TIMEOUT,
    DEFAULT_UPDATE_INTERVAL,
    RESPONSE_TIMEOUT,
    UUID_CHAR_NOTIFY,
    UUID_CHAR_WRITE,
    WAVEFORM_COLLECT_TIME,
    WAVEFORM_INTERVAL,
)
from .protocol import (
    CMD_DEVICE_CONFIG,
    CMD_INIT,
    CMD_QUICK_TEST,
    CMD_WAVEFORM_START,
    CMD_WAVEFORM_STOP,
    build_packet,
    extract_packets,
    parse_response,
    parse_waveform_samples,
)

_LOGGER = logging.getLogger(__name__)


class KonnweiCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that polls the KONNWEI BLE device each cycle.

    Each poll cycle:
    1. Connect → init → config (get max_voltage) → quick test (battery stats)
    2. Start waveform streaming → collect live voltage samples → stop streaming
    3. Average samples for live voltage, merge with battery stats, disconnect
    """

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        update_interval: int = DEFAULT_UPDATE_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"KONNWEI {address}",
            update_interval=timedelta(seconds=update_interval),
        )
        self.address = address
        self._max_voltage = 3600  # default, updated from 4204 config response

    async def _async_update_data(self) -> dict[str, Any]:
        """Connect, collect live voltage via waveform + battery stats, disconnect."""
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device is None:
            raise UpdateFailed(
                f"KONNWEI device {self.address} not found via Bluetooth"
            )

        result: dict[str, Any] = {}
        buffer = bytearray()
        waveform_samples: list[float] = []
        waveform_mode = False
        setup_event = asyncio.Event()
        stop_event = asyncio.Event()

        def on_notify(_sender: Any, data: bytearray) -> None:
            nonlocal buffer, result, waveform_mode

            if waveform_mode:
                # During waveform streaming, device sends raw LE uint16 samples.
                # But 4502 stop ACK arrives as a framed packet (2424...0d0a)
                # mixed with trailing samples — scan for 2424 header.
                hex_data = data.hex()
                header_pos = hex_data.find("2424")

                if header_pos >= 0:
                    # Samples before the header
                    if header_pos > 0:
                        sample_bytes = bytes.fromhex(hex_data[:header_pos])
                        waveform_samples.extend(
                            parse_waveform_samples(sample_bytes, self._max_voltage)
                        )
                    # Framed packet after the header
                    remaining = bytes.fromhex(hex_data[header_pos:])
                    buffer.extend(remaining)
                    packets, leftover = extract_packets(buffer)
                    buffer = leftover
                    for pkt in packets:
                        parsed = parse_response(pkt)
                        if parsed and parsed.get("streaming_stopped"):
                            waveform_mode = False
                            stop_event.set()
                else:
                    # Pure waveform samples
                    waveform_samples.extend(
                        parse_waveform_samples(bytes(data), self._max_voltage)
                    )
                return

            # Framed packet mode — accumulate and extract complete packets
            buffer.extend(data)
            packets, remaining = extract_packets(buffer)
            buffer = remaining

            for pkt in packets:
                parsed = parse_response(pkt)
                if parsed is None:
                    continue

                if parsed.get("init_ok"):
                    _LOGGER.debug("KONNWEI init acknowledged")
                elif "voltage" in parsed:
                    # 4602 quick test — battery stats (CCA, health, charge, resistance)
                    result.update(parsed)
                    setup_event.set()
                elif "max_voltage" in parsed:
                    # 4204 device config
                    self._max_voltage = parsed["max_voltage"]
                    _LOGGER.debug("KONNWEI max_voltage=%d", self._max_voltage)
                elif parsed.get("streaming"):
                    # 4501 waveform ACK — switch to raw sample mode
                    waveform_mode = True
                    _LOGGER.debug("KONNWEI waveform streaming started")
                elif parsed.get("streaming_stopped"):
                    stop_event.set()

        try:
            client = BleakClient(ble_device, timeout=CONNECT_TIMEOUT)
            await client.connect()
        except (BleakError, TimeoutError, OSError) as err:
            raise UpdateFailed(f"Failed to connect to {self.address}: {err}") from err

        try:
            await client.start_notify(UUID_CHAR_NOTIFY, on_notify)

            # Phase 1: Setup — init + config + quick test (battery stats)
            await client.write_gatt_char(
                UUID_CHAR_WRITE, build_packet(CMD_INIT), response=False
            )
            await asyncio.sleep(0.3)

            await client.write_gatt_char(
                UUID_CHAR_WRITE, build_packet(CMD_DEVICE_CONFIG), response=False
            )
            await asyncio.sleep(0.3)

            await client.write_gatt_char(
                UUID_CHAR_WRITE, build_packet(CMD_QUICK_TEST), response=False
            )

            try:
                await asyncio.wait_for(setup_event.wait(), timeout=RESPONSE_TIMEOUT)
            except TimeoutError:
                _LOGGER.debug("Setup responses timed out, continuing with waveform")

            # Phase 2: Waveform — live voltage sampling
            interval_data = struct.pack("<H", WAVEFORM_INTERVAL)
            await client.write_gatt_char(
                UUID_CHAR_WRITE,
                build_packet(CMD_WAVEFORM_START, interval_data),
                response=False,
            )

            await asyncio.sleep(WAVEFORM_COLLECT_TIME)

            # Phase 3: Stop waveform
            await client.write_gatt_char(
                UUID_CHAR_WRITE, build_packet(CMD_WAVEFORM_STOP), response=False
            )

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=RESPONSE_TIMEOUT)
            except TimeoutError:
                _LOGGER.debug("Waveform stop ACK not received")

            await client.stop_notify(UUID_CHAR_NOTIFY)

        except BleakError as err:
            raise UpdateFailed(
                f"Communication error with {self.address}: {err}"
            ) from err
        finally:
            await client.disconnect()

        # Live voltage from waveform samples overrides stale 0602 voltage
        if waveform_samples:
            result["voltage"] = round(
                sum(waveform_samples) / len(waveform_samples), 2
            )
            _LOGGER.debug(
                "KONNWEI waveform: %d samples, avg %.2fV",
                len(waveform_samples),
                result["voltage"],
            )

        # Fallback: if waveform failed but 0602 had voltage, we still have data
        # If nothing at all, try 0B0B as last resort on next cycle
        if not result:
            raise UpdateFailed("No data received from KONNWEI device")

        return result
