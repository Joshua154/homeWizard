base_url = http://{ip_address}/{password}

## Get all sensors and devices.
{base_url}/get-sensors

## Get the status of all devices.
{base_url}/get-status

## Control a switch.
{base_url}/sw/{switch_id}/{action}

## Control a Somfy cover.
{base_url}/sf/{somfy_id}/{direction}

## Radiator target temperature (read-only).
Read the `tte` field from `{base_url}/get-status`.
Radiator command routing is not verified and remains deferred; see ENDPOINTS.md.
