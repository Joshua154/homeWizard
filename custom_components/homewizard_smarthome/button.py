"""Group activation/deactivation; the API reports no group state."""

from homeassistant.components.button import ButtonEntity

from .entity import HomeWizardEntity, async_setup_entities

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_setup_entities(entry, async_add_entities, "button", HomeWizardButton)


class HomeWizardButton(HomeWizardEntity, ButtonEntity):
    def __init__(self, coordinator, spec):
        super().__init__(coordinator, spec)
        self._attr_translation_key = "activate" if spec.key == "on" else "deactivate"

    async def async_press(self):
        await self.async_command("gp", self.spec.key)
