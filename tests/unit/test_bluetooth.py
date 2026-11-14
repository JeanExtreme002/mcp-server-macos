"""The tools of mcp_server_macos.tools.bluetooth, with macos.bluetooth faked."""

from typing import Any, Dict

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio

AIRPODS = macos.bluetooth.Device(
    name="AirPods Pro",
    address="E4:61:F4:CC:49:B2",
    connected=True,
    kind="headphones",
    battery={"left": 90, "right": 85, "case": 40},
)
MOUSE = macos.bluetooth.Device(name="Magic Mouse", address="28:07:08:57:AF:F7", connected=False, kind="mouse", battery={})

LISTED = [
    {
        "name": "AirPods Pro",
        "address": "E4:61:F4:CC:49:B2",
        "connected": True,
        "kind": "headphones",
        "battery_percent": {"left": 90, "right": 85, "case": 40},
    },
    {"name": "Magic Mouse", "address": "28:07:08:57:AF:F7", "connected": False, "kind": "mouse", "battery_percent": {}},
]


@pytest.fixture
def bluetooth(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    """Bluetooth on, with two paired devices, and the calls made to what changes something."""
    recorder = Recorder()
    monkeypatch.setattr(macos.bluetooth, "power", lambda: True)
    monkeypatch.setattr(macos.bluetooth, "devices", lambda: [AIRPODS, MOUSE])
    monkeypatch.setattr(macos.bluetooth, "set_power", recorder.function("set_power"))
    monkeypatch.setattr(macos.bluetooth, "connect", recorder.function("connect", AIRPODS))
    monkeypatch.setattr(macos.bluetooth, "disconnect", recorder.function("disconnect", MOUSE))
    return recorder


async def test_get_bluetooth_status(client: Client, bluetooth: Recorder) -> None:
    result = await client.call_tool("get_bluetooth_status", {})

    assert not result.is_error
    assert result.structured_content == {"power": True, "devices": LISTED}
    assert bluetooth.calls == []


async def test_get_bluetooth_status_when_macos_does_not_tell_the_power(
    client: Client, bluetooth: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The power comes from functions some versions of macOS lack; the devices from system_profiler,
    # which still lists them.
    def power() -> bool:
        raise macos.NotSupportedError("this version of macOS doesn't expose the Bluetooth power")

    monkeypatch.setattr(macos.bluetooth, "power", power)

    result = await client.call_tool("get_bluetooth_status", {})

    assert not result.is_error
    assert result.structured_content == {"power": None, "devices": LISTED}


async def test_get_bluetooth_status_of_a_mac_without_bluetooth(
    client: Client, bluetooth: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    def power() -> bool:
        raise macos.NotSupportedError("this Mac has no Bluetooth")

    monkeypatch.setattr(macos.bluetooth, "power", power)
    monkeypatch.setattr(macos.bluetooth, "devices", lambda: [])

    result = await client.call_tool("get_bluetooth_status", {})

    assert not result.is_error
    assert result.structured_content == {"power": None, "devices": []}


@pytest.mark.parametrize("on, said", [(True, "Bluetooth turned on."), (False, "Bluetooth turned off.")])
async def test_set_bluetooth_power(client: Client, bluetooth: Recorder, on: bool, said: str) -> None:
    result = await client.call_tool("set_bluetooth_power", {"on": on})

    assert not result.is_error
    assert text(result) == said
    assert bluetooth.calls == [("set_power", (on,), {})]


@pytest.mark.parametrize(
    "tool, function, device, listed",
    [
        ("connect_bluetooth_device", "connect", "airpods", LISTED[0]),
        ("disconnect_bluetooth_device", "disconnect", "28:07:08:57:AF:F7", LISTED[1]),
    ],
)
async def test_device_is_connected_and_disconnected(
    client: Client, bluetooth: Recorder, tool: str, function: str, device: str, listed: Dict[str, Any]
) -> None:
    result = await client.call_tool(tool, {"device": device})

    assert not result.is_error
    assert result.structured_content == listed
    assert bluetooth.calls == [(function, (device,), {})]


@pytest.mark.parametrize(
    "error, expected",
    [
        (ValueError("no paired Bluetooth device matches 'x'; paired: 'AirPods Pro'"), "no paired Bluetooth device matches"),
        (macos.WaitTimeoutError("AirPods Pro didn't connect within 10 seconds"), "WaitTimeoutError"),
        (macos.MacOSError("Bluetooth is off"), "MacOSError: Bluetooth is off"),
    ],
)
async def test_device_that_does_not_connect(
    client: Client, monkeypatch: pytest.MonkeyPatch, error: Exception, expected: str
) -> None:
    monkeypatch.setattr(macos.bluetooth, "connect", Recorder().function("connect", error=error))

    result = await client.call_tool("connect_bluetooth_device", {"device": "x"})

    assert result.is_error
    assert expected in text(result)


async def test_bluetooth_without_the_permission_says_what_to_allow(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    error = macos.PermissionDeniedError("Bluetooth access was denied")
    monkeypatch.setattr(macos.bluetooth, "set_power", Recorder().function("set_power", error=error))

    result = await client.call_tool("set_bluetooth_power", {"on": False})

    assert result.is_error
    assert "System Settings › Privacy & Security › Bluetooth" in text(result)


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("set_bluetooth_power", {}),
        ("set_bluetooth_power", {"on": "maybe"}),
        ("connect_bluetooth_device", {}),
        ("connect_bluetooth_device", {"device": ""}),
        ("disconnect_bluetooth_device", {"device": None}),
    ],
)
async def test_bluetooth_is_not_touched_without_knowing_how(
    client: Client, bluetooth: Recorder, tool: str, arguments: Dict[str, Any]
) -> None:
    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert bluetooth.calls == []
