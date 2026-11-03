from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.homewizard_legacy.api import AuthenticationError, GatewayError
from custom_components.homewizard_legacy.const import DOMAIN

INPUT = {"host": "gateway.test", "password": "test-secret"}


async def test_setup_and_duplicate(hass, client, entry):
    with patch("custom_components.homewizard_legacy.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=INPUT
        )
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "TEST-GATEWAY-001"
    assert result["data"]["host"] == "http://gateway.test"
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}, data=INPUT
    )
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    ("error", "expected"),
    [(AuthenticationError(), "invalid_auth"), (GatewayError(), "cannot_connect")],
)
async def test_setup_errors(hass, client, error, expected):
    client.get_sensors.side_effect = error
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}, data=INPUT
    )
    assert result["errors"] == {"base": expected}


async def test_reconfigure_preserves_identity(hass, entry, client):
    entry.add_to_hass(hass)
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_reload", return_value=True
    ) as reload:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
            data={"host": "new.test", "password": "new-secret"},
        )
    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == "TEST-GATEWAY-001"
    assert entry.data == {"host": "http://new.test", "password": "new-secret"}
    reload.assert_awaited_once()


async def test_reconfigure_wrong_gateway(hass, entry, client):
    entry.add_to_hass(hass)
    client.handshake.return_value = {"serial": "OTHER"}
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
        data=INPUT,
    )
    assert result["reason"] == "wrong_gateway"
    assert entry.data["password"] == "test-secret"


async def test_options(hass, entry, client):
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"scan_interval": 30}
    )
    assert result["data"] == {"scan_interval": 30}


async def test_reauth(hass, entry, client):
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert result["step_id"] == "reauth_confirm"
    with patch("homeassistant.config_entries.ConfigEntries.async_reload", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"host": "gateway.test", "password": "updated"},
        )
        await hass.async_block_till_done()
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "updated"
