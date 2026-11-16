# HomeWizard smartHome

Local Home Assistant custom integration for the original HomeWizard smartHome
gateway. HomeWizard Energy products use a different API and integration.

## Install locally

1. Copy `custom_components/homewizard_smarthome` into your Home Assistant
   configuration directory's `custom_components` folder.
2. Restart Home Assistant.
3. Open **Settings → Devices & services → Add integration** and select
   **HomeWizard smartHome**.
4. Enter the gateway's hostname/IP (optional HTTP(S) scheme and port) and password.
   Do not include the password in the address.

When upgrading from a differently named integration domain, remove its entry
through **Settings → Devices & services** and remove its old custom component
folder before installing this version. Add **HomeWizard smartHome** again after
restarting. The domain change creates new registry identities; check entity IDs
and update affected dashboards and automations.

Use the integration's **Reconfigure** menu to change the address/password while
preserving entity IDs. The replacement address must identify the same gateway.
Use **Configure** to change status polling from the default 10 seconds (5–300).
Inventory refreshes every five minutes, adding newly discovered entities.

## Supported devices

| Device | Entities and controls |
| --- | --- |
| Ordinary and virtual switches | On/off switches |
| Dimmers | Lights with on/off and brightness |
| Hue lights reported as switches | On/off, brightness, hue and saturation |
| Connected `led2ch` lights | On/off and brightness |
| Somfy and Brel | Covers with open, close and stop; position remains unknown |
| ASUN | Covers with open and close |
| Radiators | Climate temperature control, 5–28 °C in 0.5 °C steps; existing target sensors retained |
| HeatLink | Climate temperature control, 5–30 °C in 0.5 °C steps; AUTO returns control to the wall thermostat; reported Home/Away/Comfort/Sleep presets |
| Gateway presets | Select Home, Away, Sleep or Holiday when preset support is reported |
| Groups/scenes | Native HA scenes, plus existing activate/deactivate buttons |
| Thermometers | Temperature, humidity and returned extrema |
| Wind meters | Speed, gusts, direction, wind chill, temperature and returned speed extrema |
| Rain meters | Rain today and in the last three hours |
| UV meters | UV index and returned maximum |
| Energy meters | Power, daily energy and returned power extrema |
| EnergyLink | Net/consumed power and daily energy, gas, and supported S1/S2 electricity or water channels |
| HeatLink readings | Room/boiler temperature, wall thermostat setpoint, override target, water pressure, heating/pump/hot-water status |
| Motion/contact/smoke/leak detectors | Corresponding binary sensors, including reported 868 MHz variants |
| Light detectors and doorbells | Generic polled binary sensors |
| Reported `lowBattery` fields | Diagnostic battery binary sensors |

Use normal HA actions (`climate.set_temperature`, `climate.set_hvac_mode`,
`climate.set_preset_mode`, `light.turn_on`, `select.select_option`,
`scene.turn_on`, and existing switch/cover/button actions) in dashboards and
automations. Gateway presets and HeatLink temperature presets are separate controls.
`heat` holds the HeatLink temperature indefinitely; `auto` or preset `none`
clears that override. Radiators report no room temperature or reliable valve
activity, and have no verified off command.

The original sanitized firmware 3.403 fixture now creates **49 entities**,
including two radiator climate entities and a native scene. Presets, additional
readings and other device families are discovered when their fields appear in
actual gateway responses. The old fixture excludes the gateway preset and many
measurement fields; it is not evidence that those features are absent on a gateway.

Existing unique IDs are preserved. Missing/null current readings remain unknown;
communication failures make entities unavailable until recovery. Devices removed
from a successful inventory become unavailable without deleting registry entries.
Cover commands never infer position. ASUN stop is omitted because it requires
repeating the previous direction, which cannot be established reliably after
external control or a restart. Polling can miss brief detector/doorbell signals.
Light-detector polarity is preserved: `yes` means active/darkness.

Wind units follow the gateway's reported unit code. Unknown units or EnergyLink
channel types stay unknown. Daily totals are not exposed as lifetime increasing
counters for the Energy dashboard. Commands refresh reported state and are never
retried after an ambiguous timeout. No extra endpoints are added to polling.

Camera streams and PTZ remain unsupported: they require model-specific camera
URLs/authentication, which the core gateway snapshots do not establish. Separate
`hues` bridge records, LED color temperature, gateway pairing/configuration,
native timer/trigger editing and undocumented device families remain outside the
implemented controls. `/timers` and `/notifications` returned HTTP 404 on the
captured firmware. Weather-display records expose only verified battery data.
See [ENDPOINTS.md](ENDPOINTS.md) for exact routes, evidence and limitations.

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

Version **0.2.0** adds the platforms above. Validation uses Home Assistant
**2026.10.4** with Python **3.14.10**, sanitized captured fixtures, and synthetic
records derived from the official classic HomeWizard web application. New
commands have mocked routing, validation, failure and state-refresh tests;
physical device behavior and installation in a running HA instance remain
unverified. Validation on **2026-11-16**: **242 tests passed**, Ruff passed, and
the matching Home Assistant hassfest validator reported **0 invalid integrations**.
The installation ZIP was checked for expected assets and exclusion of private
collection files, fixtures and development files.

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
