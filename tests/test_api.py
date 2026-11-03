import asyncio
from unittest.mock import MagicMock

import pytest
from aiohttp import ClientSession, web

from custom_components.homewizard_smarthome.api import (
    AuthenticationError,
    GatewayError,
    HomeWizardClient,
    UnsupportedEndpoint,
    normalize_address,
)

from .conftest import fixture


@pytest.fixture(autouse=True)
def allow_mock_http(socket_enabled):
    """The API tests bind an ephemeral loopback server."""
    yield


async def make_client(aiohttp_server, handler, password="secret"):
    app = web.Application()
    app.router.add_route("GET", "/{tail:.*}", handler)
    server = await aiohttp_server(app)
    session = ClientSession()
    return session, HomeWizardClient(session, str(server.make_url("/")), password)


async def test_root_handshake_escaped_password_and_commands(aiohttp_server):
    paths = []

    async def handler(request):
        paths.append(request.raw_path)
        if request.path == "/handshake":
            return web.json_response(fixture("handshake"))
        return web.json_response({"status": "ok", "response": {}})

    session, client = await make_client(aiohttp_server, handler, "p/a?#%")
    async with session:
        await client.handshake()
        for family, actions in (
            ("sw", ["on", "off"]),
            ("sf", ["up", "down", "stop"]),
            ("gp", ["on", "off"]),
        ):
            for action in actions:
                await client.command(family, "8", action)
    assert paths == ["/handshake"] + [
        f"/p%2Fa%3F%23%25/{route}"
        for route in (
            "sw/8/on",
            "sw/8/off",
            "sf/8/up",
            "sf/8/down",
            "sf/8/stop",
            "gp/8/on",
            "gp/8/off",
        )
    ]


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (401, {}, AuthenticationError),
        (403, {}, AuthenticationError),
        (200, fixture("invalid-auth"), AuthenticationError),
        (404, {}, UnsupportedEndpoint),
        (500, {}, GatewayError),
        (302, {}, GatewayError),
        (200, {"status": "error", "url": "secret"}, GatewayError),
        (200, [], GatewayError),
        (200, {"status": "ok", "response": {}}, GatewayError),
    ],
)
async def test_errors_are_safe(aiohttp_server, status, body, error):
    async def handler(request):
        return web.json_response(body, status=status)

    session, client = await make_client(aiohttp_server, handler)
    async with session:
        with pytest.raises(error) as exc:
            await client.get_sensors()
    assert "secret" not in str(exc.value)
    assert "http" not in str(exc.value)


async def test_timeout_not_retried():
    session = MagicMock()
    session.get.side_effect = TimeoutError("http://private/password/sw/8/on")
    client = HomeWizardClient(session, "gateway.test", "password")
    with pytest.raises(GatewayError, match="timed out") as exc:
        await client.command("sw", "8", "on")
    assert session.get.call_count == 1
    assert session.get.call_args.kwargs["timeout"].total == 10
    assert "private" not in str(exc.value)


async def test_disconnected_command_not_retried(aiohttp_server):
    attempts = 0

    async def handler(request):
        nonlocal attempts
        attempts += 1
        request.transport.close()
        return web.Response()

    session, client = await make_client(aiohttp_server, handler)
    async with session:
        with pytest.raises(GatewayError):
            await client.command("sw", "8", "on")
    assert attempts == 1


async def test_requests_serialized(aiohttp_server):
    active = 0
    peak = 0

    async def handler(request):
        nonlocal active, peak
        active += 1
        peak = max(active, peak)
        await asyncio.sleep(0.01)
        active -= 1
        return web.json_response(fixture("handshake"))

    session, client = await make_client(aiohttp_server, handler)
    async with session:
        await asyncio.gather(*(client.handshake() for _ in range(4)))
    assert peak == 1


@pytest.mark.parametrize(
    "address",
    ["http://user:pass@host", "host/path", "ftp://host", "host?password=x", "http://host:bad"],
)
def test_reject_credential_or_path_address(address):
    with pytest.raises(ValueError):
        normalize_address(address)


def test_partial_and_duplicate_inventory_rejected():
    with pytest.raises(GatewayError):
        HomeWizardClient._validate_devices({"switches": []})
    data = fixture("get-sensors")["response"]
    data["switches"].append(data["switches"][0])
    with pytest.raises(GatewayError):
        HomeWizardClient._validate_devices(data)
