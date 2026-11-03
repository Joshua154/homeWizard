"""Somfy controls without invented physical feedback."""

from homeassistant.components.cover import CoverEntity, CoverEntityFeature

from .entity import HomeWizardEntity, async_setup_entities

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_setup_entities(entry, async_add_entities, "cover", HomeWizardCover)


class HomeWizardCover(HomeWizardEntity, CoverEntity):
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )
    _attr_is_closed = None
    _attr_current_cover_position = None

    async def async_open_cover(self, **kwargs):
        await self.async_command("sf", "up")

    async def async_close_cover(self, **kwargs):
        await self.async_command("sf", "down")

    async def async_stop_cover(self, **kwargs):
        await self.async_command("sf", "stop")
