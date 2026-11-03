"""UI setup, serial-based duplicates, reauthentication and reconfiguration."""

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import AuthenticationError, GatewayError, HomeWizardClient, normalize_address
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

try:
    import probatio as vol
except ModuleNotFoundError as err:
    if err.name != "probatio":
        raise
    # Older Home Assistant releases use voluptuous for flow schemas.
    import voluptuous as vol


class HomeWizardConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _async_form(self, step_id, user_input):
        errors = {}
        entry = None
        if step_id == "reconfigure":
            entry = self._get_reconfigure_entry()
        elif step_id == "reauth_confirm":
            entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                data = {
                    CONF_HOST: normalize_address(user_input[CONF_HOST]),
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                }
                client = HomeWizardClient(
                    async_get_clientsession(self.hass), data[CONF_HOST], data[CONF_PASSWORD]
                )
                identity = await client.handshake()
                await client.get_sensors()
            except ValueError:
                errors["base"] = "invalid_host"
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except GatewayError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(identity["serial"])
                if entry is not None:
                    if identity["serial"] != entry.unique_id:
                        return self.async_abort(reason="wrong_gateway")
                    if entry.update_listeners:
                        return self.async_update_and_abort(entry, data_updates=data)
                    return self.async_update_reload_and_abort(entry, data_updates=data)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="HomeWizard Smart Home", data=data)
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=entry.data[CONF_HOST] if entry else ""): str,
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }
        )
        return self.async_show_form(step_id=step_id, data_schema=schema, errors=errors)

    async def async_step_user(self, user_input=None):
        return await self._async_form("user", user_input)

    async def async_step_reconfigure(self, user_input=None):
        return await self._async_form("reconfigure", user_input)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        return await self._async_form("reauth_confirm", user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return HomeWizardOptionsFlow()


class HomeWizardOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                }
            ),
        )
