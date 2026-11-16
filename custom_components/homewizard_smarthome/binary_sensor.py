"""Radio detector reports and diagnostic low battery indicators."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory

from .entity import HomeWizardEntity, async_setup_entities
from .models import boolean_value

PARALLEL_UPDATES = 0
CLASSES = {
    "motion": BinarySensorDeviceClass.MOTION,
    "contact": BinarySensorDeviceClass.DOOR,
    "smoke": BinarySensorDeviceClass.SMOKE,
    "battery": BinarySensorDeviceClass.BATTERY,
    "moisture": BinarySensorDeviceClass.MOISTURE,
    "heat": BinarySensorDeviceClass.HEAT,
    "running": BinarySensorDeviceClass.RUNNING,
}


async def async_setup_entry(hass, entry, async_add_entities):
    async_setup_entities(entry, async_add_entities, "binary_sensor", HomeWizardBinarySensor)


class HomeWizardBinarySensor(HomeWizardEntity, BinarySensorEntity):
    def __init__(self, coordinator, spec):
        super().__init__(coordinator, spec)
        self._attr_device_class = CLASSES.get(spec.kind)
        if spec.kind == "battery":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
            self._attr_translation_key = "low_battery"
        elif spec.category == "heatlinks":
            self._attr_translation_key = {
                "heating": "heating",
                "pump": "pump",
                "dhw": "hot_water",
            }[spec.key]
        elif spec.kind == "doorbell":
            self._attr_translation_key = "doorbell"

    @property
    def is_on(self):
        return boolean_value(self.reported_value)
