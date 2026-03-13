# :battery: KONNWEI BLE Battery Monitor

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![HA version](https://img.shields.io/badge/Home%20Assistant-2024.1.0%2B-blue.svg)](https://www.home-assistant.io/)

A custom [Home Assistant](https://www.home-assistant.io/) integration for **KONNWEI BLE battery monitors**. It connects to the device over Bluetooth Low Energy and exposes live voltage, cold cranking amps, internal resistance, health, charge, and status as HA sensors.

The BLE protocol was reverse-engineered from the official Android app. No cloud account or internet connection required -- everything runs locally.

## Supported Devices

| Device | Voltage | Firmware | Manufacturer |
|---|---|---|---|
| KONNWEI BK200 | 24 V | 1.0.8+ | Shenzhen Jiawei Hengxin Technology (KONNWEI) |

Other KONNWEI BLE monitors that advertise a local name starting with `KONNWEI` and use the same FFF0/FFF1/FFF2 service may also work but have not been tested.

## Sensors

| Sensor | Unit | Update Source | Notes |
|---|---|---|---|
| Voltage | V | Live waveform (averaged) | ~3 samples averaged per poll cycle |
| Cold Cranking Amps (CCA) | A | Quick test | |
| Internal Resistance | mOhm | Quick test | |
| Battery Health | % | Quick test | |
| Battery Charge | % | Quick test | |
| Battery Status | enum | Quick test | `good`, `fair`, `low`, `error`, `unknown` |

## Installation

### HACS (recommended)

1. Open **HACS** in Home Assistant.
2. Click the three-dot menu in the top right and select **Custom repositories**.
3. Add the repository URL:
   ```
   Maheidem/konnwei-ble-ha
   ```
   Category: **Integration**
4. Click **Add**.
5. Search for **KONNWEI BLE Battery Monitor** in HACS and click **Download**.
6. Restart Home Assistant.

### Manual

1. Copy the `custom_components/konnwei_ble` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

### Automatic discovery

If your Home Assistant host has a Bluetooth adapter and the KONNWEI monitor is powered on and in range, HA will discover it automatically. You will see a notification:

> Found KONNWEI battery monitor: KONNWEI-XXXX. Do you want to add it?

Click **Configure** and confirm to add the device.

### Manual setup

1. Go to **Settings > Devices & Services > Add Integration**.
2. Search for **KONNWEI BLE Battery Monitor**.
3. Select your device from the list of discovered KONNWEI monitors.

### Options

After setup you can adjust the **update interval** (how often the integration polls the device):

- Default: **60 seconds**
- Range: 30 -- 300 seconds

Go to the integration's entry in **Settings > Devices & Services**, click **Configure**, and change the interval.

## How It Works

Each poll cycle the integration performs a connect-poll-disconnect sequence:

1. **Connect** to the KONNWEI device via BLE and subscribe to notifications on the FFF1 characteristic.
2. **Init + Config** -- sends the initialization command (`0x0100`) and reads the device configuration (`0x0204`) to learn the maximum voltage range.
3. **Quick test** (`0x0602`) -- retrieves battery stats: CCA, internal resistance, health percentage, charge percentage, and status code.
4. **Waveform streaming** (`0x0501`) -- starts live voltage sampling at 1 sample/second. The integration collects samples for 3 seconds, then sends the stop command (`0x0502`). Raw LE uint16 values are parsed and averaged to produce a stable voltage reading.
5. **Disconnect** -- releases the BLE connection so the device remains available for other tools.

The protocol uses plain binary packets (no encryption) with CRC-16/X25 validation. Communication happens over the BLE GATT service `FFF0` using characteristic `FFF1` (notify) and `FFF2` (write).

## Troubleshooting

**Device not discovered**

- Make sure the KONNWEI monitor is powered on and connected to a battery.
- Confirm your Home Assistant host has a working Bluetooth adapter. Check **Settings > Devices & Services > Bluetooth** for adapter status.
- Bring the monitor within a few meters of the HA host for initial setup.

**"No KONNWEI devices found" during manual setup**

- The device must be advertising via BLE. If another app (e.g., the KONNWEI Android app) is currently connected to it, disconnect first -- BLE monitors typically allow only one active connection.

**Sensors show "unavailable"**

- The device may be out of range or powered off. The integration will retry on the next poll cycle.
- Check the Home Assistant logs for `konnwei_ble` entries:
  ```
  Logger: custom_components.konnwei_ble.coordinator
  ```
- If you see `Failed to connect` errors, the device may be busy. Increase the update interval to give it more time between connections.

**Voltage reading seems stale or incorrect**

- The integration uses waveform mode for live voltage. If waveform collection fails (e.g., timeout), it falls back to the voltage from the quick test command, which may be less current.
- Ensure the battery terminals on the KONNWEI monitor are clean and firmly attached.

**Connection drops or timeouts**

- BLE range is limited (typically 5--10 m). Reduce the distance between the HA host and the monitor.
- Other BLE devices on the same adapter can cause congestion. If you have many BLE devices, consider a dedicated USB Bluetooth adapter for this integration.
- The default connect timeout is 15 seconds. If your environment is noisy, this should be sufficient for retries via `bleak-retry-connector`.

## Requirements

- Home Assistant **2024.1.0** or later
- A Bluetooth adapter accessible to Home Assistant
- Python package: `bleak-retry-connector >= 3.5.0` (installed automatically)

## License

This project is provided as-is for personal use. The BLE protocol implementation was reverse-engineered independently and is not affiliated with or endorsed by KONNWEI / Shenzhen Jiawei Hengxin Technology.
