"""
KONNWEI BLE Battery Voltage Reader

Protocol reverse-engineered from the BKmonitor/Kbattery Android app (com.jiawei.batteryonline).

Packet format: 4040 [len_LE] [cmd] [data] [CRC_LE] 0D0A
- Header: 0x40 0x40
- Length: total packet bytes, 2 bytes little-endian
- Command: 2 bytes (responses = request cmd + 0x40 on first byte)
- CRC: CRC-16/X25 (FCS-16), 2 bytes little-endian
- Terminator: 0x0D 0x0A

Key commands:
    0100 = init/handshake (response: 4100)
    0B0B = request voltage monitor data (response: 4B0B)
    0602 = quick test data (response: 4602 with detailed voltage/CCA/resistance)

4B0B response data layout (hex string positions after 4040+len+cmd):
    [12:16] = voltage (LE uint16 / 100.0 = volts)
    [16:18] = battery connect status (00=disconnected)
    [18:20] = charging status

Usage:
    pip install bleak
    python konnwei_voltage.py
"""

import asyncio
import struct
import sys
from bleak import BleakClient, BleakScanner

DEVICE_NAME = "KONNWEI"
CHAR_NOTIFY = "0000fff1-0000-1000-8000-00805f9b34fb"
CHAR_WRITE  = "0000fff2-0000-1000-8000-00805f9b34fb"

# CRC-16/X25 (FCS-16) lookup table - from decompiled app
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


def crc16_x25(hex_string: str) -> int:
    """CRC-16/X25 (FCS-16) as implemented in the KONNWEI app."""
    data = bytes.fromhex(hex_string)
    fcs = 0xFFFF
    for b in data:
        fcs = (fcs >> 8) ^ FCSTAB[(b ^ fcs) & 0xFF]
    return 0xFFFF ^ fcs


def build_packet(command: str, data: str = "") -> bytes:
    """Build a KONNWEI protocol packet.

    Args:
        command: 4-char hex string (e.g., "0100", "0b0b")
        data: hex string of data payload (empty string for no data)

    Returns:
        bytes ready to write to FFF2
    """
    data_bytes = len(data) // 2
    total_len = data_bytes + 10  # header(2) + len(2) + cmd(2) + crc(2) + term(2)
    len_hex = struct.pack("<H", total_len).hex()  # little-endian uint16

    payload = "4040" + len_hex + command + data
    crc = crc16_x25(payload)
    crc_hex = struct.pack("<H", crc).hex()

    packet_hex = payload + crc_hex + "0d0a"
    return bytes.fromhex(packet_hex)


def parse_le_uint16(hex_str: str) -> int:
    """Parse a 4-char hex string as a little-endian uint16 (getDaduan from the app)."""
    raw = bytes.fromhex(hex_str)
    val = 0
    for i in range(len(raw) - 1, -1, -1):
        val = (val << 8) | (raw[i] & 0xFF)
    return val


def parse_le_uint8(hex_str: str) -> int:
    """Parse a 2-char hex string as uint8."""
    return int(hex_str, 16)


async def find_device(timeout: int = 10) -> str | None:
    """Scan for the KONNWEI device."""
    print(f"Scanning for '{DEVICE_NAME}' ({timeout}s)...")
    devices = await BleakScanner.discover(return_adv=True, timeout=timeout)
    for device, adv in devices.values():
        if device.name and DEVICE_NAME in device.name.upper():
            print(f"  Found: {device.name} | {device.address} | RSSI: {adv.rssi}")
            return device.address
    return None


async def read_voltage():
    """Connect to KONNWEI, send protocol commands, read voltage."""
    address = await find_device()
    if not address:
        print("No KONNWEI device found. Is it powered on and in range?")
        return None

    collected = bytearray()
    result = {}

    def on_notify(_sender, data):
        nonlocal collected, result
        collected.extend(data)
        hex_str = collected.hex()

        # Check if we have a complete packet (ends with 0d0a)
        while "0d0a" in hex_str:
            end_idx = hex_str.index("0d0a") + 4
            packet = hex_str[:end_idx]
            hex_str = hex_str[end_idx:]
            collected = bytearray.fromhex(hex_str)

            print(f"  << {packet}")

            if len(packet) < 18:
                continue

            resp_cmd = packet[8:12]

            # 4B0B = voltage monitor response
            if resp_cmd == "4b0b" and len(packet) >= 20:
                voltage_raw = parse_le_uint16(packet[12:16])
                voltage = voltage_raw / 100.0
                connect_status = parse_le_uint8(packet[16:18])
                result["voltage"] = voltage
                result["connected"] = connect_status != 0
                if len(packet) >= 22:
                    charging = parse_le_uint8(packet[18:20])
                    result["charging"] = charging != 0

            # 4602 = quick test response (detailed)
            elif resp_cmd == "4602" and len(packet) >= 34:
                voltage = parse_le_uint16(packet[12:16]) / 100.0
                cca = parse_le_uint16(packet[16:20])
                resistance = parse_le_uint16(packet[20:24]) / 100.0
                health = parse_le_uint8(packet[24:26])
                charge = parse_le_uint8(packet[26:28])
                status = parse_le_uint8(packet[28:30])
                result["voltage"] = voltage
                result["cca"] = cca
                result["resistance"] = resistance
                result["health"] = health
                result["charge"] = charge
                result["status"] = status

            # 4100 = init response
            elif resp_cmd == "4100":
                result["init_ok"] = True
                print(f"    Init response received")

            # Any other response
            else:
                print(f"    Response cmd: {resp_cmd}")

    async with BleakClient(address, timeout=20) as client:
        print(f"Connected to {address}")

        await client.start_notify(CHAR_NOTIFY, on_notify)

        # Step 1: Send init command (0100)
        init_pkt = build_packet("0100")
        print(f"\n  >> INIT: {init_pkt.hex()}")
        await client.write_gatt_char(CHAR_WRITE, init_pkt, response=False)
        await asyncio.sleep(2)

        # Step 2: Send voltage monitor command (0B0B)
        volt_pkt = build_packet("0b0b")
        print(f"\n  >> VOLT: {volt_pkt.hex()}")
        await client.write_gatt_char(CHAR_WRITE, volt_pkt, response=False)
        await asyncio.sleep(3)

        # Step 3: If no voltage yet, try quick test (0602)
        if "voltage" not in result:
            quick_pkt = build_packet("0602")
            print(f"\n  >> QUICK: {quick_pkt.hex()}")
            await client.write_gatt_char(CHAR_WRITE, quick_pkt, response=False)
            await asyncio.sleep(3)

        # Step 4: Try ATRVER (ASCII version query used by the app)
        if not result:
            atrver = b"ATRVER\n\r"
            print(f"\n  >> ATRVER: {atrver.hex()}")
            await client.write_gatt_char(CHAR_WRITE, atrver, response=False)
            await asyncio.sleep(2)

        await client.stop_notify(CHAR_NOTIFY)

    if result:
        print(f"\n{'='*40}")
        if "voltage" in result:
            print(f"  Voltage:   {result['voltage']:.2f} V")
        if "connected" in result:
            print(f"  Connected: {'Yes' if result['connected'] else 'No'}")
        if "charging" in result:
            print(f"  Charging:  {'Yes' if result['charging'] else 'No'}")
        if "cca" in result:
            print(f"  CCA:       {result['cca']} A")
        if "resistance" in result:
            print(f"  Resistance:{result['resistance']:.2f} mΩ")
        if "health" in result:
            print(f"  Health:    {result['health']}%")
        if "charge" in result:
            print(f"  Charge:    {result['charge']}%")
        print(f"{'='*40}")
    else:
        print("\nNo data received. Is the device connected to a battery?")
        print("The KONNWEI monitor needs a battery to measure voltage.")

    return result


async def explore_gatt():
    """Dump all GATT services/characteristics."""
    address = await find_device()
    if not address:
        return
    print(f"\nConnecting to {address}...")
    async with BleakClient(address, timeout=20) as client:
        print(f"Connected: {client.is_connected}\n")
        for service in client.services:
            print(f"Service: {service.uuid}")
            for char in service.characteristics:
                props = ", ".join(char.properties)
                print(f"  {char.uuid} | {props}")
                if "read" in char.properties:
                    try:
                        val = await client.read_gatt_char(char.uuid)
                        print(f"    -> {val.hex()} ({val})")
                    except Exception as e:
                        print(f"    -> read error: {e}")


if __name__ == "__main__":
    if "--explore" in sys.argv:
        asyncio.run(explore_gatt())
    else:
        asyncio.run(read_voltage())
