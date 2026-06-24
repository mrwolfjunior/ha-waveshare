"""Constants for the Waveshare Relay integration."""

DOMAIN = "waveshare_relay"
VERSION = "1.0.0"

# Config entry keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_SLAVE_RELAY = "slave_relay"
CONF_SLAVE_SENSOR = "slave_sensor"
CONF_SCAN_INTERVAL = "scan_interval"

# Device descriptor keys (stored in options["devices"])
CONF_DEVICES = "devices"
CONF_DEVICE_ID = "id"
CONF_DEVICE_TYPE = "device_type"
CONF_DEVICE_NAME = "device_name"

# Light-specific
CONF_RELAY_INDEX = "relay_index"
CONF_SENSOR_SLAVE = "sensor_slave"
CONF_SENSOR_REGISTER = "sensor_register"
CONF_PULSE_MS = "pulse_ms"

# Cover-specific
CONF_RELAY_OPEN = "relay_open"
CONF_RELAY_CLOSE = "relay_close"
CONF_TILT_MS = "tilt_ms"

# Device types
DEVICE_TYPE_LIGHT = "light"
DEVICE_TYPE_COVER = "cover"

# Defaults
DEFAULT_PORT = 26
DEFAULT_SLAVE_RELAY = 1
DEFAULT_SLAVE_SENSOR = 2
DEFAULT_SCAN_INTERVAL = 5
DEFAULT_PULSE_MS = 400
DEFAULT_TILT_MS = 4000
