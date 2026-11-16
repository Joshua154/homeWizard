"""Synthetic classic API records derived from documented client field use.

Sources: http://app.homewizard.com/assets/app.min.js models/detail templates;
https://github.com/jtebbens/com.homewizard/tree/master/drivers legacy drivers.
Values and device identities below are invented test data, not device captures.
"""

import logging
from copy import deepcopy
from types import SimpleNamespace

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import (
    DATA_COMPONENT,
    DEVICE_CLASS_STATE_CLASSES,
    DEVICE_CLASS_UNITS,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import STATE_UNKNOWN
from homeassistant.helpers import entity_registry as er

from custom_components.homewizard_smarthome.binary_sensor import HomeWizardBinarySensor
from custom_components.homewizard_smarthome.const import DOMAIN
from custom_components.homewizard_smarthome.measurements import SENSOR_FIELDS, measurement_fields
from custom_components.homewizard_smarthome.models import EntitySpec, discover
from custom_components.homewizard_smarthome.sensor import HomeWizardSensor


def make_entity(category, key, status, inventory=None, *, platform="sensor", kind=""):
    device_key = category, "99"
    coordinator = SimpleNamespace(
        serial="SYNTHETIC",
        inventory={device_key: {"id": 99, **(inventory or {})}},
        status={device_key: {"id": 99, **status}},
        last_update_success=True,
    )
    spec = EntitySpec(category, "99", key, platform, kind)
    cls = HomeWizardSensor if platform == "sensor" else HomeWizardBinarySensor
    return cls(coordinator, spec)


@pytest.mark.parametrize(
    ("category", "record", "keys"),
    [
        (
            "thermometers",
            {"te": 19.1, "hu": None, "te+": 21, "te-": 17},
            {"te", "hu", "te+", "te-"},
        ),
        (
            "windmeters",
            {"unit": 0, "ws": 12.3, "gu": 15, "dir": "WNW 292", "te": 11, "wc": 8},
            {"ws", "gu", "dir", "te", "wc"},
        ),
        ("rainmeters", {"mm": 8.1, "3h": 0.2}, {"mm", "3h"}),
        ("uvmeters", {"uv": 3.5, "uv+": 4.2}, {"uv", "uv+"}),
        ("energymeters", {"po": 400, "dayTotal": 3.2}, {"po", "dayTotal"}),
        (
            "heatlinks",
            {
                "rte": 20,
                "rsp": 21,
                "tte": 0,
                "wte": 60,
                "wp": 1.5,
                "pump": "on",
                "heating": "off",
                "dhw": None,
            },
            {"rte", "rsp", "tte", "wte", "wp", "pump", "heating", "dhw"},
        ),
    ],
)
def test_allowlisted_measurements_only_when_present(category, record, keys):
    assert {key for key, _, _ in measurement_fields(category, record, {})} == keys
    assert {key for key, _, _ in measurement_fields(category, {}, record)} == keys
    assert list(measurement_fields(category, {}, {})) == []


def test_energy_link_nested_channels_and_unknown_types():
    record = {
        "t1": "solar",
        "t2": "water",
        "s1": {"po": 900, "dayTotal": 4.2},
        "s2": {"po": 3, "dayTotal": 120},
        "aggregate": {"po": -700, "dayTotal": -2.1},
        "used": {"po": 200, "dayTotal": 2.1},
        "gas": {"lastHour": 0.2, "dayTotal": 1.3},
    }
    keys = {key for key, _, _ in measurement_fields("energylinks", record, {})}
    assert keys == {
        "s1.po",
        "s1.dayTotal",
        "s2.po",
        "s2.dayTotal",
        "aggregate.po",
        "aggregate.dayTotal",
        "used.po",
        "used.dayTotal",
        "gas.lastHour",
        "gas.dayTotal",
    }
    record["t1"] = "unfamiliar"
    record["s2"] = None
    assert {key for key, _, _ in measurement_fields("energylinks", record, {})} == keys - {
        "s1.po",
        "s1.dayTotal",
        "s2.po",
        "s2.dayTotal",
    }


@pytest.mark.parametrize(("code", "unit"), [(0, "km/h"), (1, "m/s"), (2, "Beaufort"), (3, "kn")])
def test_wind_units_from_official_client(code, unit):
    entity = make_entity("windmeters", "ws", {"unit": code, "ws": 2.3})
    assert entity.native_value == 2.3
    assert entity.native_unit_of_measurement == unit
    assert entity.device_class == SensorDeviceClass.WIND_SPEED
    assert entity.state_class == SensorStateClass.MEASUREMENT


@pytest.mark.parametrize("code", [None, True, "0", 4, -1, [], {}])
def test_unknown_wind_unit_never_assumed(code):
    entity = make_entity("windmeters", "gu", {"unit": code, "gu": 2.3}, {"unit": 0})
    assert entity.native_value is None
    assert entity.native_unit_of_measurement is None
    assert entity.device_class is None


def test_wind_metadata_fallback_and_later_change():
    entity = make_entity("windmeters", "ws", {"ws": 10}, {"unit": 0})
    assert entity.native_unit_of_measurement == "km/h"
    entity.coordinator.status[entity.spec.device_key]["unit"] = 1
    assert entity.native_unit_of_measurement == "m/s"
    assert entity.unique_id == "SYNTHETIC:windmeters:99:ws"


@pytest.mark.parametrize(
    ("direction", "expected"),
    [
        ("WNW 292", 292),
        ("N 0", 0),
        ("NNW 337.5", 337.5),
        (None, None),
        ("SW", None),
        ("bad 42", None),
        ("N 400", None),
        ("NW nan", None),
        (2, None),
    ],
)
def test_wind_direction_explicit_degrees(direction, expected):
    entity = make_entity("windmeters", "dir", {"dir": direction})
    assert entity.native_value == expected
    assert entity.native_unit_of_measurement == "°"
    assert entity.state_class == SensorStateClass.MEASUREMENT_ANGLE


@pytest.mark.parametrize(
    ("category", "key", "status", "inventory", "value", "unit", "device_class"),
    [
        ("rainmeters", "3h", {"3h": 0}, {}, 0, "mm", SensorDeviceClass.PRECIPITATION),
        ("uvmeters", "uv", {"uv": 3.5}, {}, 3.5, None, None),
        ("energymeters", "po", {"po": 400}, {}, 400, "W", SensorDeviceClass.POWER),
        (
            "energylinks",
            "aggregate.dayTotal",
            {"aggregate": {"dayTotal": -1.2}},
            {},
            -1.2,
            "kWh",
            SensorDeviceClass.ENERGY,
        ),
        (
            "energylinks",
            "gas.lastHour",
            {"gas": {"lastHour": 0.2}},
            {},
            0.2,
            "m³",
            SensorDeviceClass.GAS,
        ),
        (
            "energylinks",
            "s1.po",
            {"s1": {"po": 2.5}},
            {"t1": "water"},
            2.5,
            "L/min",
            SensorDeviceClass.VOLUME_FLOW_RATE,
        ),
        (
            "energylinks",
            "s2.dayTotal",
            {"s2": {"dayTotal": 120}},
            {"t2": "water"},
            120,
            "L",
            SensorDeviceClass.WATER,
        ),
        (
            "energylinks",
            "s1.po",
            {"s1": {"po": 200}},
            {"t1": "bike"},
            200,
            "W",
            SensorDeviceClass.POWER,
        ),
        ("heatlinks", "wp", {"wp": 1.5}, {}, 1.5, "bar", SensorDeviceClass.PRESSURE),
    ],
)
def test_units_classes_and_values(category, key, status, inventory, value, unit, device_class):
    entity = make_entity(category, key, status, inventory)
    assert entity.native_value == value
    assert entity.native_unit_of_measurement == unit
    assert entity.device_class == device_class


@pytest.mark.parametrize(
    "status",
    [
        {},
        {"s1": None},
        {"s1": {}},
        {"s1": {"po": None}},
        {"s1": {"po": True}},
        {"s1": {"po": "200"}},
    ],
)
def test_missing_null_and_malformed_nested_readings_stay_unknown(status):
    entity = make_entity("energylinks", "s1.po", status, {"t1": "solar", "s1": {"po": 200}})
    assert entity.native_value is None


def test_daily_totals_never_claim_lifetime_increasing_statistics():
    entity = make_entity("energylinks", "aggregate.dayTotal", {"aggregate": {"dayTotal": -2}})
    assert entity.state_class is None


@pytest.mark.parametrize("channel_type", [None, True, 1, "unknown", [], {}])
def test_malformed_channel_metadata_never_crashes_or_guesses_units(channel_type):
    record = {"t1": "solar", "s1": {"po": 200}}
    status = {"t1": channel_type, "s1": {"po": 200}}
    assert list(measurement_fields("energylinks", record, status)) == []
    entity = make_entity("energylinks", "s1.po", status, record)
    assert entity.native_value is None
    assert entity.native_unit_of_measurement is None
    assert entity.device_class is None


@pytest.mark.parametrize("detector_type", [None, True, 1, [], {}])
def test_malformed_detector_type_stays_unsupported(detector_type):
    assert list(measurement_fields("kakusensors", {"type": detector_type}, {})) == []


@pytest.mark.parametrize(
    ("key", "kind", "device_class"),
    [
        ("heating", "heat", BinarySensorDeviceClass.HEAT),
        ("pump", "running", BinarySensorDeviceClass.RUNNING),
        ("dhw", "running", BinarySensorDeviceClass.RUNNING),
    ],
)
def test_readonly_heatlink_binary_reports(key, kind, device_class):
    entity = make_entity("heatlinks", key, {key: "on"}, platform="binary_sensor", kind=kind)
    assert entity.device_class == device_class
    assert entity.is_on is True
    entity.coordinator.status[entity.spec.device_key][key] = "off"
    assert entity.is_on is False


@pytest.mark.parametrize(
    ("detector_type", "kind", "device_class"),
    [
        ("smoke868", "smoke", BinarySensorDeviceClass.SMOKE),
        ("contact868", "contact", BinarySensorDeviceClass.DOOR),
        ("leakage", "moisture", BinarySensorDeviceClass.MOISTURE),
        ("doorbell", "doorbell", None),
        ("light", "light", None),
    ],
)
def test_extended_detectors_preserve_explicit_status(detector_type, kind, device_class):
    assert ("status", "binary_sensor", kind) in set(
        measurement_fields("kakusensors", {"type": detector_type}, {})
    )
    entity = make_entity(
        "kakusensors", "status", {"status": "yes"}, platform="binary_sensor", kind=kind
    )
    assert entity.device_class == device_class
    assert entity.is_on is True
    entity.coordinator.status[entity.spec.device_key]["status"] = None
    assert entity.is_on is None


def test_no_speculative_weather_display_or_detector_mapping():
    assert (
        list(measurement_fields("weatherdisplays", {"temperature": 10, "pressure": 1000}, {})) == []
    )
    assert (
        list(measurement_fields("kakusensors", {"type": "unfamiliar", "status": "yes"}, {})) == []
    )


def test_model_discovers_expanded_families_without_duplicate_identity():
    inventory = {
        ("windmeters", "1"): {"unit": 0, "ws": None},
        ("uvmeters", "1"): {"uv": None, "lowBattery": "yes"},
        ("energymeters", "1"): {"po": None, "lowBattery": "no"},
        ("kakusensors", "1"): {"type": "smoke868"},
    }
    specs = discover(inventory, {})
    assert {spec.unique_id("synthetic") for spec in specs} == {
        "synthetic:windmeters:1:ws",
        "synthetic:uvmeters:1:uv",
        "synthetic:uvmeters:1:lowBattery",
        "synthetic:energymeters:1:po",
        "synthetic:energymeters:1:lowBattery",
        "synthetic:kakusensors:1:status",
    }


def test_measurement_metadata_matches_home_assistant_contracts():
    """Catch HA restrictions such as circular rather than linear angle statistics."""
    for category, fields in SENSOR_FIELDS.items():
        for key in fields:
            entity = make_entity(category, key, {"unit": 0}, {"t1": "solar", "t2": "water"})
            if entity.device_class is None:
                continue
            if entity.state_class is not None:
                assert entity.state_class in DEVICE_CLASS_STATE_CLASSES[entity.device_class]
            if entity.native_unit_of_measurement is not None:
                assert entity.native_unit_of_measurement in DEVICE_CLASS_UNITS[entity.device_class]


async def test_measurements_in_home_assistant(hass, loaded, client, caplog):
    """Exercise actual platform discovery, validation and refreshes across families."""
    inventory = deepcopy(client.get_sensors.return_value)
    status = deepcopy(client.get_status.return_value)
    records = {
        "windmeters": [
            {"id": 99, "unit": 0, "ws": 36, "gu": 54, "dir": "WNW 292", "te": 11, "wc": 8}
        ],
        "rainmeters": [{"id": 99, "mm": 8.1, "3h": 0.2}],
        "uvmeters": [{"id": 99, "uv": 3.5, "uv+": 4.2, "lowBattery": "no"}],
        "energymeters": [{"id": 99, "po": 400, "dayTotal": 3.2}],
        "energylinks": [
            {
                "id": 99,
                "t1": "solar",
                "t2": "water",
                "s1": {"po": 900, "dayTotal": 4.2},
                "s2": {"po": 3, "dayTotal": 120},
                "aggregate": {"po": -700, "dayTotal": -2.1},
                "used": {"po": 200, "dayTotal": 2.1},
                "gas": {"lastHour": 0.2, "dayTotal": 1.3},
            }
        ],
        "heatlinks": [
            {
                "id": 99,
                "rte": 20,
                "rsp": 21,
                "tte": 0,
                "wte": 60,
                "wp": 1.5,
                "pump": "on",
                "heating": "off",
                "dhw": "on",
            }
        ],
        "kakusensors": [
            {"id": 99, "type": "smoke868", "status": "yes"},
            {"id": 100, "type": "contact868", "status": "no"},
            {"id": 101, "type": "leakage", "status": "yes"},
            {"id": 102, "type": "doorbell", "status": None},
        ],
    }
    for category, new_records in records.items():
        inventory.setdefault(category, []).extend(deepcopy(new_records))
        status.setdefault(category, []).extend(deepcopy(new_records))
    client.get_sensors.return_value = inventory
    client.get_status.return_value = status
    loaded._inventory_at = 0
    await loaded.async_refresh()
    await hass.async_block_till_done()

    registry = er.async_get(hass)

    def state_for(category, key, *, platform="sensor", device_id=99):
        unique_id = f"TEST-GATEWAY-001:{category}:{device_id}:{key}"
        entity_id = registry.async_get_entity_id(platform, DOMAIN, unique_id)
        assert entity_id is not None, unique_id
        assert registry.async_get(entity_id).unique_id == unique_id
        state = hass.states.get(entity_id)
        assert state is not None
        return state

    expected_sensor_states = {
        ("windmeters", "dir"): ("292.0", "°", "wind_direction"),
        ("windmeters", "te"): ("11", "°C", "temperature"),
        ("windmeters", "wc"): ("8", "°C", "temperature"),
        ("rainmeters", "mm"): ("8.1", "mm", "precipitation"),
        ("rainmeters", "3h"): ("0.2", "mm", "precipitation"),
        ("uvmeters", "uv"): ("3.5", None, None),
        ("uvmeters", "uv+"): ("4.2", None, None),
        ("energymeters", "po"): ("400", "W", "power"),
        ("energymeters", "dayTotal"): ("3.2", "kWh", "energy"),
        ("energylinks", "aggregate.po"): ("-700", "W", "power"),
        ("energylinks", "aggregate.dayTotal"): ("-2.1", "kWh", "energy"),
        ("energylinks", "used.po"): ("200", "W", "power"),
        ("energylinks", "used.dayTotal"): ("2.1", "kWh", "energy"),
        ("energylinks", "gas.lastHour"): ("0.2", "m³", "gas"),
        ("energylinks", "gas.dayTotal"): ("1.3", "m³", "gas"),
        ("energylinks", "s1.po"): ("900", "W", "power"),
        ("energylinks", "s1.dayTotal"): ("4.2", "kWh", "energy"),
        ("energylinks", "s2.po"): ("3", "L/min", "volume_flow_rate"),
        ("energylinks", "s2.dayTotal"): ("120", "L", "water"),
        ("heatlinks", "rte"): ("20", "°C", "temperature"),
        ("heatlinks", "rsp"): ("21", "°C", "temperature"),
        ("heatlinks", "tte"): ("0", "°C", "temperature"),
        ("heatlinks", "wte"): ("60", "°C", "temperature"),
        ("heatlinks", "wp"): ("1.5", "bar", "pressure"),
    }
    for (category, key), (value, unit, device_class) in expected_sensor_states.items():
        state = state_for(category, key)
        assert state.state == value
        assert state.attributes.get("unit_of_measurement") == unit
        assert state.attributes.get("device_class") == device_class
    assert state_for("windmeters", "dir").attributes["state_class"] == "measurement_angle"
    assert "state_class" not in state_for("energylinks", "aggregate.dayTotal").attributes
    for category, key, device_id, value, device_class in [
        ("uvmeters", "lowBattery", 99, "off", "battery"),
        ("heatlinks", "pump", 99, "on", "running"),
        ("heatlinks", "heating", 99, "off", "heat"),
        ("heatlinks", "dhw", 99, "on", "running"),
        ("kakusensors", "status", 99, "on", "smoke"),
        ("kakusensors", "status", 100, "off", "door"),
        ("kakusensors", "status", 101, "on", "moisture"),
        ("kakusensors", "status", 102, STATE_UNKNOWN, None),
    ]:
        state = state_for(category, key, device_id=device_id, platform="binary_sensor")
        assert state.state == value
        assert state.attributes.get("device_class") == device_class

    wind_id = state_for("windmeters", "ws").entity_id
    wind = hass.data[DATA_COMPONENT].get_entity(wind_id)
    assert wind.native_value == 36
    assert wind.native_unit_of_measurement == "km/h"
    assert state_for("windmeters", "gu").state != STATE_UNKNOWN
    # Gateway unit edits change native metadata while the registry ID remains stable.
    wind_record = next(record for record in status["windmeters"] if record["id"] == 99)
    wind_record.update({"unit": 1, "ws": 10})
    await loaded.async_refresh()
    await hass.async_block_till_done()
    assert wind.native_unit_of_measurement == "m/s"
    assert wind.native_value == 10
    assert state_for("windmeters", "ws").entity_id == wind_id
    assert state_for("windmeters", "ws").state != STATE_UNKNOWN

    # Explicit null and missing current/nested readings never revive inventory data.
    wind_record.pop("ws")
    wind_record["gu"] = None
    next(record for record in status["energylinks"] if record["id"] == 99)["s1"] = None
    await loaded.async_refresh()
    await hass.async_block_till_done()
    assert state_for("windmeters", "ws").state == STATE_UNKNOWN
    assert state_for("windmeters", "gu").state == STATE_UNKNOWN
    assert state_for("energylinks", "s1.po").state == STATE_UNKNOWN
    assert state_for("energylinks", "s1.dayTotal").state == STATE_UNKNOWN
    assert not [
        record
        for record in caplog.records
        if record.levelno >= logging.WARNING
        and (
            record.name.startswith("homeassistant.components.sensor")
            or record.name.startswith("custom_components.homewizard_smarthome")
        )
    ]
    client.command.assert_not_called()
