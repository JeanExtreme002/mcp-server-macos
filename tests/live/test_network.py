"""The network tools against this Mac: the connection is read and measured, and nothing is turned off or connected."""

import pytest
from mcp import Client

from tests.helpers import text
from tests.live.helpers import call

pytestmark = pytest.mark.anyio


async def test_get_network_status(client: Client) -> None:
    status = await call(client, "get_network_status")

    assert isinstance(status["online"], bool)
    assert status["wifi_power"] in (True, False, None)
    if status["online"]:
        assert status["interface"]
    if status["wifi_signal"] is not None:
        assert status["wifi_signal"]["quality"] in ("excellent", "good", "fair", "poor")
        assert status["wifi_signal"]["rssi_dbm"] < 0
    assert isinstance(status["dns_servers"], list)
    assert set(status["proxies"]) == {"http", "https", "socks", "auto_config_url", "exceptions"}


async def test_interfaces_and_what_goes_through_them(client: Client) -> None:
    interfaces = await call(client, "list_network_interfaces")
    assert interfaces, "a Mac has network interfaces"
    names = [found["name"] for found in interfaces]
    assert "lo0" not in names

    for use in await call(client, "get_bandwidth", {"interval_seconds": 0.3}):
        assert use["download_mbps"] >= 0 and use["upload_mbps"] >= 0
        assert use["interface"] in names


async def test_vpns(client: Client) -> None:
    for vpn in await call(client, "list_vpns"):
        assert vpn["status"] in ("connected", "connecting", "disconnecting", "disconnected")

    result = await client.call_tool("connect_vpn", {"name": "no VPN is named like this"})
    assert result.is_error
    assert "MacOSError" in text(result)
