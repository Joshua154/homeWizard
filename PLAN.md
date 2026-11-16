# HomeWizard smartHome HACS integration

## Expansion completed (2026-11-16, version 0.2.0)

The original implementation plan below remains a historical baseline. The new
release adds radiator and HeatLink climate controls, reported HeatLink presets,
gateway preset selection, native scenes, dimmer/Hue/LED lights, Brel/ASUN covers,
and weather/UV/energy/HeatLink measurements and additional detector variants.
Protocol mappings and supported ranges are now backed by the original
HomeWizard web application's controllers and models; see the 0.2.0 section in
[ENDPOINTS.md](ENDPOINTS.md). Existing entity IDs and buttons remain intact.

Three agents implemented heating, lighting and measurements independently, with
the shared command client, coordinator, discovery, presets/scenes, documentation
and integration review combined centrally. Validation uses mocked commands and
synthetic protocol fixtures; no live device was actuated.

Validation: 242 tests passed on the pinned Home Assistant 2026.10.4 / Python
3.14.10 baseline; Ruff passed; matching hassfest reported 0 invalid integrations.
The versioned 0.2.0 installation ZIP contains only the allowlisted release assets.

Camera-model protocols, undocumented device families and native gateway
administration are still outside the supported surface. README documents the
exact supported controls and remaining limitations rather than implying every
firmware function is available. Publishing/HACS submission remains separate.

## Summary

Build **HomeWizard smartHome** under `custom_components/homewizard_smarthome`, separate from HomeWizard Energy.

Enter the gateway address and password once through Home Assistant’s UI. Automatically discover its supported devices, create their entities, and detect later additions without YAML configuration.

The initial implementation targets your gateway’s verified API responses and firmware 3.403.

## Implementation

- Follow the [API endpoint layout](ENDPOINTS.md), covering every collection request and live read-only discovery on 2026-11-03. It records supported reads, HTTP 404 results, untested commands, and collection inconsistencies.
- Use an asynchronous local HTTP client and Home Assistant’s shared update coordinator.
- Read `/handshake` at the gateway root **without a password prefix** and identify the gateway by `response.serial`. Validate the password using authenticated `/get-sensors`; the password-prefixed handshake returns HTTP 404. Support password changes and address reconfiguration without recreating entities.
- Poll `/get-status` every 10 seconds, configurable from 5–300 seconds. Refresh `/get-sensors` every five minutes for additions and metadata changes.
- Identify devices by gateway serial, API category, and device ID. Identify individual measurements by an additional measurement key. Preserve identity across restarts and renames.
- Register child devices beneath the gateway and dynamically add newly discovered entities.
- Serialize gateway requests, apply a 10-second timeout, and refresh reported state after commands. Do not automatically retry commands after an ambiguous timeout.

## Entities and behavior

| API device | Home Assistant representation |
|---|---|
| Ordinary switches | Switch entities with on/off control |
| Somfy devices | Cover entities with open, close, and stop |
| Thermometers | Temperature and humidity sensors where supported by returned fields |
| Motion, contact, and smoke detectors | Binary sensors with corresponding device classes |
| Light detectors | Generic binary sensors until polarity is verified |
| Battery indicators | Diagnostic low-battery binary sensors |
| Radiators | Read-only target-temperature sensors |
| Groups | Separate activate/deactivate buttons, since no reliable group state is returned |

- Use `/sw/{id}/on` and `/sw/{id}/off` for switches, `/sf/{id}/{up|down|stop}` for Somfy, and `/gp/{id}/{on|off}` for groups. Correct the inconsistent Somfy-up entry in the sanitized API reference.
- Covers have unknown position and no percentage-position control; commands must not fabricate physical feedback.
- Missing or `null` measurements remain unknown. Failed gateway communication makes entities unavailable; recovery restores them automatically.
- Keep inventory separate from status: covers absent from `/get-status` remain registered. Devices removed from a successful full inventory become unavailable without deleting registry entries.
- Discover weather devices, exposing verified battery fields immediately. Defer wind/rain measurements without established field and unit mappings.
- Keep `/timers` and `/notifications` out of polling: both returned HTTP 404 during discovery. `/wea/get` returned weather location/sharing configuration, so it does not currently justify weather measurement entities.
- Defer dimmer brightness, radiator commands, cameras, and unsupported device families. Retain sanitized information about unsupported types in diagnostics so support can be extended without guessing.

## Packaging and validation

- Prepare the local repository with a versioned manifest, `hacs.json`, installation instructions, English/German setup translations, license, and original icon assets, following [HACS integration requirements](https://www.hacs.xyz/docs/publish/integration/).
- Include sanitized response fixtures and diagnostics. Exclude gateway passwords, camera credentials, authenticated URLs, and the original credential-bearing collection from distribution.
- Add tests for setup, duplicate gateways, reconfiguration, discovery after startup, stable IDs, overlapping IDs across categories, missing readings, outages, recovery, command errors, and unloading.
- Verify the captured inventory produces 5 switches, 13 covers, 2 radiator readings, and 18 detector entities, plus supported measurement/battery entities and group buttons.
- Test command routing with mocked responses. During implementation, any live command test is restricted to **switch ID 8**, recording and restoring its original state.
- Run tests and integration validation against the current stable Home Assistant release; record that tested version as the initial compatibility baseline.

## Defaults and boundaries

- Automatic discovery starts after manual gateway setup; network discovery of the gateway is excluded.
- Sensor state reflects the gateway’s latest report. Polling cannot guarantee capture of every brief radio event.
- Deliver locally first. GitHub publishing, real repository metadata, and HACS listing submission remain a separate publishing step; placeholder metadata must be clearly identified.
- Read-only route discovery was performed and documented locally. No device commands were executed.

## Implementation progress (2026-11-03)

- Implemented the local `0.1.0` integration under `custom_components/homewizard_smarthome`:
  UI setup, duplicate detection, address/password reconfiguration, reauthentication,
  configurable status polling, inventory refresh, dynamic discovery and all initial
  entity platforms described above.
- Captured sanitized read-only fixtures and verified the authentication error
  envelope and supplemental inventory equivalence; see the new verification
  section in `ENDPOINTS.md`.
- Added English/German translations, safe structural diagnostics, original icon
  assets, MIT license, local installation instructions and an allowlisted ZIP builder.
- Added Home Assistant 2026.10.4 tests and a locked Python 3.14 development environment.
- Validation passed: 57 tests, Ruff, and matching Home Assistant hassfest
  (0 invalid integrations). The local installation ZIP was checked for private
  collection files and credentials.
- Live command validation and installation on the user's Home Assistant instance
  remain unperformed. Repository metadata is explicitly placeholder content;
  publishing and HACS submission remain a separate step.
