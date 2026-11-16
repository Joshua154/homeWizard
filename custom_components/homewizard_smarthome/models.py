"""Pure discovery/state mappings for the verified firmware response fields."""

import math
from dataclasses import dataclass

from .measurements import measurement_fields

DeviceKey = tuple[str, str]


def index_devices(data: dict) -> dict[DeviceKey, dict]:
    devices = {
        (category, str(record["id"])): record
        for category, records in data.items()
        if isinstance(records, list)
        for record in records
    }
    if "preset" in data:
        devices[("gateway", "0")] = {"preset": data["preset"]}
    return devices


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
        if not isinstance(kind, str):
            kind = ""
        if category == "switches":
            if kind in {"switch", "virtual"}:
                add("status", "switch")
            elif kind in {"somfy", "brel", "asun"}:
                add("cover", "cover", kind)
            elif kind == "radiator":
                add("tte", "sensor", "temperature")
                add("climate", "climate", "radiator")
            elif kind in {"dimmer", "hue", "led2ch"}:
                add("status", "light", kind)
        elif category == "heatlinks":
            add("climate", "climate", "heatlink")
        elif category == "somfy":
            add("cover", "cover", "somfy")
        elif category == "gateway":
            add("preset", "select")
        elif category == "scenes":
            add("on", "button")
            add("off", "button")
            add("activate", "scene")
        for key, platform, sensor_kind in measurement_fields(
            category, record, status.get((category, device_id), {})
        ):
            add(key, platform, sensor_kind)
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
