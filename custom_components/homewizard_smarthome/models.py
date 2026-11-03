"""Pure discovery/state mappings for the verified firmware response fields."""

import math
from dataclasses import dataclass

DeviceKey = tuple[str, str]


def index_devices(data: dict) -> dict[DeviceKey, dict]:
    return {
        (category, str(record["id"])): record
        for category, records in data.items()
        if isinstance(records, list)
        for record in records
    }


@dataclass(frozen=True)
class EntitySpec:
    category: str
    device_id: str
    key: str
    platform: str
    kind: str = ""

    @property
    def device_key(self) -> DeviceKey:
        return self.category, self.device_id

    def unique_id(self, serial: str) -> str:
        return f"{serial}:{self.category}:{self.device_id}:{self.key}"


def discover(inventory: dict[DeviceKey, dict], status: dict[DeviceKey, dict]) -> set[EntitySpec]:
    specs = set()
    for (category, device_id), record in inventory.items():

        def add(key: str, platform: str, kind: str = "") -> None:
            specs.add(EntitySpec(category, device_id, key, platform, kind))

        kind = record.get("type", "")
        if category == "switches":
            if kind == "switch":
                add("status", "switch")
            elif kind == "somfy":
                add("cover", "cover")
            elif kind == "radiator":
                add("tte", "sensor", "temperature")
        elif category == "kakusensors" and kind in {"motion", "contact", "smoke", "light"}:
            add("status", "binary_sensor", kind)
        elif category == "thermometers":
            fields = record.keys() | status.get((category, device_id), {}).keys()
            for key, sensor_kind in (("te", "temperature"), ("hu", "humidity")):
                if key in fields:
                    add(key, "sensor", sensor_kind)
        elif category == "scenes":
            add("on", "button")
            add("off", "button")
        if category in {
            "thermometers",
            "rainmeters",
            "windmeters",
            "weatherdisplays",
            "kakusensors",
            "switches",
        }:
            if "lowBattery" in record or "lowBattery" in status.get((category, device_id), {}):
                add("lowBattery", "binary_sensor", "battery")
    return specs


def boolean_value(value):
    """Explicit API values; missing, null and unfamiliar values stay unknown."""
    if value in ("yes", "on"):
        return True
    if value in ("no", "off"):
        return False
    return None


def numeric_value(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return value
    return None
