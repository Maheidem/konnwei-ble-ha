"""Constants for the KONNWEI BLE Battery Monitor integration."""

DOMAIN = "konnwei_ble"

# BLE UUIDs (KONNWEI BLE UART bridge on FFF0 service)
UUID_SERVICE = "0000fff0-0000-1000-8000-00805f9b34fb"
UUID_CHAR_NOTIFY = "0000fff1-0000-1000-8000-00805f9b34fb"
UUID_CHAR_WRITE = "0000fff2-0000-1000-8000-00805f9b34fb"

# BLE advertisement matching
MANUFACTURER_ID = 19522
LOCAL_NAME_PREFIX = "KONNWEI"

# Data keys returned by the coordinator
KEY_VOLTAGE = "voltage"
KEY_CCA = "cca"
KEY_RESISTANCE = "resistance"
KEY_HEALTH = "health"
KEY_CHARGE = "charge"
KEY_STATUS = "status"

# Defaults
DEFAULT_UPDATE_INTERVAL = 60  # seconds
MIN_UPDATE_INTERVAL = 30
MAX_UPDATE_INTERVAL = 300

# Waveform settings
WAVEFORM_INTERVAL = 1000  # ms between samples (1 sample/sec)
WAVEFORM_COLLECT_TIME = 3  # seconds to collect live voltage samples

# Timeouts
CONNECT_TIMEOUT = 15  # seconds
RESPONSE_TIMEOUT = 5  # seconds
