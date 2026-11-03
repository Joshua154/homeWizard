"""Verified temperature/humidity and read-only radiator target readings."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfTemperature

from .entity import HomeWizardEntity, async_setup_entities
from .models import numeric_value

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_setup_entities(entry, async_add_entities, "sensor", HomeWizardSensor)


class HomeWizardSensor(HomeWizardEntity, SensorEntity):
    def __init__(self, coordinator, spec):
        super().__init__(coordinator, spec)
        self._attr_device_class = SensorDeviceClass(spec.kind)
        self._attr_native_unit_of_measurement = (
            PERCENTAGE if spec.kind == "humidity" else UnitOfTemperature.CELSIUS
        )
        self._attr_translation_key = {
            "te": "temperature",
            "hu": "humidity",
            "tte": "target_temperature",
        }[spec.key]
        if spec.key != "tte":
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        return numeric_value(self.reported_value)
