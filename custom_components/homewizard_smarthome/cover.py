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

    def __init__(self, coordinator, spec):
        super().__init__(coordinator, spec)
        if spec.kind == "asun":
            # ASUN stops by repeating the previous direction. Without reliable
            # direction feedback that could start moving a stationary blind.
            self._attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    @property
    def command_family(self):
        return "sw" if self.spec.kind in {"brel", "asun"} else "sf"

    async def async_open_cover(self, **kwargs):
        await self.async_command(self.command_family, "up")

    async def async_close_cover(self, **kwargs):
        await self.async_command(self.command_family, "down")

    async def async_stop_cover(self, **kwargs):
        await self.async_command(self.command_family, "stop")
