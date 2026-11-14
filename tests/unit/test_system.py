"""The tools of mcp_server_macos.tools.system, with macos.system faked."""

from datetime import timedelta
from typing import Any

import macos
import pytest
from mcp import Client

from tests.helpers import text

pytestmark = pytest.mark.anyio

EXPECTED = {
    "macos_version": "15.6.1",
    "macos_build": "24G90",
    "model": "MacBook Pro",
    "model_identifier": "Mac14,9",
    "processor": "Apple M2 Pro",
    "memory_bytes": 17179869184,
    "computer_name": "Jean's MacBook Pro",
    "uptime_seconds": 93784,
}


@pytest.fixture
def system(monkeypatch: pytest.MonkeyPatch) -> None:
    """A fake Mac: what macos.system would say of it."""
    monkeypatch.setattr(macos.system, "version", lambda: "15.6.1")
    monkeypatch.setattr(macos.system, "build", lambda: "24G90")
    monkeypatch.setattr(macos.system, "model", lambda: "MacBook Pro")
    monkeypatch.setattr(macos.system, "model_identifier", lambda: "Mac14,9")
    monkeypatch.setattr(macos.system, "processor", lambda: "Apple M2 Pro")
    monkeypatch.setattr(macos.system, "memory", lambda: 17179869184)
    monkeypatch.setattr(macos.system, "computer_name", lambda: "Jean's MacBook Pro")
    monkeypatch.setattr(macos.system, "uptime", lambda: timedelta(days=1, hours=2, minutes=3, seconds=4.9))


@pytest.mark.usefixtures("system")
async def test_get_system_info(client: Client) -> None:
    result = await client.call_tool("get_system_info", {})

    assert not result.is_error
    assert result.structured_content == EXPECTED
    # The same as text, for the clients that only read text.
    assert '"macos_version": "15.6.1"' in text(result)


async def test_get_system_info_describes_its_result(client: Client) -> None:
    (tool,) = [tool for tool in (await client.list_tools()).tools if tool.name == "get_system_info"]

    assert tool.annotations is not None and tool.annotations.read_only_hint is True
    assert tool.input_schema.get("properties", {}) == {}
    assert tool.output_schema is not None
    assert set(tool.output_schema["properties"]) == set(EXPECTED)
    assert set(tool.output_schema["required"]) == set(EXPECTED)
    for name, field in tool.output_schema["properties"].items():
        assert field.get("description"), "{} isn't described".format(name)


@pytest.mark.usefixtures("system")
async def test_get_system_info_outside_macos(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    def version() -> str:
        raise macos.NotSupportedError("macos.system requires macOS")

    monkeypatch.setattr(macos.system, "version", version)

    result = await client.call_tool("get_system_info", {})

    assert result.is_error
    assert "NotSupportedError: macos.system requires macOS" in text(result)


@pytest.mark.usefixtures("system")
async def test_get_system_info_ignores_arguments_it_does_not_take(client: Client) -> None:
    # The SDK drops the arguments a tool doesn't declare: none reaches the function.
    result = await client.call_tool("get_system_info", {"verbose": True})

    assert not result.is_error
    assert result.structured_content == EXPECTED


# What else the Mac is: its protections, fonts, USB devices and updates.


@pytest.mark.parametrize(
    "status, expected",
    [
        ((True, False, True, True), {"filevault": True, "firewall": False, "gatekeeper": True}),
        ((None, None, None, None), {"filevault": None, "firewall": None, "gatekeeper": None}),
    ],
)
async def test_get_security_status(client: Client, monkeypatch: pytest.MonkeyPatch, status: Any, expected: Any) -> None:
    # None: macOS didn't say, which isn't the protection being off.
    found = macos.system.SecurityStatus(filevault=status[0], firewall=status[1], gatekeeper=status[2], sip=status[3])
    monkeypatch.setattr(macos.system, "security_status", lambda: found)

    result = await client.call_tool("get_security_status", {})

    assert not result.is_error
    assert result.structured_content == {**expected, "system_integrity_protection": status[3]}


@pytest.mark.parametrize(
    "arguments, expected",
    [
        ({}, ["Arial", "Avenir", "Helvetica", "Helvetica Neue", "Menlo"]),
        ({"search": "HELV"}, ["Helvetica", "Helvetica Neue"]),
        ({"search": "neue"}, ["Helvetica Neue"]),
        ({"search": "comic"}, []),
        ({"search": ""}, ["Arial", "Avenir", "Helvetica", "Helvetica Neue", "Menlo"]),
    ],
)
async def test_list_fonts(client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Any, expected: Any) -> None:
    monkeypatch.setattr(macos.system, "fonts", lambda: ["Arial", "Avenir", "Helvetica", "Helvetica Neue", "Menlo"])

    result = await client.call_tool("list_fonts", arguments)

    assert not result.is_error
    assert result.structured_content == {"result": expected}


async def test_list_usb_devices(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    devices = [
        macos.system.USBDevice(
            name="Samsung T7", vendor="Samsung", vendor_id=1256, product_id=16384, serial="S5T", speed="super", is_hub=False
        ),
        macos.system.USBDevice(
            name=None, vendor=None, vendor_id=None, product_id=None, serial=None, speed=None, is_hub=True
        ),
    ]
    monkeypatch.setattr(macos.system, "usb_devices", lambda: devices)

    result = await client.call_tool("list_usb_devices", {})

    assert result.structured_content == {
        "result": [
            {
                "name": "Samsung T7",
                "vendor": "Samsung",
                "vendor_id": 1256,
                "product_id": 16384,
                "serial": "S5T",
                "speed": "super",
                "is_hub": False,
            },
            {
                "name": None,
                "vendor": None,
                "vendor_id": None,
                "product_id": None,
                "serial": None,
                "speed": None,
                "is_hub": True,
            },
        ]
    }


async def test_list_available_updates(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    updates = [
        macos.system.Update(
            label="macOS Sequoia 15.8.1-24H32",
            title="macOS Sequoia 15.8.1",
            version="15.8.1",
            size=3600000000,
            recommended=True,
            restart=True,
        ),
        macos.system.Update(
            label="Safari18.6-18621", title="Safari", version="18.6", size=None, recommended=False, restart=False
        ),
    ]
    monkeypatch.setattr(macos.system, "available_updates", lambda: updates)

    result = await client.call_tool("list_available_updates", {})

    assert not result.is_error
    assert result.structured_content == {
        "result": [
            {
                "label": "macOS Sequoia 15.8.1-24H32",
                "title": "macOS Sequoia 15.8.1",
                "version": "15.8.1",
                "size_bytes": 3600000000,
                "recommended": True,
                "restart": True,
            },
            {
                "label": "Safari18.6-18621",
                "title": "Safari",
                "version": "18.6",
                "size_bytes": None,
                "recommended": False,
                "restart": False,
            },
        ]
    }


async def test_list_available_updates_when_apple_does_not_answer(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    def available_updates() -> Any:
        raise macos.CommandTimeoutError(["softwareupdate"], 300.0)

    monkeypatch.setattr(macos.system, "available_updates", available_updates)

    result = await client.call_tool("list_available_updates", {})

    assert result.is_error
    assert "CommandTimeoutError" in text(result)


async def test_list_available_updates_says_it_asks_a_server(client: Client) -> None:
    # The one tool of the module that reaches beyond this Mac.
    (tool,) = [tool for tool in (await client.list_tools()).tools if tool.name == "list_available_updates"]

    assert tool.annotations is not None
    assert tool.annotations.open_world_hint is True
    assert tool.annotations.read_only_hint is True
