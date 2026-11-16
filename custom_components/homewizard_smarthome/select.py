"""HomeWizard's mutually exclusive, gateway-wide presets."""

from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import ServiceValidationError

from .const import PRESETS
from .entity import HomeWizardEntity, async_setup_entities

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_setup_entities(entry, async_add_entities, "select", HomeWizardPreset)


class HomeWizardPreset(HomeWizardEntity, SelectEntity):
    _attr_translation_key = "preset"
    _attr_options = list(PRESETS)

    @property
    def current_option(self):
        value = self.reported_value
        if type(value) is int and 0 <= value < len(PRESETS):
            return PRESETS[value]
        return None

    async def async_select_option(self, option):
        if option not in PRESETS:
            raise ServiceValidationError("Unsupported HomeWizard preset")
        await self.coordinator.async_set_preset(PRESETS.index(option))
