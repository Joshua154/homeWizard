"""Gateway presets, native scenes, and additional cover protocols."""

from copy import deepcopy
from unittest.mock import patch

import pytest
from homeassistant.components.cover import CoverEntityFeature
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.homewizard_smarthome.api import AuthenticationError, GatewayError
from custom_components.homewizard_smarthome.const import DOMAIN

from .test_integration import entity_id


async def add_preset(hass, loaded, client, value=0):
    client.get_status.return_value = deepcopy(client.get_status.return_value)
    client.get_status.return_value["preset"] = value
    await loaded.async_refresh()
    await hass.async_block_till_done()
    return entity_id(hass, "select", "gateway", "0", "preset")


async def test_preset_discovery_command_and_gateway_device(hass, loaded, client, entry):
    preset = await add_preset(hass, loaded, client)
    assert hass.states.get(preset).state == "home"
    assert hass.states.get(preset).attributes["options"] == ["home", "away", "sleep", "holiday"]
    gateway = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, "TEST-GATEWAY-001"), entry.entry_id
    )
    assert er.async_get(hass).async_get(preset).device_id == gateway.id
    client.get_status.return_value["preset"] = 2
    with patch.object(
        loaded, "async_request_refresh", wraps=loaded.async_request_refresh
    ) as refresh:
        await hass.services.async_call(
            "select", "select_option", {"entity_id": preset, "option": "sleep"}, blocking=True
        )
    client.set_preset.assert_awaited_once_with(2)
    refresh.assert_awaited_once()
    assert hass.states.get(preset).state == "sleep"
    loaded._inventory_at = 0
    await loaded.async_refresh()
    assert hass.states.get(preset).state == "sleep"
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entity_id(hass, "select", "gateway", "0", "preset") == preset


@pytest.mark.parametrize("value", [None, True, -1, 4, "2", {}, []])
async def test_invalid_preset_state_is_unknown(hass, loaded, client, value):
    preset = await add_preset(hass, loaded, client, value)
    assert hass.states.get(preset).state == STATE_UNKNOWN


async def test_preset_missing_report_and_outage(hass, loaded, client):
    preset = await add_preset(hass, loaded, client)
    del client.get_status.return_value["preset"]
    await loaded.async_refresh()
    assert hass.states.get(preset).state == STATE_UNKNOWN
    client.get_status.side_effect = GatewayError("Offline")
    await loaded.async_refresh()
    assert hass.states.get(preset).state == STATE_UNAVAILABLE
    client.get_status.side_effect = None
    client.get_status.return_value["preset"] = 3
    await loaded.async_refresh()
    assert hass.states.get(preset).state == "holiday"


async def test_preset_failure_no_retry_or_optimistic_state(hass, loaded, client):
    preset = await add_preset(hass, loaded, client)
    client.set_preset.side_effect = GatewayError("Timed out")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "select", "select_option", {"entity_id": preset, "option": "away"}, blocking=True
        )
    client.set_preset.assert_awaited_once_with(1)
    assert loaded.status[("gateway", "0")]["preset"] == 0


async def test_control_authentication_failure_starts_reauth(hass, loaded, client, entry):
    await add_preset(hass, loaded, client)
    client.set_preset.side_effect = AuthenticationError("Denied")
    with patch.object(type(entry), "async_start_reauth") as reauth:
        with pytest.raises(HomeAssistantError):
            await loaded.async_set_preset(1)
    reauth.assert_called_once_with(hass)
    assert not loaded.last_update_success


async def test_scene_activation_retains_legacy_buttons(hass, loaded, client):
    scene = entity_id(hass, "scene", "scenes", "0", "activate")
    assert hass.states.get(scene).state == STATE_UNKNOWN
    await hass.services.async_call("scene", "turn_on", {"entity_id": scene}, blocking=True)
    client.command.assert_awaited_once_with("gp", "0", "on")
    assert hass.states.get(entity_id(hass, "button", "scenes", "0", "off")) is not None


@pytest.mark.parametrize("kind,feature", [("brel", True), ("asun", False)])
async def test_additional_covers(hass, loaded, client, kind, feature):
    client.get_sensors.return_value = deepcopy(client.get_sensors.return_value)
    client.get_sensors.return_value["switches"].append({"id": 50, "type": kind})
    loaded._inventory_at = 0
    await loaded.async_refresh()
    await hass.async_block_till_done()
    cover = entity_id(hass, "cover", "switches", "50", "cover")
    state = hass.states.get(cover)
    assert state.state == STATE_UNKNOWN
    assert bool(state.attributes["supported_features"] & CoverEntityFeature.STOP) == feature
    for service, command in [("open_cover", "up"), ("close_cover", "down")]:
        await hass.services.async_call("cover", service, {"entity_id": cover}, blocking=True)
        client.command.assert_awaited_with("sw", "50", command)
    if feature:
        await hass.services.async_call("cover", "stop_cover", {"entity_id": cover}, blocking=True)
        client.command.assert_awaited_with("sw", "50", "stop")
