"""Native scenes stored on the HomeWizard gateway."""

from homeassistant.components.scene import Scene

from .entity import HomeWizardEntity, async_setup_entities

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_setup_entities(entry, async_add_entities, "scene", HomeWizardScene)


class HomeWizardScene(HomeWizardEntity, Scene):
    async def async_activate(self, **kwargs):
        await self.async_command("gp", "on")
