"""Allowlisted weather, energy and read-only heating measurements."""

import re

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass

from .entity import HomeWizardEntity, async_setup_entities
from .measurements import sensor_definition
from .models import numeric_value

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_setup_entities(entry, async_add_entities, "sensor", HomeWizardSensor)


class HomeWizardSensor(HomeWizardEntity, SensorEntity):
    def __init__(self, coordinator, spec):
        super().__init__(coordinator, spec)
        self._attr_translation_key = self.definition.translation_key

    @property
    def definition(self):
        return sensor_definition(
            self.spec.category,
            self.spec.key,
            self.coordinator.inventory.get(self.spec.device_key, {}),
            self.coordinator.status.get(self.spec.device_key, {}),
        )

    @property
    def device_class(self):
        kind = self.definition.device_class
        return SensorDeviceClass(kind) if kind else None

    @property
    def native_unit_of_measurement(self):
        return self.definition.unit

    @property
    def state_class(self):
        state_class = self.definition.state_class
        return SensorStateClass(state_class) if state_class else None

    @property
    def native_value(self):
        if self.spec.category == "windmeters":
            if self.spec.key == "dir":
                value = self.reported_value
                if not isinstance(value, str):
                    return None
                match = re.fullmatch(
                    r"(?:N|NNE|NE|ENE|E|ESE|SE|SSE|S|SSW|SW|WSW|W|WNW|NW|NNW) (\d{1,3}(?:\.\d+)?)",
                    value,
                )
                if match and 0 <= (direction := float(match[1])) <= 360:
                    return direction
                return None
            if self.spec.key in {"ws", "ws+", "ws-", "gu"} and self.definition.unit is None:
                return None
        if self.spec.category == "energylinks" and self.spec.key.startswith(("s1.", "s2.")):
            if self.definition.unit is None:
                return None
        return numeric_value(self.reported_value)
