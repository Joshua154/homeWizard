# HomeWizard Smart Home (Legacy)

Local Home Assistant custom integration for the original HomeWizard Smart Home
gateway. HomeWizard Energy products use a different API and integration.

## Install locally

1. Copy `custom_components/homewizard_legacy` into your Home Assistant
   configuration directory's `custom_components` folder.
2. Restart Home Assistant.
3. Open **Settings → Devices & services → Add integration** and select
   **HomeWizard Smart Home (Legacy)**.
4. Enter the gateway's hostname/IP (optional HTTP(S) scheme and port) and password.
   Do not include the password in the address.

Use the integration's **Reconfigure** menu to change the address/password while
preserving entity IDs. The replacement address must identify the same gateway.
Use **Configure** to change status polling from the default 10 seconds (5–300).
Inventory refreshes every five minutes, adding newly discovered entities.

## Supported devices

| Device | Entities |
| --- | --- |
| Ordinary switches | On/off switch |
| Somfy | Cover with open, close, stop; unknown position |
| Thermometers | Temperature/humidity when the fields exist |
| Radiators | Read-only target temperature (`tte`) |
| Motion/contact/smoke detectors | Corresponding binary sensor |
| Light detectors | Generic binary sensor; polarity not inferred |
| Reported `lowBattery` fields | Diagnostic battery binary sensor |
| Groups/scenes | Separate activate and deactivate buttons |

The captured firmware 3.403 inventory creates **46 entities**: 5 switches,
13 covers, 2 radiator readings, 18 detector readings, 2 thermometer readings,
4 battery indicators and 2 group buttons. The second thermometer has no
temperature/humidity fields and therefore only exposes its battery indicator.

Missing/null readings remain unknown. Communication failures make entities
unavailable until recovery. Devices removed from a successful inventory become
unavailable, retaining their registry entries. Covers missing from status remain
registered. Polling can miss short radio events; this is not an event stream.

Commands refresh reported state and are never retried automatically after a
timeout. Cover commands do not report inferred position. Wind/rain measurements,
dimmer brightness, radiator control, cameras and other unsupported families are
deferred. `/timers`, `/notifications`, and optional configuration/history routes
are excluded from polling. See [ENDPOINTS.md](ENDPOINTS.md) for the API evidence.

## Development and validation

Python 3.14.2 or later is required by the pinned Home Assistant development
baseline, **2026.10.4**. With [uv](https://docs.astral.sh/uv/) installed:

```sh
uv sync --locked
uv run pytest -q
uv run ruff check custom_components tests scripts
uv run python scripts/package.py
```

Integration source retains Python 3.13-compatible syntax, enforced by Ruff's
target version and a syntax regression test. The full integration tests run
against the newer development baseline above; this does not establish full
compatibility with older Home Assistant releases.

Config flows use `probatio` when available and fall back to `voluptuous` on
older Home Assistant installations, including 2026.1.1.

Tests use sanitized gateway fixtures and mocked HTTP/device commands. No live
device commands were executed during implementation. Live command testing, if
later performed, remains restricted to switch ID 8 with its initial state
recorded and restored.

Validation on 2026-11-03: **57 tests passed** on Home Assistant 2026.10.4 with
Python 3.14.10; Ruff passed; the matching Home Assistant `hassfest` validator
reported **0 invalid integrations**. Tests verify the captured entity counts,
setup/reconfiguration/reauthentication, registry identity across renames/reloads,
later discovery, removals, missing/null readings, outages/recovery, command
routing, serialization, and no command retry after a lost response. Physical
commands and installation in a running user Home Assistant instance remain
unverified.

`scripts/capture_fixtures.pl` is an explicit read-only developer utility using the
ignored local Postman collection. It writes only allowlisted, anonymized fields;
camera records, radio codes, addresses, credentials, timestamps and device names
are excluded. Fixtures preserve numeric API IDs to test overlapping categories.
Diagnostics provide firmware and counts by API category/type, without config
entry data or raw responses.

The ZIP packager includes only integration assets, this README, the API reference,
the license and HACS metadata. It excludes the credential-bearing Postman
collection and local developer tooling.

## Publishing status

This is a local development release, not yet published or submitted to HACS.
The manifest's `example.com` documentation/issue URLs are **placeholders**;
`codeowners` must be populated with the real maintainer before publishing.
Original icon assets are included under the MIT license. Complete repository
metadata and the [HACS requirements](https://www.hacs.xyz/docs/publish/integration/)
before a separate publishing step.
