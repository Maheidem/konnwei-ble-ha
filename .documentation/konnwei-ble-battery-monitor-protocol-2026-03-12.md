---
title: KONNWEI BLE Battery Monitor - Reverse-Engineered Protocol
date: 2026-03-12
status: WORKING
device: KONNWEI BK200 (24V BLE battery monitor, firmware 1.0.8)
---

# KONNWEI BLE Battery Monitor Protocol

## Device Info

| Field | Value |
|---|---|
| Name | KONNWEI |
| MAC | B1:00:60:00:1D:87 |
| BLE Chip | CEVA (RivieraWaves) BT 4.0 |
| Service | 0000fff0 |
| Notify Char | 0000fff1 (property: notify) |
| Write Char | 0000fff2 (property: write-without-response) |
| App | BKmonitor / Kbattery (com.jiawei.batteryonline / com.jiawei.batterytool3) |
| Manufacturer | Shenzhen Jiawei Hengxin Technology (KONNWEI) |

**NOT a Leagend BM2/BM6/BM7** — different chip, different protocol, no AES encryption.

## Packet Format

Both requests and responses:
```
[header 2B] [length_LE 2B] [command 2B] [data NB] [CRC_LE 2B] [terminator 2B]
```

- **Header**: `0x40 0x40` (requests) / `0x24 0x24` (responses from device)
- **Length**: total packet size in bytes, uint16 little-endian
- **Command**: 2 bytes. Responses = request_cmd with first byte + 0x40
- **CRC**: CRC-16/X25 (FCS-16), uint16 little-endian
- **Terminator**: `0x0D 0x0A`

## CRC Algorithm

Standard CRC-16/X25 (FCS-16):
```python
FCS_START = 0xFFFF
for byte in packet_before_crc:
    fcs = (fcs >> 8) ^ FCSTAB[(byte ^ fcs) & 0xFF]
result = FCS_START ^ fcs
```

## Commands

### Standard Commands

| Request Cmd | Response Cmd | Purpose | Data |
|---|---|---|---|
| `0100` | `4100` | Init / handshake | (none) |
| `0602` | `4602` | Quick test — returns last test result (SOH, CCA, V, R, SOC) | (none) |
| `0B0B` | `4B0B` | Voltage monitor (single background reading) | (none) |
| `0B01` | `4B01` | Get last stored data | 4-byte unix timestamp (LE) |
| `0B08` | `4B08` | Get collection open/close | (none) |
| `0201` | `4201` | Get device version | (none) |
| `0203` | `4203` | Get device info (variant 2) | (none) |
| `0204` | `4204` | Get device config (maxVoltage, battery system) | (none) |
| `0301` | `4301` | Get device info (name, IAP version) | (hardcoded packet) |
| `0601` | `4601` | Quick test start/ready check | (none) |
| `0c02` | `4C02` | Change BLE name | BLE name string |
| `ATRVER` | (text) | Version query (raw ASCII, no framing) | (none) |

### Waveform Commands (high-frequency live voltage)

| Request Cmd | Response Cmd | Purpose | Data |
|---|---|---|---|
| `0501` | `4501` | Start waveform collection | interval LE uint16 (default: 20 = 20ms) |
| `0502` | `4502` | Stop waveform collection | (none) |

Source: `WaveformTestDeleteFragment.kt` in APK `com.jiawei.batterytool3`

## Response Data Layout: 4602 (Quick Test)

This is the most useful command — returns voltage + full battery analysis.

Response hex string positions:
```
Position   Field              Parsing
[0:4]      Header (2424)      -
[4:8]      Length (LE uint16)  -
[8:12]     Command (4602)      -
[12:16]    Voltage            LE uint16 / 100.0 = volts
[16:20]    CCA                LE uint16 = amps
[20:24]    Internal Resistance LE uint16 / 100.0 = milliohms
[24:26]    Health %           uint8 (0-100)
[26:28]    Charge %           uint8 (0-100)
[28:30]    Battery Status     uint8 (255 = error)
[-8:-4]    CRC                LE uint16
[-4:]      Terminator         0d0a
```

### Example

Response: `242413004602 c70a 0601 6411 64 64 01 baac 0d0a`

| Field | Hex | LE Parse | Result |
|---|---|---|---|
| Voltage | `c70a` | 0x0AC7 = 2759 | **27.59 V** |
| CCA | `0601` | 0x0106 = 262 | **262 A** |
| Resistance | `6411` | 0x1164 = 4452 | **44.52 mΩ** |
| Health | `64` | 100 | **100%** |
| Charge | `64` | 100 | **100%** |
| Status | `01` | 1 | **OK** |

## Response Data Layout: 4B0B (Voltage Monitor)

```
[12:16]    Voltage/status     LE uint16
[16:18]    Battery connect    uint8 (00=disconnected)
[18:20]    Charging status    uint8
```

## Response Data Layout: 4501 (Waveform Start ACK)

```
[8:12]     Command (4501)
[12:14]    Status             uint8:
                                00 = success, streaming started
                                02 = battery disconnected / error
                                other = failure
```

When status=00, the device begins pushing **raw voltage samples** directly on
the notify characteristic (FFF1). These are NOT framed in 4040/2424 packets —
they arrive as **bare LE uint16 values** (2 bytes each, or packed multiples of
2/4/6/8 bytes per notification). Parse each 2-byte pair as:

```python
voltage = struct.unpack_from("<H", data, offset)[0] / 100.0  # volts
```

The app validates `getDaduan(sample) <= maxVoltage` to discard corrupted data.
Samples arrive at the interval requested in the `0501` command (default 20ms =
~50 samples/second).

## Response Data Layout: 4204 (Device Config)

```
[14:18]    maxVoltage         LE uint16 (used to filter bad waveform samples)
[22:24]    battery system     uint8 (determines voltage scale: 12V/24V system)
```

CRC validated the same way as other framed packets.

## Response Data Layout: 4502 (Waveform Stop ACK)

No data fields — just confirms streaming has stopped. Parse `charList` to
extract final `valueList` if needed.

## Waveform Flow

1. Connect + enable notifications on FFF1
2. Write `0100` init to FFF2 → wait for `4100` ACK
3. Write `0204` to FFF2 → receive `4204` with maxVoltage config
4. Write `0501` with interval data (LE uint16, e.g. `e803` = 1000ms) to FFF2
5. Receive `4501` with status byte — if `00`, streaming starts
6. Device pushes raw LE uint16 voltage samples on FFF1 (no framing)
7. Write `0502` to FFF2 → receive `4502`, streaming stops

**Confirmed working** (2026-03-13): Continuous streaming mode works — device streams
indefinitely until `0502` is sent. Intervals tested: 20ms (~50 samples/s) and 1000ms (1/s).
The app uses start/stop cycles for its 10-second recording feature, but continuous mode
is valid for live monitoring.

**Note**: The device may auto-respond with a stale `4602` quick test result immediately
after `0100` init, even without sending `0602`. This is harmless — just ignore it or use
it for initial stats (CCA, health, charge, resistance).

## Standard Test Flow (last test result)

1. Scan BLE for device named "KONNWEI"
2. Connect to FFF0 service
3. Enable notifications on FFF1
4. Write `0100` init command to FFF2 (write-without-response)
5. Write `0602` quick test command to FFF2
6. Parse `4602` response from FFF1 notifications
7. Voltage = LE_uint16(response[12:16]) / 100.0

**Note**: `0602` returns the result of the LAST test performed on the device.
It does NOT trigger a new test or read live voltage.

## Key Files (from APK decompilation)

APK: `com.jiawei.batterytool3` (Kbattery v3)

- `com/clj/fastble/utils/HexUtil.java` — sendWriteData(), CRC computation
- `com/clj/fastble/utils/CrcUtil.java` — CRC-16/X25 lookup table
- `com/jiawei/batterytool3/fragment/SendDataUtils.java` — BLE write helper
- `com/jiawei/batterytool3/fragment/DaXiaoDuanConvertUtils.java` — LE byte parsing (getDaduan)
- `org/devio/as/proj/biz_home/home/WaveformTestDeleteFragment.kt` — waveform mode (0501/0502 commands, raw voltage parsing)
- `org/devio/as/proj/biz_home/home/StandTestDeleteFragment.kt` — standard test (0602 last result)
- `org/devio/as/proj/biz_home/home/ChargeTestFragment.java` — charge test (0204/4204 config parsing)
- `com/jiawei/batterytool3/ConstAct.java` — constants

## Verified Packet Reference (from logcat capture 2026-03-12)

All packets below were captured from the official app (`com.jiawei.batterytool3`) via `adb logcat`
and verified byte-for-byte against our `protocol.py` implementation.

### Requests (app → device)

| Command | Packet (hex) | CRC |
|---|---|---|
| `0100` init | `40400a0001000af10d0a` | `f10a` |
| `0203` info v2 | `40400a000203f9e90d0a` | `e9f9` |
| `0204` config | `40400a000204469d0d0a` | `9d46` |
| `0501` waveform start (20ms) | `40400c00050114000ad60d0a` | `d60a` |
| `0502` waveform stop | `40400a00050278b50d0a` | `b578` |
| `0602` quick test | `40400a000602109f0d0a` | `9f10` |

### Responses (device → app)

| Response | Packet (hex) | Parsed |
|---|---|---|
| `4204` config | `24241a00420402100ed00200...9ad50d0a` | maxVoltage=3600 (36V) |
| `4501` waveform ACK | `24240b00450100b6740d0a` | status=00 (streaming started) |
| `4301` device info | `242436004301424b323030...` | name=BK200, firmware=1.0.8 |

## CRC Bug Fix (2026-03-12)

The original `FCSTAB` lookup table (copied from `konnwei_voltage.py`) had **12 corrupted
values at indices 16-31** (rows 2-3). Values from other table rows were mixed in during
copy-paste. Commands without data payloads (0100, 0602, 0204) happened to never use those
indices during CRC computation, so they produced correct CRCs. The `0501` command with its
`1400` interval data payload did hit those indices, producing CRC `c0bf` instead of the
correct `0ad6`.

**Root cause**: FCSTAB rows 2-3 were garbled. Fixed by copying the correct values from the
decompiled Java source (`CrcUtil.java`).

**Affected files fixed**: `protocol.py`, `konnwei_voltage.py`

## Notes

- Device model: BK200, firmware 1.0.8, IAP 9.9.9 (confirmed via 4301 response)
- Device was discovered NOT to be a Leagend BM2/BM6/BM7 family device
- No AES encryption — plain binary protocol over BLE UART bridge
- The app uses `fastble` library for BLE communication
- Response header is `2424` while request header is `4040`
- The `0602` command works even without sending `0601` first
- macOS uses CoreBluetooth UUIDs instead of MAC addresses for BLE
