"""Shared stable identity, availability and dynamic platform discovery."""

from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


@callback
def async_setup_entities(entry, async_add_entities, platform, entity_class):
    coordinator = entry.runtime_data
    added = set()

    @callback
    def discover_entities():
        specs = {spec for spec in coordinator.specs if spec.platform == platform}
        new_specs = specs - added
        if new_specs:
            async_add_entities(
                [
                    entity_class(coordinator, spec)
                    for spec in sorted(
                        new_specs, key=lambda spec: spec.unique_id(coordinator.serial)
                    )
                ]
            )
            added.update(new_specs)

    entry.async_on_unload(coordinator.async_add_listener(discover_entities))
    discover_entities()


class HomeWizardEntity(CoordinatorEntity):
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator, spec):
        super().__init__(coordinator)
        self.spec = spec
        self._attr_unique_id = spec.unique_id(coordinator.serial)
        self._last_name = None

    @property
    def device_info(self):
        record = self.coordinator.inventory.get(self.spec.device_key, {})
        self._last_name = record.get("name", self._last_name)
        return DeviceInfo(
            identifiers={
                (DOMAIN, f"{self.coordinator.serial}:{self.spec.category}:{self.spec.device_id}")
            },
            name=self._last_name or f"{self.spec.category} {self.spec.device_id}",
            manufacturer="HomeWizard",
            model=record.get("type", self.spec.category),
            via_device=(DOMAIN, self.coordinator.serial),
        )

    @property
    def available(self):
        return super().available and self.spec.device_key in self.coordinator.inventory

    @property
    def reported_value(self):
        status = self.coordinator.status.get(self.spec.device_key, {})
        if self.spec.key == "lowBattery" and self.spec.key not in status:
            return self.coordinator.inventory.get(self.spec.device_key, {}).get(self.spec.key)
        return status.get(self.spec.key)

    async def async_command(self, family, action):
        await self.coordinator.async_command(family, self.spec.device_id, action)
