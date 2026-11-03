from copy import deepcopy
from unittest.mock import patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.homewizard_legacy.api import GatewayError
from custom_components.homewizard_legacy.const import DOMAIN
from custom_components.homewizard_legacy.diagnostics import async_get_config_entry_diagnostics


def entity_id(hass, platform, category, device_id, key):
    return er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"TEST-GATEWAY-001:{category}:{device_id}:{key}"
    )


async def test_setup_states_and_unload(hass, loaded, entry, client):
    states = hass.states.async_all()
    assert len(states) == 46
    cover = hass.states.get(entity_id(hass, "cover", "switches", "0", "cover"))
    assert cover.state == STATE_UNKNOWN
    assert "current_position" not in cover.attributes
    smoke = hass.states.get(entity_id(hass, "binary_sensor", "kakusensors", "1", "status"))
    assert smoke.state == STATE_UNKNOWN
    battery = hass.states.get(entity_id(hass, "binary_sensor", "thermometers", "1", "lowBattery"))
    assert battery.state == "on"
    assert hass.states.get(entity_id(hass, "sensor", "switches", "16", "tte")).state == "15"
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not loaded._listeners


async def test_discovery_removal_missing_status_recovery(hass, loaded, client):
    switch_id = entity_id(hass, "switch", "switches", "8", "status")
    client.get_status.return_value = deepcopy(client.get_status.return_value)
    client.get_status.return_value["switches"] = [
        r for r in client.get_status.return_value["switches"] if r["id"] != 8
    ]
    await loaded.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(switch_id).state == STATE_UNKNOWN
    assert client.get_sensors.call_count == 1
    client.get_status.side_effect = GatewayError("Offline")
    await loaded.async_refresh()
    assert hass.states.get(switch_id).state == STATE_UNAVAILABLE
    client.get_status.side_effect = None
    await loaded.async_refresh()
    assert hass.states.get(switch_id).state == STATE_UNKNOWN
    client.get_sensors.return_value = deepcopy(client.get_sensors.return_value)
    client.get_sensors.return_value["switches"] = [
        r for r in client.get_sensors.return_value["switches"] if r["id"] != 8
    ]
    client.get_sensors.return_value["switches"].append({"id": 99, "name": "New", "type": "switch"})
    loaded._inventory_at = 0
    await loaded.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(switch_id).state == STATE_UNAVAILABLE
    assert er.async_get(hass).async_get(switch_id) is not None
    new_id = entity_id(hass, "switch", "switches", "99", "status")
    assert hass.states.get(new_id).state == STATE_UNKNOWN
    assert (
        hass.states.get(entity_id(hass, "cover", "switches", "0", "cover")).state == STATE_UNKNOWN
    )


async def test_failed_inventory_retained(hass, loaded, client):
    before = deepcopy(loaded.inventory)
    loaded._inventory_at = 0
    client.get_sensors.side_effect = GatewayError("Offline")
    await loaded.async_refresh()
    assert loaded.inventory == before
    assert not loaded.last_update_success
    client.get_sensors.side_effect = None
    await loaded.async_refresh()
    assert loaded.last_update_success


@pytest.mark.parametrize(
    ("platform", "category", "device", "key", "service", "family", "action"),
    [
        ("switch", "switches", "8", "status", "turn_on", "sw", "on"),
        ("switch", "switches", "8", "status", "turn_off", "sw", "off"),
        ("cover", "switches", "0", "cover", "open_cover", "sf", "up"),
        ("cover", "switches", "0", "cover", "close_cover", "sf", "down"),
        ("cover", "switches", "0", "cover", "stop_cover", "sf", "stop"),
        ("button", "scenes", "0", "on", "press", "gp", "on"),
        ("button", "scenes", "0", "off", "press", "gp", "off"),
    ],
)
async def test_command_services(
    hass, loaded, client, platform, category, device, key, service, family, action
):
    with patch.object(
        loaded, "async_request_refresh", wraps=loaded.async_request_refresh
    ) as refresh:
        await hass.services.async_call(
            platform,
            service,
            {"entity_id": entity_id(hass, platform, category, device, key)},
            blocking=True,
        )
    client.command.assert_awaited_once_with(family, device, action)
    refresh.assert_awaited_once()


async def test_command_failure_not_retried(hass, loaded, client):
    client.command.side_effect = GatewayError("Command timeout")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": entity_id(hass, "switch", "switches", "8", "status")},
            blocking=True,
        )
    assert client.command.call_count == 1


async def test_safe_diagnostics(hass, loaded, entry):
    loaded.inventory[("cameras", "0")] = {
        "name": "private",
        "password": "secret",
        "url": "http://private/secret",
        "username": "private",
    }
    data = await async_get_config_entry_diagnostics(hass, entry)
    assert data["inventory_counts_by_type"]["cameras/unspecified"] == 1
    assert all(
        value not in str(data) for value in ["private", "secret", "TEST-GATEWAY", "gateway.test"]
    )


async def test_metadata_refresh_preserves_registry_identity(hass, loaded, client, entry):
    registry = dr.async_get(hass)
    identifier = (DOMAIN, "TEST-GATEWAY-001:switches:8")
    device = registry.async_get_device_by_identifier(identifier, entry.entry_id)
    original_id = device.id
    switch_id = entity_id(hass, "switch", "switches", "8", "status")
    client.get_sensors.return_value = deepcopy(client.get_sensors.return_value)
    for record in client.get_sensors.return_value["switches"]:
        if record["id"] == 8:
            record["name"] = "Renamed switch"
    loaded._inventory_at = 0
    await loaded.async_refresh()
    await hass.async_block_till_done()
    device = registry.async_get_device_by_identifier(identifier, entry.entry_id)
    assert device.id == original_id
    assert device.name == "Renamed switch"
    assert entity_id(hass, "switch", "switches", "8", "status") == switch_id
    weather = registry.async_get_device_by_identifier(
        (DOMAIN, "TEST-GATEWAY-001:weatherdisplays:0"), entry.entry_id
    )
    assert weather is not None
    assert (
        weather.via_device_id
        == registry.async_get_device_by_identifier((DOMAIN, "TEST-GATEWAY-001"), entry.entry_id).id
    )


async def test_missing_and_null_readings_do_not_reuse_inventory(hass, loaded, client):
    client.get_status.return_value = deepcopy(client.get_status.return_value)
    client.get_status.return_value["thermometers"] = [{"id": 1, "te": None, "lowBattery": None}]
    await loaded.async_refresh()
    assert (
        hass.states.get(entity_id(hass, "sensor", "thermometers", "1", "te")).state == STATE_UNKNOWN
    )
    assert (
        hass.states.get(entity_id(hass, "sensor", "thermometers", "1", "hu")).state == STATE_UNKNOWN
    )
    assert (
        hass.states.get(entity_id(hass, "binary_sensor", "thermometers", "1", "lowBattery")).state
        == STATE_UNKNOWN
    )


async def test_reloading_preserves_entity_registry(hass, loaded, entry):
    before = {state.entity_id for state in hass.states.async_all()}
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert {state.entity_id for state in hass.states.async_all()} == before
    assert not loaded._listeners
