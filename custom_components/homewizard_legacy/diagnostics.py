"""Allowlisted structural diagnostics; never export raw gateway responses."""

from collections import Counter


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    # Unknown field names and values can contain personal data. Retain structure
    # and counts only, with type names restricted to a small API token alphabet.
    import re

    types = Counter()
    for (category, _), record in coordinator.inventory.items():
        safe_category = category if re.fullmatch(r"[a-z]{1,32}", category) else "unknown"
        kind = record.get("type", "unspecified")
        safe_kind = (
            kind if isinstance(kind, str) and re.fullmatch(r"[a-z]{1,24}", kind) else "unknown"
        )
        types[f"{safe_category}/{safe_kind}"] += 1
    return {
        "firmware": coordinator.firmware,
        "last_update_success": coordinator.last_update_success,
        "inventory_counts_by_type": dict(types),
        "entity_counts": dict(Counter(spec.platform for spec in coordinator.specs)),
    }
