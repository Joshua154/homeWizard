"""Allowlisted classic API measurements, with no dependency on Home Assistant.

Field names and units are established by the original HomeWizard web client:
http://app.homewizard.com/assets/app.min.js (Windmeter/UVmeter/EnergyLink/
HeatLink models and detail templates). The legacy Homey drivers corroborate
current readings: https://github.com/jtebbens/com.homewizard/tree/master/drivers.
Unknown fields, wind unit codes and EnergyLink channel types are not guessed.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Measurement:
    translation_key: str
    device_class: str | None = None
    unit: str | None = None
    state_class: str | None = "measurement"


TEMPERATURE = Measurement("temperature", "temperature", "°C")
HUMIDITY = Measurement("humidity", "humidity", "%")
POWER = Measurement("power", "power", "W")
# These are daily reports, not lifetime meter readings. In particular, net
# energy can be negative. Do not advertise them as increasing lifetime totals.
ENERGY_TODAY = Measurement("energy_today", "energy", "kWh", None)
WIND_UNITS = {0: "km/h", 1: "m/s", 2: "Beaufort", 3: "kn"}
DETECTOR_KINDS = {
    "motion": "motion",
    "contact": "contact",
    "contact868": "contact",
    "smoke": "smoke",
    "smoke868": "smoke",
    "light": "light",
    "leakage": "moisture",
    "doorbell": "doorbell",
}


def extrema(key, measurement):
    """The API's +/- fields are extrema, not separate raw unit encodings."""
    return {
        key: measurement,
        f"{key}+": Measurement(
            f"{measurement.translation_key}_maximum", measurement.device_class, measurement.unit
        ),
        f"{key}-": Measurement(
            f"{measurement.translation_key}_minimum", measurement.device_class, measurement.unit
        ),
    }


SENSOR_FIELDS = {
    "thermometers": {**extrema("te", TEMPERATURE), **extrema("hu", HUMIDITY)},
    "windmeters": {
        **extrema("ws", Measurement("wind_speed", "wind_speed")),
        "gu": Measurement("wind_gust", "wind_speed"),
        "dir": Measurement("wind_direction", "wind_direction", "°", "measurement_angle"),
        "te": TEMPERATURE,
        "wc": Measurement("wind_chill", "temperature", "°C"),
    },
    "rainmeters": {
        "mm": Measurement("rain_today", "precipitation", "mm"),
        "3h": Measurement("rain_last_three_hours", "precipitation", "mm"),
    },
    "uvmeters": {"uv": Measurement("uv_index"), "uv+": Measurement("uv_index_maximum")},
    "energymeters": {**extrema("po", POWER), "dayTotal": ENERGY_TODAY},
    "energylinks": {
        "aggregate.po": Measurement("net_power", "power", "W"),
        "aggregate.dayTotal": Measurement("net_energy_today", "energy", "kWh", None),
        "used.po": Measurement("used_power", "power", "W"),
        "used.dayTotal": Measurement("used_energy_today", "energy", "kWh", None),
        "gas.lastHour": Measurement("gas_last_hour", "gas", "m³", None),
        "gas.dayTotal": Measurement("gas_today", "gas", "m³", None),
        **{
            f"{channel}.{field}": Measurement(f"{channel}_{name}", state_class=state_class)
            for channel in ("s1", "s2")
            for field, name, state_class in (
                ("po", "rate", "measurement"),
                ("dayTotal", "today", None),
            )
        },
    },
    "heatlinks": {
        "rte": TEMPERATURE,
        "rsp": Measurement("thermostat_setpoint", "temperature", "°C", None),
        "tte": Measurement("target_temperature", "temperature", "°C", None),
        "wte": Measurement("boiler_temperature", "temperature", "°C"),
        "wp": Measurement("water_pressure", "pressure", "bar"),
    },
}


def has_field(record: dict, key: str) -> bool:
    """Null leaf values still establish a supported measurement's existence."""
    parts = key.split(".")
    for part in parts[:-1]:
        record = record.get(part)
        if not isinstance(record, dict):
            return False
    return parts[-1] in record


def metadata(record: dict, status: dict, key: str):
    """Status metadata overrides inventory, including explicit null values."""
    return status[key] if key in status else record.get(key)


def measurement_fields(category: str, record: dict, status: dict):
    """Yield (key, platform, kind) tuples for models.discover's add callback."""
    for key, definition in SENSOR_FIELDS.get(category, {}).items():
        if has_field(record, key) or has_field(status, key):
            if category == "energylinks" and key.startswith(("s1.", "s2.")):
                channel = key[1]
                channel_type = metadata(record, status, f"t{channel}")
                if not isinstance(channel_type, str) or channel_type not in {
                    "solar",
                    "other",
                    "car",
                    "bike",
                    "water",
                }:
                    continue
            yield key, "sensor", definition.device_class or "measurement"
    if category == "kakusensors":
        detector_type = record.get("type")
        if isinstance(detector_type, str) and (kind := DETECTOR_KINDS.get(detector_type)):
            yield "status", "binary_sensor", kind
    if category == "heatlinks":
        for key in ("heating", "pump", "dhw"):
            if key in record or key in status:
                yield key, "binary_sensor", "heat" if key == "heating" else "running"
    if category in {*SENSOR_FIELDS, "weatherdisplays", "kakusensors", "switches"}:
        if "lowBattery" in record or "lowBattery" in status:
            yield "lowBattery", "binary_sensor", "battery"


def sensor_definition(category: str, key: str, record: dict, status: dict) -> Measurement:
    """Resolve metadata which can change when an existing device is edited."""
    if category == "switches" and key == "tte":
        return Measurement("target_temperature", "temperature", "°C", None)
    definition = SENSOR_FIELDS[category][key]
    if category == "windmeters" and key in {"ws", "ws+", "ws-", "gu"}:
        code = metadata(record, status, "unit")
        unit = WIND_UNITS.get(code) if type(code) is int else None
        return Measurement(definition.translation_key, "wind_speed" if unit else None, unit)
    if category == "energylinks" and key.startswith(("s1.", "s2.")):
        channel_type = metadata(record, status, f"t{key[1]}")
        if channel_type == "water":
            return Measurement(
                definition.translation_key,
                "volume_flow_rate" if key.endswith(".po") else "water",
                "L/min" if key.endswith(".po") else "L",
                definition.state_class,
            )
        if isinstance(channel_type, str) and channel_type in {"solar", "other", "car", "bike"}:
            return Measurement(
                definition.translation_key,
                "power" if key.endswith(".po") else "energy",
                "W" if key.endswith(".po") else "kWh",
                definition.state_class,
            )
        return Measurement(definition.translation_key, state_class=None)
    return definition
