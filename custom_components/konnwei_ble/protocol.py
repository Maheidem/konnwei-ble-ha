"""KONNWEI BLE battery monitor protocol.

Packet format: [header 2B] [length_LE 2B] [command 2B] [data NB] [CRC_LE 2B] [terminator 2B]
- Request header:  0x40 0x40
- Response header: 0x24 0x24
- CRC: CRC-16/X25 (FCS-16), little-endian
- Terminator: 0x0D 0x0A

Reverse-engineered from the BKmonitor Android app (com.jiawei.batteryonline).
"""

from __future__ import annotations

import struct

# Protocol commands
CMD_INIT = 0x0100
CMD_QUICK_TEST = 0x0602
CMD_VOLTAGE_MONITOR = 0x0B0B
CMD_DEVICE_CONFIG = 0x0204
CMD_DEVICE_INFO = 0x0301
CMD_WAVEFORM_START = 0x0501
CMD_WAVEFORM_STOP = 0x0502

# Response commands (request cmd with first byte + 0x40)
RESP_INIT = "4100"
RESP_QUICK_TEST = "4602"
RESP_VOLTAGE_MONITOR = "4b0b"
RESP_DEVICE_CONFIG = "4204"
RESP_DEVICE_INFO = "4301"
RESP_WAVEFORM_START = "4501"
RESP_WAVEFORM_STOP = "4502"

# CRC-16/X25 (FCS-16) lookup table — from decompiled KONNWEI app
FCSTAB = [
    0, 4489, 8978, 12955, 17956, 22445, 25910, 29887,
    35912, 40385, 44890, 48851, 51820, 56293, 59774, 63735,
    4225, 264, 13203, 8730, 22181, 18220, 30135, 25662,
    40137, 36160, 49115, 44626, 56045, 52068, 63999, 59510,
    8450, 12427, 528, 5017, 26406, 30383, 17460, 21949,
    44362, 48323, 36440, 40913, 60270, 64231, 51324, 55797,
    12675, 8202, 4753, 792, 30631, 26158, 21685, 17724,
    48587, 44098, 40665, 36688, 64495, 60006, 55549, 51572,
    16900, 21389, 24854, 28831, 1056, 5545, 10034, 14011,
    52812, 57285, 60766, 64727, 34920, 39393, 43898, 47859,
    21125, 17164, 29079, 24606, 5281, 1320, 14259, 9786,
    57037, 53060, 64991, 60502, 39145, 35168, 48123, 43634,
    25350, 29327, 16404, 20893, 9506, 13483, 1584, 6073,
    61262, 65223, 52316, 56789, 43370, 47331, 35448, 39921,
    29575, 25102, 20629, 16668, 13731, 9258, 5809, 1848,
    65487, 60998, 56541, 52564, 47595, 43106, 39673, 35696,
    33800, 38273, 42778, 46739, 49708, 54181, 57662, 61623,
    2112, 6601, 11090, 15067, 20068, 24557, 28022, 31999,
    38025, 34048, 47003, 42514, 53933, 49956, 61887, 57398,
    6337, 2376, 15315, 10842, 24293, 20332, 32247, 27774,
    42250, 46211, 34328, 38801, 58158, 62119, 49212, 53685,
    10562, 14539, 2640, 7129, 28518, 32495, 19572, 24061,
    46475, 41986, 38553, 34576, 62383, 57894, 53437, 49460,
    14787, 10314, 6865, 2904, 32743, 28270, 23797, 19836,
    50700, 55173, 58654, 62615, 32808, 37281, 41786, 45747,
    19012, 23501, 26966, 30943, 3168, 7657, 12146, 16123,
    54925, 50948, 62879, 58390, 37033, 33056, 46011, 41522,
    23237, 19276, 31191, 26718, 7393, 3432, 16371, 11898,
    59150, 63111, 50204, 54677, 41258, 45219, 33336, 37809,
    27462, 31439, 18516, 23005, 11618, 15595, 3696, 8185,
    63375, 58886, 54429, 50452, 45483, 40994, 37561, 33584,
    31687, 27214, 22741, 18780, 15843, 11370, 7921, 3960,
]


def crc16_x25(data: bytes) -> int:
    """Compute CRC-16/X25 (FCS-16) over raw bytes."""
    fcs = 0xFFFF
    for b in data:
        fcs = (fcs >> 8) ^ FCSTAB[(b ^ fcs) & 0xFF]
    return 0xFFFF ^ fcs


def build_packet(command: int, data: bytes = b"") -> bytes:
    """Build a KONNWEI protocol packet ready to write to FFF2.

    Args:
        command: 2-byte command as integer (e.g. 0x0100, 0x0602).
        data: optional payload bytes.

    Returns:
        Complete packet as bytes.
    """
    # header(2) + length(2) + cmd(2) + data(N) + crc(2) + terminator(2)
    total_len = 10 + len(data)

    payload = bytearray()
    payload += b"\x40\x40"
    payload += struct.pack("<H", total_len)
    payload += struct.pack(">H", command)  # command is big-endian in the packet
    payload += data

    crc = crc16_x25(bytes(payload))

    packet = bytearray(payload)
    packet += struct.pack("<H", crc)
    packet += b"\x0d\x0a"
    return bytes(packet)


def parse_response(raw: bytes) -> dict | None:
    """Parse a complete KONNWEI response packet.

    Args:
        raw: complete packet bytes (header through terminator).

    Returns:
        Dict with parsed data, or None if packet is invalid.
    """
    hex_str = raw.hex()

    if len(hex_str) < 18:
        return None

    # Validate terminator
    if not hex_str.endswith("0d0a"):
        return None

    # Validate CRC: CRC covers everything before the last 4 bytes (crc+terminator)
    payload_bytes = raw[:-4]  # everything except CRC(2) + terminator(2)
    expected_crc = crc16_x25(payload_bytes)
    actual_crc = struct.unpack_from("<H", raw, len(raw) - 4)[0]
    if expected_crc != actual_crc:
        return None

    resp_cmd = hex_str[8:12]

    if resp_cmd == RESP_QUICK_TEST:
        return _parse_4602(raw)
    if resp_cmd == RESP_VOLTAGE_MONITOR:
        return _parse_4b0b(raw)
    if resp_cmd == RESP_INIT:
        return {"init_ok": True}
    if resp_cmd == RESP_DEVICE_CONFIG:
        return _parse_4204(raw)
    if resp_cmd == RESP_WAVEFORM_START:
        return _parse_4501(raw)
    if resp_cmd == RESP_WAVEFORM_STOP:
        return {"command": resp_cmd, "streaming_stopped": True}
    if resp_cmd == RESP_DEVICE_INFO:
        return _parse_4301(raw)

    return {"command": resp_cmd}


def _parse_4602(raw: bytes) -> dict | None:
    """Parse a 4602 quick test response."""
    if len(raw) < 17:  # minimum: header(2)+len(2)+cmd(2)+data(7)+crc(2)+term(2)
        return None

    voltage = struct.unpack_from("<H", raw, 6)[0] / 100.0
    cca = struct.unpack_from("<H", raw, 8)[0]
    resistance = struct.unpack_from("<H", raw, 10)[0] / 100.0
    health = raw[12]
    charge = raw[13]
    status = raw[14]

    return {
        "voltage": voltage,
        "cca": cca,
        "resistance": resistance,
        "health": health,
        "charge": charge,
        "status": status,
    }


def _parse_4b0b(raw: bytes) -> dict | None:
    """Parse a 4B0B voltage monitor response."""
    if len(raw) < 12:
        return None

    voltage = struct.unpack_from("<H", raw, 6)[0] / 100.0
    result: dict = {"voltage": voltage}

    if len(raw) >= 10:
        result["connected"] = raw[8] != 0
    if len(raw) >= 11:
        result["charging"] = raw[9] != 0

    return result


def _parse_4204(raw: bytes) -> dict:
    """Parse a 4204 device config response."""
    # [14:18] maxVoltage LE uint16, [22:24] battery system uint8
    result: dict = {"command": "4204"}
    if len(raw) >= 9:
        result["max_voltage"] = struct.unpack_from("<H", raw, 7)[0]
    if len(raw) >= 12:
        result["battery_system"] = raw[11]
    return result


def _parse_4501(raw: bytes) -> dict:
    """Parse a 4501 waveform start ACK response."""
    result: dict = {"command": "4501"}
    if len(raw) >= 7:
        result["status"] = raw[6]
        result["streaming"] = raw[6] == 0x00
    return result


def _parse_4301(raw: bytes) -> dict:
    """Parse a 4301 device info response."""
    result: dict = {"command": "4301"}
    if len(raw) >= 10:
        # Device name starts at byte 6, null-terminated
        name_end = raw.index(0, 6) if 0 in raw[6:] else len(raw) - 4
        result["device_name"] = raw[6:name_end].decode("ascii", errors="replace").strip("\x00")
    return result


def parse_waveform_samples(data: bytes, max_voltage: int = 3600) -> list[float]:
    """Parse raw waveform voltage samples from BLE notifications.

    During waveform streaming, the device sends unframed LE uint16 values
    directly on FFF1 (no 4040/2424 packet wrapping).

    Args:
        data: raw notification bytes (2, 4, 6, or 8 bytes per notification).
        max_voltage: maximum valid voltage in centvolts (from 4204 config).

    Returns:
        List of voltage floats, filtered for validity.
    """
    samples = []
    for offset in range(0, len(data) - 1, 2):
        raw_val = struct.unpack_from("<H", data, offset)[0]
        if 0 < raw_val <= max_voltage:
            samples.append(raw_val / 100.0)
    return samples


def extract_packets(buffer: bytearray) -> tuple[list[bytes], bytearray]:
    """Extract complete packets from a byte buffer.

    BLE notifications may arrive as fragments. This function finds complete
    packets (ending with 0x0D 0x0A) and returns them plus any remaining bytes.

    Returns:
        Tuple of (list of complete packet bytes, remaining buffer).
    """
    packets: list[bytes] = []
    hex_str = buffer.hex()

    while "0d0a" in hex_str:
        end_idx = hex_str.index("0d0a") + 4
        packet_hex = hex_str[:end_idx]
        hex_str = hex_str[end_idx:]
        packets.append(bytes.fromhex(packet_hex))

    return packets, bytearray.fromhex(hex_str)
