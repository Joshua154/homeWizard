base_url = http://{ip_address}/{password}

## Get all sensors and devices.
{base_url}/get-sensors

## Get the status of all devices.
{base_url}/get-status

## Control a switch.
{base_url}/sw/{switch_id}/{action}

## Control a Somfy cover.
{base_url}/sf/{somfy_id}/{direction}

## Set thermostat temperature.
{base_url}/sw/{radiator_id}/settarget/{temperature}