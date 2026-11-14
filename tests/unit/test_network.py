"""The tools of mcp_server_macos.tools.network, with macos.network faked."""

from typing import Any, Dict

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


@pytest.fixture
def network(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    """A Mac on Wi-Fi, and the calls made to the functions of macos.network that change or measure something."""
    recorder = Recorder()
    signal = macos.network.WiFiSignal(
        rssi=-62, noise=-95, transmit_rate=866.0, channel=157, band="5GHz", channel_width=80, security="wpa2_personal"
    )
    proxies = macos.network.Proxies(
        http=None, https="proxy.example.com:8080", socks=None, auto_config_url=None, exceptions=("*.local", "169.254/16")
    )
    monkeypatch.setattr(macos.network, "is_online", lambda: True)
    monkeypatch.setattr(macos.network, "interface", lambda: "en0")
    monkeypatch.setattr(macos.network, "ip", lambda: "192.168.0.8")
    monkeypatch.setattr(macos.network, "wifi_power", lambda: True)
    monkeypatch.setattr(macos.network, "wifi_signal", lambda: signal)
    monkeypatch.setattr(macos.network, "dns_servers", lambda: ["192.168.0.1", "8.8.8.8"])
    monkeypatch.setattr(macos.network, "proxies", lambda: proxies)
    for name in ("set_wifi_power", "connect_vpn", "disconnect_vpn"):
        monkeypatch.setattr(macos.network, name, recorder.function(name))
    return recorder


async def test_get_network_status(client: Client, network: Recorder) -> None:
    result = await client.call_tool("get_network_status", {})

    assert not result.is_error
    assert result.structured_content == {
        "online": True,
        "interface": "en0",
        "ip": "192.168.0.8",
        "wifi_power": True,
        "wifi_signal": {
            "quality": "good",
            "rssi_dbm": -62,
            "noise_dbm": -95,
            "snr_db": 33,
            "transmit_rate_mbps": 866.0,
            "channel": 157,
            "band": "5GHz",
            "channel_width_mhz": 80,
            "security": "wpa2_personal",
        },
        "dns_servers": ["192.168.0.1", "8.8.8.8"],
        "proxies": {
            "http": None,
            "https": "proxy.example.com:8080",
            "socks": None,
            "auto_config_url": None,
            "exceptions": ["*.local", "169.254/16"],
        },
    }
    assert network.calls == []


async def test_get_network_status_offline_on_a_mac_without_wifi(
    client: Client, network: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    def wifi_power() -> bool:
        raise macos.NotSupportedError("this Mac has no Wi-Fi")

    monkeypatch.setattr(macos.network, "is_online", lambda: False)
    monkeypatch.setattr(macos.network, "interface", lambda: None)
    monkeypatch.setattr(macos.network, "ip", lambda: None)
    monkeypatch.setattr(macos.network, "wifi_power", wifi_power)
    monkeypatch.setattr(macos.network, "wifi_signal", lambda: None)
    monkeypatch.setattr(macos.network, "dns_servers", lambda: [])

    result = await client.call_tool("get_network_status", {})

    assert not result.is_error
    status = result.structured_content
    assert status is not None
    assert (status["online"], status["interface"], status["ip"]) == (False, None, None)
    assert (status["wifi_power"], status["wifi_signal"], status["dns_servers"]) == (None, None, [])


async def test_list_network_interfaces(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    interfaces = [
        macos.network.NetworkInterface(
            name="en0",
            display_name="Wi-Fi",
            mac="a4:83:e7:12:34:56",
            ipv4=("192.168.0.8",),
            ipv6=("fe80::1", "2804::2"),
            up=True,
            active=True,
        ),
        macos.network.NetworkInterface(
            name="utun3", display_name=None, mac=None, ipv4=(), ipv6=(), up=False, active=False
        ),
    ]
    monkeypatch.setattr(macos.network, "interfaces", lambda: interfaces)

    result = await client.call_tool("list_network_interfaces", {})

    assert result.structured_content == {
        "result": [
            {
                "name": "en0",
                "display_name": "Wi-Fi",
                "mac": "a4:83:e7:12:34:56",
                "ipv4": ["192.168.0.8"],
                "ipv6": ["fe80::1", "2804::2"],
                "up": True,
                "active": True,
            },
            {"name": "utun3", "display_name": None, "mac": None, "ipv4": [], "ipv6": [], "up": False, "active": False},
        ]
    }


@pytest.mark.parametrize("arguments, interval", [({}, 1.0), ({"interval_seconds": 5}, 5.0)])
async def test_get_bandwidth(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any], interval: float
) -> None:
    recorder = Recorder()
    usage = [
        macos.network.Bandwidth(
            interface="en0", display_name="Wi-Fi", download=42.1, upload=3.5, received=5262500, sent=437500
        )
    ]
    monkeypatch.setattr(macos.network, "bandwidth", recorder.function("bandwidth", usage))

    result = await client.call_tool("get_bandwidth", arguments)

    assert not result.is_error
    assert result.structured_content == {
        "result": [
            {
                "interface": "en0",
                "display_name": "Wi-Fi",
                "download_mbps": 42.1,
                "upload_mbps": 3.5,
                "received_bytes": 5262500,
                "sent_bytes": 437500,
            }
        ]
    }
    assert recorder.calls == [("bandwidth", (interval,), {})]


@pytest.mark.parametrize("arguments, sequential", [({}, False), ({"sequential": True}, True)])
async def test_run_speed_test(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any], sequential: bool
) -> None:
    recorder = Recorder()
    measured = macos.network.SpeedTest(
        download=43.61,
        upload=39.42,
        latency=54.6,
        loaded_latency=1126.6,
        responsiveness=53.0,
        interface="en0",
        server="saopaulo1.cdn.apple.com",
    )
    monkeypatch.setattr(macos.network, "speed_test", recorder.function("speed_test", measured))

    result = await client.call_tool("run_speed_test", arguments)

    assert not result.is_error
    assert result.structured_content == {
        "download_mbps": 43.61,
        "upload_mbps": 39.42,
        "latency_ms": 54.6,
        "loaded_latency_ms": 1126.6,
        "responsiveness_rpm": 53.0,
        "interface": "en0",
        "server": "saopaulo1.cdn.apple.com",
    }
    assert recorder.calls == [("speed_test", (), {"sequential": sequential})]


async def test_run_speed_test_says_it_talks_to_a_server(client: Client) -> None:
    (tool,) = [tool for tool in (await client.list_tools()).tools if tool.name == "run_speed_test"]

    assert tool.annotations is not None
    assert tool.annotations.open_world_hint is True


@pytest.mark.parametrize("on, said", [(True, "Wi-Fi turned on."), (False, "Wi-Fi turned off.")])
async def test_set_wifi_power(client: Client, network: Recorder, on: bool, said: str) -> None:
    result = await client.call_tool("set_wifi_power", {"on": on})

    assert not result.is_error
    assert text(result) == said
    assert network.calls == [("set_wifi_power", (on,), {})]


async def test_list_vpns(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    vpns = [
        macos.network.VPN(name="Office", kind="L2TP", status="disconnected", id="A1B2"),
        macos.network.VPN(
            name="GlobalProtect", kind="com.paloaltonetworks.GlobalProtect.client", status="connected", id="C3D4"
        ),
    ]
    monkeypatch.setattr(macos.network, "vpns", lambda: vpns)

    result = await client.call_tool("list_vpns", {})

    assert result.structured_content == {
        "result": [
            {"name": "Office", "kind": "L2TP", "status": "disconnected", "id": "A1B2"},
            {
                "name": "GlobalProtect",
                "kind": "com.paloaltonetworks.GlobalProtect.client",
                "status": "connected",
                "id": "C3D4",
            },
        ]
    }


@pytest.mark.parametrize(
    "tool, function, said",
    [("connect_vpn", "connect_vpn", "Office is connected."), ("disconnect_vpn", "disconnect_vpn", "Office is disconnected.")],
)
async def test_vpn_is_connected_and_disconnected(
    client: Client, network: Recorder, tool: str, function: str, said: str
) -> None:
    result = await client.call_tool(tool, {"name": "Office"})

    assert not result.is_error
    assert text(result) == said
    assert network.calls == [(function, ("Office",), {})]


@pytest.mark.parametrize(
    "error, expected",
    [
        (macos.MacOSError("no VPN named 'Home'"), "MacOSError: no VPN named 'Home'"),
        (macos.WaitTimeoutError("Home didn't connect within 30 seconds"), "WaitTimeoutError"),
    ],
)
async def test_vpn_that_does_not_connect(
    client: Client, monkeypatch: pytest.MonkeyPatch, error: Exception, expected: str
) -> None:
    monkeypatch.setattr(macos.network, "connect_vpn", Recorder().function("connect_vpn", error=error))

    result = await client.call_tool("connect_vpn", {"name": "Home"})

    assert result.is_error
    assert expected in text(result)


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("set_wifi_power", {}),
        ("set_wifi_power", {"on": "maybe"}),
        ("connect_vpn", {}),
        ("connect_vpn", {"name": ""}),
        ("disconnect_vpn", {"name": None}),
        ("get_bandwidth", {"interval_seconds": 0}),
        ("get_bandwidth", {"interval_seconds": 61}),
    ],
)
async def test_network_is_not_touched_without_knowing_how(
    client: Client, network: Recorder, monkeypatch: pytest.MonkeyPatch, tool: str, arguments: Dict[str, Any]
) -> None:
    monkeypatch.setattr(macos.network, "bandwidth", network.function("bandwidth", []))

    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert network.calls == []
