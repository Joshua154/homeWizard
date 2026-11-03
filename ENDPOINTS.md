# HomeWizard Legacy API endpoint layout

Sources: every request in the local Postman collection, the integration plan, and live read-only checks on **2026-11-03**. The collection contains **21 requests covering 19 unique route templates**: 11 read routes and eight command routes. `Get weather Copy` duplicates `Get weather`; `Set Radiator` duplicates `Set dimmer`.

All routes use HTTP `GET`, including commands. Paths are relative to `http://{gateway_address}/{password}` **except `/handshake`, which uses `http://{gateway_address}` without the password prefix**. Keep passwords and full authenticated URLs out of logs and diagnostics.

This is complete coverage of the local collection plus the plan's handshake and Somfy-up correction. It is not proof that every route implemented by the firmware has been discovered. Commands were not executed, and no unknown routes were brute-forced.

## Live read-route discovery

Successful reads returned HTTP 200 and JSON with `status: "ok"`. Their envelope contains `status`, `version`, `request.route`, and `response`. Shapes below describe observed responses, not exhaustive schemas. An HTTP 404 applies to the tested path on this gateway; it does not establish availability on other firmware.

| Postman request / source | Route | Result | Observed response |
|---|---|---|---|
| Plan: handshake | `/handshake` (no password prefix) | Verified | Object with `serial`, `version`, `homewizard`, `appupdaterequired`, `firmwareupdateavailable` |
| Get sensors | `/get-sensors` | Verified | Inventory object; category counts below |
| Get status | `/get-status` | Verified | State object: seven switches, 18 KaKu sensors, two thermometers, one each of rain meter, wind meter, weather display; additional empty categories, `preset`, `time` |
| List switches | `/swlist` | Verified | Array of 20 switches; sample fields: `id`, `name`, `type`, `mode`, `favorite` |
| List scenes/groups | `/gplist` | Verified | Array of one group; sample fields: `id`, `name`, `favorite` |
| Get triggers | `/triggers` | Verified | Array of 30 triggers; sample includes actions, schedule, sensor reference, notification configuration |
| Get timers | `/timers` | HTTP 404 | Non-JSON response |
| Get notifications | `/notifications` | HTTP 404 | Non-JSON response |
| Notification receivers | `/nf-receivers` | Verified | Array of six receivers; sample fields: `id`, `name`, `type` |
| Sun times today | `/suntimes/today` | Verified | Object with `sunrise`, `sunset`; formats/timezone not yet established |
| Get weather; Get weather Copy | `/wea/get` | Verified | Weather location/sharing configuration, including `location`, `country`, `sharing`, `outside_thermometer`, `shared_thermometers`; no current weather measurements observed |
| KaKu Log | `/kks/get/{id}/log` | Verified for one discovered sensor | Array of 98 log entries; sample fields: `status`, `t`; time units not yet established |

The password-prefixed `/handshake` returned HTTP 404. The unprefixed handshake succeeded and exposes the gateway serial at `response.serial`. Because handshake is unauthenticated, password validation must use an authenticated read such as `/get-sensors`.

### Observed inventory

| Category in `/get-sensors` | Count | Notes |
|---|---|---|
| `switches` | 20 | Five `switch`, 13 `somfy`, two `radiator` |
| `kakusensors` | 18 | Sample fields include `id`, `name`, `type`, `status`, `timestamp`, `cameraid`, `favorite` |
| `thermometers` | 2 | Sample includes `te`, `hu`, extrema/timestamps, and `lowBattery` |
| `rainmeters` | 1 | Sample includes identity metadata and `lowBattery` |
| `windmeters` | 1 | Sample includes identity metadata, `unit`, and `lowBattery` |
| `weatherdisplays` | 1 | Identity metadata |
| `scenes` | 1 | `id`, `name`, `favorite` in the sample |
| `cameras` | 1 | Includes credentials and connection details; exclude from distributed fixtures |
| `energylinks`, `energymeters`, `heatlinks`, `hues`, `uvmeters` | 0 each | Empty inventory categories |

Only field names, counts, and limited non-sensitive status/type values were retained during discovery. Names, credentials, addresses, serial values, receiver details, and raw response bodies were not saved. Counts are a snapshot and may change.

## Command routes

These are documented from the collection and plan, **not live-tested**. `{id}` belongs to the corresponding device/group category; do not assume IDs are interchangeable. Commands are on-demand only, never part of route probing or polling.

| Postman request | Collection route | Proposed client method | Status / intended behavior |
|---|---|---|---|
| Switch on | `/sw/{id}/on` | `set_switch(id, True)` | Turn switch on |
| Switch off | `/sw/{id}/off` | `set_switch(id, False)` | Turn switch off |
| Set dimmer; Set Radiator | `/sw/dim/{id}/{value}` | `set_dimmer(id, value)` | Deferred; value range unknown. The duplicated radiator entry does not establish a radiator command or temperature encoding |
| Somfy up | `/sw/{id}/up` | `open_cover(id)` | Inconsistent collection entry; the plan specifies `/sf/{id}/up` instead. Use that planned correction in implementation, subject to command validation |
| Somfy down | `/sf/{id}/down` | `close_cover(id)` | Close cover; no position feedback established |
| Somfy stop | `/sf/{id}/stop` | `stop_cover(id)` | Stop cover |
| Activate scene | `/gp/{id}/on` | `activate_group(id)` | Activate group |
| Deactivate scene | `/gp/{id}/off` | `deactivate_group(id)` | Deactivate group |

After supported commands, refresh `/get-status`; do not fabricate cover position or retry commands after ambiguous timeouts. Any later live command test remains restricted by the plan to switch ID 8, recording and restoring its original state.

## Discovery and state

These are the proposed client methods and polling responsibilities for `custom_components/homewizard_legacy`.

| Postman request | Endpoint | Proposed client method | Integration use | When to request |
|---|---|---|---|---|
| Get sensors | `/get-sensors` | `get_sensors()` | Primary device inventory and metadata for entity discovery | Setup, then every five minutes |
| Get status | `/get-status` | `get_status()` | Latest reported device and sensor states | Initial refresh, then every 10 seconds by default; configurable from 5–300 seconds; refresh after commands |
| List switches | `/swlist` | `list_switches()` | Supplemental switch inventory, if `/get-sensors` lacks required switch metadata | During inventory refresh only if response validation establishes a need |
| List scenes/groups | `/gplist` | `list_groups()` | Discover groups for activate/deactivate buttons; does not establish their current state | Setup and every five minutes when group discovery is supported |

`/get-sensors` and `/get-status` form the core discovery/state path. Keep their results separate so a device missing from status, such as a cover, remains registered. Reconcile removals only against a successful full inventory response.

`/gplist` and `/swlist` are available, and the primary inventory also includes `scenes` and `switches` with matching counts. Compare complete records before choosing one authoritative source; matching counts alone do not prove equivalence. Avoid routinely requesting supplemental inventory if the primary inventory supplies the required metadata. An unsupported supplemental endpoint should not prevent core devices from loading.

## Optional read endpoints

Keep these outside the initial polling loop. Their presence in the collection does not establish entity mappings or justify adding Home Assistant automation or notification features.

| Postman request | Endpoint | Proposed client method | Purpose and initial scope |
|---|---|---|---|
| Get triggers | `/triggers` | `get_triggers()` | Read gateway automation triggers; defer integration support |
| Get timers | `/timers` | `get_timers()` | Unavailable at this path on the tested gateway; exclude from polling |
| Get notifications | `/notifications` | `get_notifications()` | Unavailable at this path on the tested gateway; exclude from polling |
| Get weather | `/wea/get` | `get_weather()` | Observed configuration/sharing data; no measurement entities justified |
| Notification receivers | `/nf-receivers` | `get_notification_receivers()` | Receiver configuration; defer integration support |
| Sun times today | `/suntimes/today` | `get_sun_times()` | Sunrise/sunset values; defer until formats and timezone are established |
| KaKu Log | `/kks/get/{id}/log` | `get_kaku_log(id)` | History for a discovered KaKu sensor; optional diagnostic read, outside routine polling |

Weather devices can still be discovered through the core inventory. Expose verified battery fields from the core responses as planned; do not infer wind/rain units from this endpoint's name.

## Setup dependency outside the collection

`PLAN.md` also requires `GET /handshake`, with a proposed client method `handshake()`, for gateway identity. It is **absent from the collection**, but the unprefixed route is now verified; the serial number is at `response.serial`.

Proposed startup sequence:

1. Read `/handshake` without the password prefix to identify the gateway; validate the password using the authenticated `/get-sensors` route.
2. Use the verified gateway serial number to identify the integration, then build inventory from `/get-sensors`.
3. Retrieve group inventory from `/gplist` when supported, and use `/swlist` only if needed for switch metadata.
4. Fetch `/get-status` for initial entity state, then start the status and inventory refresh schedules.

Serialize all gateway requests and apply the planned 10-second timeout. Keep optional read failures separate from core communication failures. Missing or `null` measurements remain unknown; never treat a failed inventory request as an empty inventory.

## Response validation before implementation

Live discovery established route availability and sampled shapes. Before implementation, capture appropriately sanitized fixtures and establish:

- The success/error envelope and how authentication failures are reported.
- Field types and device variants across complete responses; gateway identity comes from `response.serial` in the root handshake.
- Which inventory fields are also present in status, including missing-device behavior.
- Measurement types, units, battery semantics, and missing/`null` values.
- Whether `/swlist` and `/gplist` add information beyond `/get-sensors`.

Do not distribute the original collection or authenticated URLs. Retain only sanitized response fixtures needed by the integration.

All 21 collection requests are covered above, including duplicates and inconsistent entries. HTTP `GET` alone does not identify a read-only operation in this API.

## Implementation verification (2026-11-03)

Read-only fixture capture established the following additional details on firmware 3.403:

- Invalid passwords return HTTP **200**, `status: "failed"`, and numeric `error: 1`.
  Treat this as an authentication failure, alongside HTTP 401/403. Other failed
  envelopes remain general API errors; their meanings have not been established.
- Complete `/swlist` and `/gplist` records matched `switches` and `scenes` from
  `/get-sensors` during the comparison. The initial integration uses the primary
  inventory without supplemental polling.
- Ordinary switches report `status: "on"` or `"off"`. KaKu types are `motion`,
  `contact`, `smoke`, and `light`; their status is `"yes"`, `"no"`, or `null`.
  Light status remains generic without a light/dark interpretation.
- Radiators expose numeric `tte` (both captured values were 15), mapped to the
  planned read-only target temperature in degrees Celsius. Physical command
  behavior and radiator controls remain unverified/deferred.
- One thermometer has numeric `te` and `hu`; the other has neither field in
  inventory or status. Only returned measurement fields create entities.
- `lowBattery` is `"yes"`/`"no"` in the two thermometer records and the wind/rain
  records. These fields were absent from status, so battery readings use the most
  recent successful inventory unless a status record explicitly supplies a value.
- All 13 Somfy records were absent from status and remain registered from inventory.

Sanitized fixtures live in `tests/fixtures`. They replace names and gateway serial,
omit cameras and connection data, and retain only allowlisted state fields. This
snapshot produces 46 entities. No live device command was executed; the corrected
`/sf/{id}/up` route is covered by mocked command tests.
