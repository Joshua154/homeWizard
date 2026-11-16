"""Constants for the HomeWizard smartHome gateway (not HomeWizard Energy)."""

DOMAIN = "homewizard_smarthome"
DEFAULT_SCAN_INTERVAL = 10
INVENTORY_INTERVAL = 300
PLATFORMS = [
    "binary_sensor",
    "button",
    "climate",
    "cover",
    "light",
    "scene",
    "select",
    "sensor",
    "switch",
]
PRESETS = ("home", "away", "sleep", "holiday")
RADIATOR_MIN_TEMP = 5.0
RADIATOR_MAX_TEMP = 28.0
RADIATOR_TEMP_STEP = 0.5
HEATLINK_MIN_TEMP = 5.0
HEATLINK_MAX_TEMP = 30.0
HEATLINK_TEMP_STEP = 0.5
