"""Classic HomeWizard dimmers, Hue and connected LED lights."""

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_HS_COLOR, ColorMode, LightEntity
from homeassistant.exceptions import HomeAssistantError

from .entity import HomeWizardEntity, async_setup_entities
from .models import boolean_value, numeric_value

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_setup_entities(entry, async_add_entities, "light", HomeWizardLight)


def _bounded(value, maximum):
    value = numeric_value(value)
    return value if value is not None and 0 <= value <= maximum else None


def _percent_brightness(value):
    """Convert reported percent to HA brightness without accepting invalid data."""
    value = _bounded(value, 100)
    return int(value * 255 / 100 + 0.5) if value is not None else None


def _brightness_percent(value):
    """Keep a nonzero HA brightness on when rounding to integer percent."""
    value = _bounded(value, 255)
    if value is None:
        raise HomeAssistantError("Invalid light brightness")
    return max(1, int(value * 100 / 255 + 0.5)) if value else 0


class HomeWizardLight(HomeWizardEntity, LightEntity):
    def __init__(self, coordinator, spec):
        super().__init__(coordinator, spec)
        mode = ColorMode.HS if spec.kind == "hue" else ColorMode.BRIGHTNESS
        self._attr_supported_color_modes = {mode}
        self._attr_color_mode = mode

    @property
    def is_on(self):
        return boolean_value(self.reported_value)

    @property
    def _color(self):
        color = self.coordinator.status.get(self.spec.device_key, {}).get("color")
        return color if isinstance(color, dict) else {}

    @property
    def brightness(self):
        value = (
            self._color.get("bri")
            if self.spec.kind in {"hue", "led2ch"}
            else self.coordinator.status.get(self.spec.device_key, {}).get("dimlevel")
        )
        return _percent_brightness(value)

    @property
    def hs_color(self):
        if self.spec.kind != "hue":
            return None
        hue = _bounded(self._color.get("hue"), 360)
        saturation = _bounded(self._color.get("sat"), 100)
        return (hue, saturation) if hue is not None and saturation is not None else None

    async def async_turn_on(self, **kwargs):
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if brightness is not None and _brightness_percent(brightness) == 0:
            await self.async_turn_off()
            return
        if self.spec.kind == "hue" and (ATTR_BRIGHTNESS in kwargs or ATTR_HS_COLOR in kwargs):
            hs = kwargs.get(ATTR_HS_COLOR, self.hs_color)
            level = (
                _brightness_percent(brightness)
                if brightness is not None
                else _bounded(self._color.get("bri"), 100)
            )
            if hs is None or level is None:
                raise HomeAssistantError("Current light color and brightness are unknown")
            hue, saturation = hs
            if _bounded(hue, 360) is None or _bounded(saturation, 100) is None:
                raise HomeAssistantError("Invalid light color")
            await self.coordinator.async_set_hue(
                self.spec.device_id,
                True,
                int(hue + 0.5),
                int(saturation + 0.5),
                int(level + 0.5),
            )
        elif brightness is not None:
            await self.coordinator.async_set_dimmer(
                self.spec.device_id, _brightness_percent(brightness)
            )
        elif self.spec.kind != "dimmer" or self.is_on is not True:
            # Repeating "on" on a running radio dimmer can enter dimming mode.
            await self.async_command("sw", "on")

    async def async_turn_off(self, **kwargs):
        await self.async_command("sw", "off")
