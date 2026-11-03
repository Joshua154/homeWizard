"""HomeWizard smartHome integration."""

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_SCAN_INTERVAL
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AuthenticationError, GatewayError, HomeWizardClient
from .const import DEFAULT_SCAN_INTERVAL, PLATFORMS
from .coordinator import HomeWizardCoordinator


async def async_setup_entry(hass, entry):
    client = HomeWizardClient(
        async_get_clientsession(hass), entry.data[CONF_HOST], entry.data[CONF_PASSWORD]
    )
    try:
        identity = await client.handshake()
    except AuthenticationError:
        raise ConfigEntryAuthFailed("Gateway authentication failed") from None
    except GatewayError:
        raise ConfigEntryNotReady("Cannot identify HomeWizard gateway") from None
    if identity["serial"] != entry.unique_id:
        raise ConfigEntryNotReady(
            "A different gateway is at this address; reconfigure the integration"
        )
    coordinator = HomeWizardCoordinator(
        hass, entry, client, identity, entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
