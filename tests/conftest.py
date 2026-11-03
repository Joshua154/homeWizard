"""Sanitized gateway fixtures; no test contacts a real device."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homewizard_smarthome.const import DOMAIN


def fixture(name):
    return json.loads((Path(__file__).parent / "fixtures" / f"{name}.json").read_text())


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def client():
    client = AsyncMock()
    client.handshake.return_value = fixture("handshake")["response"]
    client.get_sensors.return_value = fixture("get-sensors")["response"]
    client.get_status.return_value = fixture("get-status")["response"]
    with (
        patch("custom_components.homewizard_smarthome.HomeWizardClient", return_value=client),
        patch(
            "custom_components.homewizard_smarthome.config_flow.HomeWizardClient", return_value=client
        ),
    ):
        yield client


@pytest.fixture
def entry():
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="TEST-GATEWAY-001",
        data={"host": "http://gateway.test", "password": "test-secret"},
    )


@pytest.fixture
async def loaded(hass, entry, client):
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.runtime_data
