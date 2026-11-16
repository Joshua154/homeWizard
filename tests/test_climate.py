"""Climate services use mocked gateway commands and reported feedback only."""

from copy import deepcopy
from unittest.mock import patch

import pytest
from homeassistant.components.climate import ClimateEntityFeature, HVACMode
from homeassistant.const import STATE_UNAVAILABLE, UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from custom_components.homewizard_smarthome.api import GatewayError
from custom_components.homewizard_smarthome.climate import HomeWizardClimate
from custom_components.homewizard_smarthome.const import DOMAIN
from custom_components.homewizard_smarthome.models import EntitySpec


def climate_id(hass, category="switches", device="16"):
    return er.async_get(hass).async_get_entity_id(
        "climate", DOMAIN, f"TEST-GATEWAY-001:{category}:{device}:climate"
    )


async def add_heatlink(hass, loaded, client):
    """Discover an absent-in-the-captured-fixture device without touching hardware."""
    client.get_sensors.return_value = deepcopy(client.get_sensors.return_value)
    client.get_status.return_value = deepcopy(client.get_status.return_value)
    client.get_sensors.return_value["heatlinks"] = [{"id": 0, "name": "Test HeatLink"}]
    client.get_status.return_value["heatlinks"] = [
        {"id": 0, "rte": 20.125, "rsp": 18.5, "tte": 21, "heating": "on"}
    ]
    loaded._inventory_at = 0
    await loaded.async_refresh()
    await hass.async_block_till_done()
    return climate_id(hass, "heatlinks", "0")


async def test_radiator_controls_keep_reported_target(hass, loaded, client):
    entity_id = climate_id(hass)
    state = hass.states.get(entity_id)
    assert state.state == "heat"
    assert state.attributes["temperature"] == 15
    assert state.attributes["current_temperature"] is None
    assert "hvac_action" not in state.attributes
    assert state.attributes["hvac_modes"] == ["heat"]
    assert state.attributes["min_temp"] == 5
    assert state.attributes["max_temp"] == 28
    assert state.attributes["target_temp_step"] == 0.5
    assert state.attributes["supported_features"] == ClimateEntityFeature.TARGET_TEMPERATURE
    with patch.object(
        loaded, "async_request_refresh", wraps=loaded.async_request_refresh
    ) as refresh:
        await hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": entity_id, "temperature": 20.5},
            blocking=True,
        )
    client.set_radiator_temperature.assert_awaited_once_with("16", 20.5)
    refresh.assert_awaited_once()
    assert hass.states.get(entity_id).attributes["temperature"] == 15
    # Existing target-temperature sensor identity remains usable by automations.
    sensor_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, "TEST-GATEWAY-001:switches:16:tte"
    )
    assert hass.states.get(sensor_id).state == "15"


async def test_heatlink_dynamic_discovery_and_service(hass, loaded, client):
    entity_id = await add_heatlink(hass, loaded, client)
    state = hass.states.get(entity_id)
    assert state.attributes["temperature"] == 21
    assert state.attributes["current_temperature"] == 20.1
    assert state.attributes["hvac_action"] == "heating"
    assert state.attributes["min_temp"] == 5
    assert state.attributes["max_temp"] == 30
    assert state.attributes["target_temp_step"] == 0.5
    await hass.services.async_call(
        "climate", "set_temperature", {"entity_id": entity_id, "temperature": 22.5}, blocking=True
    )
    client.set_heatlink_temperature.assert_awaited_once_with("0", 22.5)
    client.set_radiator_temperature.assert_not_awaited()
    assert hass.states.get(entity_id).attributes["temperature"] == 21


@pytest.mark.parametrize(
    ("record", "target", "current", "action"),
    [
        ({"tte": 0, "rsp": 18.5, "rte": 19, "heating": "off"}, 18.5, 19, "idle"),
        ({"tte": 22, "rsp": 18.5, "rte": -1, "heating": "on"}, 22, -1, "heating"),
        ({"tte": None, "rsp": 18.5, "rte": None, "heating": None}, None, None, None),
        ({"rsp": 18.5}, None, None, None),
        ({"tte": 0}, None, None, None),
        ({"tte": True, "rte": False, "heating": "yes"}, None, None, None),
        ({"tte": -1, "rte": float("inf"), "heating": "unknown"}, None, None, None),
    ],
)
async def test_heatlink_feedback_does_not_invent_readings(
    hass, loaded, client, record, target, current, action
):
    entity_id = await add_heatlink(hass, loaded, client)
    client.get_status.return_value["heatlinks"] = [{"id": 0, **record}]
    await loaded.async_refresh()
    attributes = hass.states.get(entity_id).attributes
    assert attributes["temperature"] == target
    assert attributes["current_temperature"] == current
    assert attributes.get("hvac_action") == action


@pytest.mark.parametrize("record", [{"tte": None}, {}, {"tte": True}, {"tte": float("nan")}])
async def test_missing_radiator_target_stays_unknown(hass, loaded, client, record):
    client.get_status.return_value = deepcopy(client.get_status.return_value)
    client.get_status.return_value["switches"] = [{"id": 16, **record}]
    await loaded.async_refresh()
    state = hass.states.get(climate_id(hass))
    assert state.attributes["temperature"] is None
    assert state.attributes["current_temperature"] is None
    assert "hvac_action" not in state.attributes


@pytest.mark.parametrize(
    ("category", "temperature"),
    [
        ("switches", None),
        ("switches", True),
        ("switches", "20"),
        ("switches", float("inf")),
        ("switches", float("nan")),
        ("switches", 4.9),
        ("switches", 28.1),
        ("switches", 20.1),
        ("heatlinks", 4.5),
        ("heatlinks", 30.5),
        ("heatlinks", 20.1),
    ],
)
async def test_invalid_temperature_never_reaches_gateway(loaded, client, category, temperature):
    entity = HomeWizardClimate(loaded, EntitySpec(category, "16", "climate", "climate"))
    with pytest.raises(ServiceValidationError):
        await entity.async_set_temperature(temperature=temperature)
    client.set_radiator_temperature.assert_not_awaited()
    client.set_heatlink_temperature.assert_not_awaited()


async def test_unsupported_modes_do_not_issue_commands(hass, loaded, client):
    entity_id = climate_id(hass)
    await hass.services.async_call(
        "climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": "heat"}, blocking=True
    )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": "off"}, blocking=True
        )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": entity_id, "temperature": 20, "hvac_mode": "cool"},
            blocking=True,
        )
    entity = HomeWizardClimate(loaded, EntitySpec("switches", "16", "climate", "climate"))
    with pytest.raises(ServiceValidationError):
        await entity.async_set_hvac_mode(HVACMode.OFF)
    client.set_radiator_temperature.assert_not_awaited()
    client.command.assert_not_awaited()


async def test_fahrenheit_service_converts_to_celsius(hass, loaded, client):
    hass.config.units = US_CUSTOMARY_SYSTEM
    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": climate_id(hass), "temperature": 68.9},
        blocking=True,
    )
    assert client.set_radiator_temperature.await_args.args[0] == "16"
    assert client.set_radiator_temperature.await_args.args[1] == pytest.approx(20.5)
    assert hass.config.units.temperature_unit == UnitOfTemperature.FAHRENHEIT


async def test_failed_temperature_command_is_not_retried(hass, loaded, client):
    entity_id = climate_id(hass)
    client.set_radiator_temperature.side_effect = GatewayError("Timeout")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "climate", "set_temperature", {"entity_id": entity_id, "temperature": 20}, blocking=True
        )
    client.set_radiator_temperature.assert_awaited_once_with("16", 20)
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE
    client.set_radiator_temperature.side_effect = None
    await loaded.async_refresh()
    assert hass.states.get(entity_id).attributes["temperature"] == 15


async def test_heatlink_auto_resumes_thermostat_and_heat_holds_target(hass, loaded, client):
    entity_id = await add_heatlink(hass, loaded, client)
    await hass.services.async_call(
        "climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": "auto"}, blocking=True
    )
    client.clear_heatlink_override.assert_awaited_once_with("0")
    # Do not claim the thermostat resumed until the gateway reports tte=0.
    assert hass.states.get(entity_id).state == "heat"
    client.get_status.return_value["heatlinks"][0]["tte"] = 0
    await loaded.async_refresh()
    assert hass.states.get(entity_id).state == "auto"
    assert hass.states.get(entity_id).attributes["temperature"] == 18.5
    await hass.services.async_call(
        "climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": "heat"}, blocking=True
    )
    client.set_heatlink_temperature.assert_awaited_once_with("0", 18.5)


async def test_heatlink_cannot_hold_unknown_target(hass, loaded, client):
    entity_id = await add_heatlink(hass, loaded, client)
    client.get_status.return_value["heatlinks"] = [{"id": 0, "tte": 0}]
    await loaded.async_refresh()
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": "heat"}, blocking=True
        )
    client.set_heatlink_temperature.assert_not_awaited()


async def test_heatlink_presets_use_reported_configuration(hass, loaded, client):
    entity_id = await add_heatlink(hass, loaded, client)
    client.get_sensors.return_value["heatlinks"][0]["presets"] = [
        {"id": 0, "te": 20},
        {"id": 1, "te": 15},
        {"id": 2, "te": 21},
        {"id": 3, "te": 17.5},
    ]
    loaded._inventory_at = 0
    await loaded.async_refresh()
    state = hass.states.get(entity_id)
    assert state.attributes["preset_modes"] == ["none", "home", "away", "comfort", "sleep"]
    assert state.attributes["preset_mode"] == "comfort"
    await hass.services.async_call(
        "climate",
        "set_preset_mode",
        {"entity_id": entity_id, "preset_mode": "sleep"},
        blocking=True,
    )
    client.set_heatlink_temperature.assert_awaited_once_with("0", 17.5)
    assert hass.states.get(entity_id).attributes["preset_mode"] == "comfort"
    await hass.services.async_call(
        "climate", "set_preset_mode", {"entity_id": entity_id, "preset_mode": "none"}, blocking=True
    )
    client.clear_heatlink_override.assert_awaited_once_with("0")
    client.get_status.return_value["heatlinks"][0]["tte"] = 0
    await loaded.async_refresh()
    assert hass.states.get(entity_id).attributes["preset_mode"] == "none"


async def test_heatlink_invalid_and_ambiguous_presets(hass, loaded, client):
    entity_id = await add_heatlink(hass, loaded, client)
    client.get_sensors.return_value["heatlinks"][0]["presets"] = [
        {"id": 0, "te": 21},
        {"id": 1, "te": 21},
        {"id": 2, "te": True},
        {"id": 3, "te": 20.1},
        {"id": 4, "te": 20},
        "bad",
    ]
    loaded._inventory_at = 0
    await loaded.async_refresh()
    assert hass.states.get(entity_id).attributes["preset_modes"] == ["none", "home", "away"]
    assert hass.states.get(entity_id).attributes["preset_mode"] is None
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "climate",
            "set_preset_mode",
            {"entity_id": entity_id, "preset_mode": "comfort"},
            blocking=True,
        )
    client.set_heatlink_temperature.assert_not_awaited()
    # Explicit null config from status supersedes the last inventory configuration.
    client.get_status.return_value["heatlinks"][0]["presets"] = None
    await loaded.async_refresh()
    attributes = hass.states.get(entity_id).attributes
    assert "preset_modes" not in attributes
    assert "preset_mode" not in attributes
    assert attributes["supported_features"] == ClimateEntityFeature.TARGET_TEMPERATURE


async def test_radiator_inventory_removal_marks_unavailable(hass, loaded, client):
    entity_id = climate_id(hass)
    client.get_sensors.return_value = deepcopy(client.get_sensors.return_value)
    client.get_sensors.return_value["switches"] = [
        record for record in client.get_sensors.return_value["switches"] if record["id"] != 16
    ]
    loaded._inventory_at = 0
    await loaded.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE
