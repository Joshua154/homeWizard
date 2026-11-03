from collections import Counter

import pytest

from custom_components.homewizard_legacy.models import (
    boolean_value,
    discover,
    index_devices,
    numeric_value,
)

from .conftest import fixture


def test_captured_inventory_counts_and_identity():
    inventory = index_devices(fixture("get-sensors")["response"])
    status = index_devices(fixture("get-status")["response"])
    specs = discover(inventory, status)
    assert Counter(spec.platform for spec in specs) == {
        "switch": 5,
        "cover": 13,
        "sensor": 4,
        "binary_sensor": 22,
        "button": 2,
    }
    assert sum(spec.kind == "battery" for spec in specs) == 4
    assert sum(spec.key == "tte" for spec in specs) == 2
    assert len({spec.unique_id("serial") for spec in specs}) == len(specs)
    original_ids = {spec.unique_id("serial") for spec in specs}
    for record in inventory.values():
        record["name"] = "Renamed"
    assert {spec.unique_id("serial") for spec in discover(inventory, status)} == original_ids
    assert ("switches", "0") in inventory and ("kakusensors", "0") in inventory


@pytest.mark.parametrize("value", [None, "unknown", "", 0, 1, True, False, [], {}])
def test_unknown_boolean(value):
    assert boolean_value(value) is None


@pytest.mark.parametrize("value", [None, "15", True, float("nan"), float("inf")])
def test_unknown_number(value):
    assert numeric_value(value) is None


def test_discover_null_supported_field():
    specs = discover({("thermometers", "99"): {"te": None, "hu": None}}, {})
    assert {spec.key for spec in specs} == {"te", "hu"}
