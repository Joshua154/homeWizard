"""Lighting contracts based on classic gateway implementations; no live commands."""

from copy import deepcopy
from unittest.mock import patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.exceptions import HomeAssistantError

from custom_components.homewizard_smarthome.api import GatewayError
from tests.test_integration import entity_id


@pytest.fixture
async def lights(hass, entry, client):
    client.get_sensors.return_value = deepcopy(client.get_sensors.return_value)
    client.get_status.return_value = deepcopy(client.get_status.return_value)
    for device_id, kind, values in (
        (92, "led2ch", {"color": {"hue": 80, "sat": 0, "bri": 30}}),
        (90, "dimmer", {"dimlevel": 50}),
        (91, "hue", {"color": {"hue": 210, "sat": 40, "bri": 80}}),
    ):
        client.get_sensors.return_value["switches"].append(
            {"id": device_id, "name": f"Test {kind}", "type": kind, "status": "off", **values}
        )
        client.get_status.return_value["switches"].append(
            {"id": device_id, "status": "on", **values}
        )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.runtime_data


def light_id(hass, device_id=90):
    return entity_id(hass, "light", "switches", str(device_id), "status")


async def call_light(hass, device_id=90, service="turn_on", **kwargs):
    await hass.services.async_call(
        "light", service, {"entity_id": light_id(hass, device_id), **kwargs}, blocking=True
    )


async def test_lighting_discovery_and_units(hass, lights):
    dimmer = hass.states.get(light_id(hass))
    hue = hass.states.get(light_id(hass, 91))
    assert dimmer.state == "on"
    assert dimmer.attributes["brightness"] == 128
    assert dimmer.attributes["supported_color_modes"] == ["brightness"]
    assert hue.attributes["brightness"] == 204
    assert hue.attributes["hs_color"] == (210, 40)
    assert hue.attributes["supported_color_modes"] == ["hs"]
    assert entity_id(hass, "switch", "switches", "8", "status") is not None
    assert entity_id(hass, "switch", "switches", "90", "status") is None


@pytest.mark.parametrize(("brightness", "percent"), [(1, 1), (128, 50), (255, 100)])
async def test_dimmer_brightness_command(hass, lights, client, brightness, percent):
    with patch.object(lights, "async_request_refresh") as refresh:
        await call_light(hass, brightness=brightness)
    client.set_dimmer.assert_awaited_once_with("90", percent)
    client.command.assert_not_awaited()
    refresh.assert_awaited_once()
    # No optimistic state: continue displaying the gateway's reported level.
    assert hass.states.get(light_id(hass)).attributes["brightness"] == 128


async def test_dimmer_on_and_off(hass, lights, client):
    await call_light(hass)
    client.command.assert_not_awaited()  # Repeated "on" can trigger dimming mode.
    client.get_status.return_value["switches"][-2]["status"] = "off"
    await lights.async_refresh()
    await call_light(hass)
    client.command.assert_awaited_once_with("sw", "90", "on")
    client.command.reset_mock()
    await call_light(hass, brightness=0)
    client.command.assert_awaited_once_with("sw", "90", "off")
    client.set_dimmer.assert_not_awaited()


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"brightness": 255}, (210, 40, 100)),
        ({"hs_color": (90, 75)}, (90, 75, 80)),
        ({"hs_color": (359.7, 20.6), "brightness": 128}, (360, 21, 50)),
    ],
)
async def test_hue_partial_commands_preserve_reported_components(
    hass, lights, client, kwargs, expected
):
    with patch.object(lights, "async_request_refresh") as refresh:
        await call_light(hass, 91, **kwargs)
    client.set_hue.assert_awaited_once_with("91", True, *expected)
    client.command.assert_not_awaited()
    refresh.assert_awaited_once()


@pytest.mark.parametrize("service", ["turn_on", "turn_off"])
async def test_hue_power_uses_switch_route(hass, lights, client, service):
    await call_light(hass, 91, service)
    client.command.assert_awaited_once_with("sw", "91", service.removeprefix("turn_"))
    client.set_hue.assert_not_awaited()


@pytest.mark.parametrize("color", [None, {}, {"hue": 210, "sat": 40, "bri": None}])
async def test_hue_unknown_components_do_not_send_defaults(hass, lights, client, color):
    client.get_status.return_value["switches"][-1]["color"] = color
    await lights.async_refresh()
    with pytest.raises(HomeAssistantError, match="unknown"):
        await call_light(hass, 91, hs_color=(60, 80))
    client.set_hue.assert_not_awaited()
    client.command.assert_not_awaited()
    await call_light(hass, 91, hs_color=(60, 80), brightness=255)
    client.set_hue.assert_awaited_once_with("91", True, 60, 80, 100)


@pytest.mark.parametrize("value", [None, True, "50", -1, 101, float("inf")])
async def test_invalid_brightness_feedback_unknown(hass, lights, client, value):
    record = client.get_status.return_value["switches"][-2]
    record["dimlevel"] = value
    record["status"] = None
    await lights.async_refresh()
    state = hass.states.get(light_id(hass))
    assert state.state == STATE_UNKNOWN
    assert state.attributes.get("brightness") is None


async def test_missing_status_and_removed_light(hass, lights, client):
    client.get_status.return_value["switches"] = [
        record for record in client.get_status.return_value["switches"] if record["id"] != 90
    ]
    await lights.async_refresh()
    assert hass.states.get(light_id(hass)).state == STATE_UNKNOWN
    assert hass.states.get(light_id(hass)).attributes.get("brightness") is None
    client.get_sensors.return_value["switches"] = [
        record for record in client.get_sensors.return_value["switches"] if record["id"] != 90
    ]
    lights._inventory_at = 0
    await lights.async_refresh()
    assert hass.states.get(light_id(hass)).state == STATE_UNAVAILABLE


async def test_led2ch_brightness_without_guessed_color_temperature(hass, lights, client):
    state = hass.states.get(light_id(hass, 92))
    assert state.attributes["brightness"] == 77
    assert state.attributes["supported_color_modes"] == ["brightness"]
    assert "hs_color" not in state.attributes
    assert "color_temp_kelvin" not in state.attributes
    await call_light(hass, 92, brightness=255)
    client.set_dimmer.assert_awaited_once_with("92", 100)
    client.set_hue.assert_not_awaited()


async def test_brightness_timeout_is_not_retried(hass, lights, client):
    client.set_dimmer.side_effect = GatewayError("Command timed out")
    with patch.object(lights, "async_request_refresh") as refresh:
        with pytest.raises(HomeAssistantError, match="delivery may be uncertain"):
            await call_light(hass, brightness=255)
    client.set_dimmer.assert_awaited_once_with("90", 100)
    client.command.assert_not_awaited()
    refresh.assert_not_awaited()
    assert hass.states.get(light_id(hass)).state == STATE_UNAVAILABLE
