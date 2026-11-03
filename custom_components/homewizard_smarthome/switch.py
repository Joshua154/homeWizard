"""Ordinary radio switches."""

from homeassistant.components.switch import SwitchEntity

from .entity import HomeWizardEntity, async_setup_entities
from .models import boolean_value

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_setup_entities(entry, async_add_entities, "switch", HomeWizardSwitch)


class HomeWizardSwitch(HomeWizardEntity, SwitchEntity):
    @property
    def is_on(self):
        return boolean_value(self.reported_value)

    async def async_turn_on(self, **kwargs):
        await self.async_command("sw", "on")

    async def async_turn_off(self, **kwargs):
        await self.async_command("sw", "off")
