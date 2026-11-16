"""Temperature controls for classic radiator valves and HeatLinks."""

from homeassistant.components.climate import (
    PRESET_AWAY,
    PRESET_COMFORT,
    PRESET_HOME,
    PRESET_NONE,
    PRESET_SLEEP,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.exceptions import ServiceValidationError

from .const import (
    HEATLINK_MAX_TEMP,
    HEATLINK_MIN_TEMP,
    HEATLINK_TEMP_STEP,
    RADIATOR_MAX_TEMP,
    RADIATOR_MIN_TEMP,
    RADIATOR_TEMP_STEP,
)
from .entity import HomeWizardEntity, async_setup_entities
from .models import numeric_value

PARALLEL_UPDATES = 0
HEATLINK_PRESETS = (PRESET_HOME, PRESET_AWAY, PRESET_COMFORT, PRESET_SLEEP)


async def async_setup_entry(hass, entry, async_add_entities):
    async_setup_entities(entry, async_add_entities, "climate", HomeWizardClimate)


class HomeWizardClimate(HomeWizardEntity, ClimateEntity):
    """Set a temperature without inventing valve feedback or mode commands."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, spec):
        super().__init__(coordinator, spec)
        self._heatlink = spec.category == "heatlinks"
        self._attr_hvac_modes = (
            [HVACMode.HEAT, HVACMode.AUTO] if self._heatlink else [HVACMode.HEAT]
        )
        self._attr_min_temp = HEATLINK_MIN_TEMP if self._heatlink else RADIATOR_MIN_TEMP
        self._attr_max_temp = HEATLINK_MAX_TEMP if self._heatlink else RADIATOR_MAX_TEMP
        self._attr_target_temperature_step = (
            HEATLINK_TEMP_STEP if self._heatlink else RADIATOR_TEMP_STEP
        )

    @property
    def _status(self):
        return self.coordinator.status.get(self.spec.device_key, {})

    @property
    def _presets(self):
        if not self._heatlink:
            return {}
        inventory = self.coordinator.inventory.get(self.spec.device_key, {})
        records = self._status.get("presets", inventory.get("presets"))
        if not isinstance(records, list):
            return {}
        presets = {}
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            preset_id = record.get("id", index)
            temperature = numeric_value(record.get("te"))
            if (
                type(preset_id) is int
                and 0 <= preset_id < len(HEATLINK_PRESETS)
                and temperature is not None
                and self.min_temp <= temperature <= self.max_temp
                and abs(
                    temperature / self.target_temperature_step
                    - round(temperature / self.target_temperature_step)
                )
                < 1e-7
            ):
                presets[HEATLINK_PRESETS[preset_id]] = temperature
        return presets

    @property
    def supported_features(self):
        features = ClimateEntityFeature.TARGET_TEMPERATURE
        if self._presets:
            features |= ClimateEntityFeature.PRESET_MODE
        return features

    @property
    def preset_modes(self):
        presets = self._presets
        return [PRESET_NONE, *presets] if presets else None

    @property
    def preset_mode(self):
        if not self._presets:
            return None
        if self.hvac_mode == HVACMode.AUTO:
            return PRESET_NONE
        # Equal configured temperatures cannot identify which preset was chosen.
        matches = [
            name for name, value in self._presets.items() if value == self.target_temperature
        ]
        return matches[0] if len(matches) == 1 else None

    @property
    def hvac_mode(self):
        if self._heatlink:
            target = numeric_value(self._status.get("tte"))
            if target == 0:
                return HVACMode.AUTO
            return HVACMode.HEAT if target is not None and target > 0 else None
        return HVACMode.HEAT

    @property
    def target_temperature(self):
        target = numeric_value(self._status.get("tte"))
        if self._heatlink:
            # Zero explicitly means no override; rsp is the thermostat setpoint.
            if target == 0:
                return numeric_value(self._status.get("rsp"))
            return target if target is not None and target > 0 else None
        return target

    @property
    def current_temperature(self):
        # Classic radio valves do not expose their internal room thermometer.
        return numeric_value(self._status.get("rte")) if self._heatlink else None

    @property
    def hvac_action(self):
        if self._heatlink:
            heating = self._status.get("heating")
            if heating == "on":
                return HVACAction.HEATING
            if heating == "off":
                return HVACAction.IDLE
        return None

    async def async_set_hvac_mode(self, hvac_mode):
        """Resume HeatLink thermostat control, or hold its current target."""
        if hvac_mode not in self.hvac_modes:
            raise ServiceValidationError("Unsupported HVAC mode")
        if self._heatlink:
            if hvac_mode == HVACMode.AUTO:
                await self.coordinator.async_clear_heatlink_override(self.spec.device_id)
            elif self.hvac_mode != HVACMode.HEAT:
                await self.async_set_temperature(temperature=self.target_temperature)

    async def async_set_preset_mode(self, preset_mode):
        """Apply a returned HeatLink preset temperature or resume thermostat control."""
        if preset_mode not in (self.preset_modes or []):
            raise ServiceValidationError("Unsupported HeatLink preset")
        if preset_mode == PRESET_NONE:
            await self.coordinator.async_clear_heatlink_override(self.spec.device_id)
        else:
            await self.async_set_temperature(temperature=self._presets[preset_mode])

    async def async_set_temperature(self, **kwargs):
        """Send one validated temperature command and refresh reported state."""
        if kwargs.get("hvac_mode", HVACMode.HEAT) != HVACMode.HEAT:
            raise ServiceValidationError("Temperature overrides require heat mode")
        temperature = numeric_value(kwargs.get(ATTR_TEMPERATURE))
        if temperature is None or not self.min_temp <= temperature <= self.max_temp:
            raise ServiceValidationError(
                f"Temperature must be between {self.min_temp} and {self.max_temp} °C"
            )
        # Reject unsupported precision instead of silently changing the request.
        increments = temperature / self.target_temperature_step
        if abs(increments - round(increments)) > 1e-7:
            raise ServiceValidationError(
                f"Temperature must use {self.target_temperature_step} °C increments"
            )
        if self._heatlink:
            await self.coordinator.async_set_heatlink_temperature(self.spec.device_id, temperature)
        else:
            await self.coordinator.async_set_radiator_temperature(self.spec.device_id, temperature)
