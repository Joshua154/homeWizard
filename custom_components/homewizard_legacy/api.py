"""Serialized local HTTP API. Never expose authenticated URLs in errors."""

import asyncio
from typing import Any

import aiohttp
from yarl import URL


class GatewayError(Exception):
    """Safe error suitable for Home Assistant logs."""


class AuthenticationError(GatewayError):
    """The gateway rejected authentication."""


class UnsupportedEndpoint(GatewayError):
    """The firmware does not implement an endpoint."""


async def _single_attempt(request, handler):
    """Prevent aiohttp's transparent GET retry after a lost command response."""
    try:
        return await handler(request)
    except aiohttp.ClientError:
        raise GatewayError("Gateway command failed; delivery may be uncertain") from None


def normalize_address(address: str) -> str:
    """Accept a hostname/IP with an optional HTTP(S) scheme and port."""
    try:
        url = URL(address if "://" in address else f"http://{address}")
        if (
            url.scheme not in ("http", "https")
            or not url.host
            or url.user is not None
            or url.path not in ("", "/")
            or url.query_string
            or url.fragment
        ):
            raise ValueError
        _ = url.port
    except ValueError, TypeError:
        raise ValueError("Enter a gateway address without credentials or a path") from None
    return str(url.origin())


class HomeWizardClient:
    """GET-only legacy API, including non-idempotent command routes."""

    def __init__(self, session: aiohttp.ClientSession, address: str, password: str):
        self._session = session
        self._base = URL(normalize_address(address))
        self._password = password
        self._lock = asyncio.Lock()

    async def _request(
        self, route: str, *, authenticated: bool = True, command: bool = False
    ) -> Any:
        # with_path quotes reserved characters in the password, including /.
        from urllib.parse import quote

        path = f"/{quote(self._password, safe='')}/{route}" if authenticated else f"/{route}"
        url = self._base.with_path(path, encoded=True)
        async with self._lock:
            try:
                async with self._session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=10),
                    allow_redirects=False,
                    middlewares=(_single_attempt,) if command else (),
                ) as response:
                    if response.status in (401, 403):
                        raise AuthenticationError("Gateway authentication failed")
                    if response.status == 404:
                        raise UnsupportedEndpoint("Gateway endpoint unavailable")
                    if response.status != 200:
                        raise GatewayError("Gateway returned an HTTP error")
                    payload = await response.json(content_type=None)
            except aiohttp.ClientError, TimeoutError, ValueError:
                raise GatewayError("Gateway request failed or timed out") from None
        if (
            isinstance(payload, dict)
            and payload.get("status") == "failed"
            and payload.get("error") == 1
        ):
            raise AuthenticationError("Gateway authentication failed")
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            raise GatewayError("Gateway returned an unsuccessful response")
        return payload.get("response")

    async def handshake(self) -> dict:
        data = await self._request("handshake", authenticated=False)
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("serial"), str)
            or not data["serial"]
        ):
            raise GatewayError("Gateway identity is missing")
        return data

    async def get_sensors(self) -> dict:
        return self._validate_devices(await self._request("get-sensors"))

    async def get_status(self) -> dict:
        return self._validate_devices(await self._request("get-status"))

    @staticmethod
    def _validate_devices(data: Any) -> dict:
        # Reject partial/error-shaped snapshots before reconciling removals.
        if not isinstance(data, dict) or not all(
            isinstance(data.get(key), list) for key in ("switches", "thermometers", "kakusensors")
        ):
            raise GatewayError("Gateway returned an invalid device snapshot")
        for value in data.values():
            if isinstance(value, list):
                ids = set()
                for record in value:
                    if not isinstance(record, dict) or not str(record.get("id", "")).isdigit():
                        raise GatewayError("Gateway returned an invalid device record")
                    device_id = str(record["id"])
                    if device_id in ids:
                        raise GatewayError("Gateway returned duplicate device IDs")
                    ids.add(device_id)
        return data

    async def list_switches(self) -> list:
        return await self._request("swlist")

    async def list_groups(self) -> list:
        return await self._request("gplist")

    async def command(self, family: str, device_id: str, action: str) -> None:
        allowed = {"sw": {"on", "off"}, "sf": {"up", "down", "stop"}, "gp": {"on", "off"}}
        if family not in allowed or action not in allowed[family] or not str(device_id).isdigit():
            raise ValueError("Unsupported gateway command")
        # Exactly one attempt: retrying a timed-out radio command is unsafe.
        await self._request(f"{family}/{device_id}/{action}", command=True)
