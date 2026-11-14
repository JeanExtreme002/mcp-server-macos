"""
The tools that can only be read from in a test: opening files, shortcuts, authentication, Bluetooth and maps.

Nothing is opened or run, nobody is asked for a fingerprint, no device is connected and Maps stays closed.
"""

from pathlib import Path

import pytest
from mcp import Client

from tests.helpers import text
from tests.live.helpers import call

pytestmark = pytest.mark.anyio


async def test_file_that_does_not_exist_is_not_opened(client: Client, tmp_path: Path) -> None:
    result = await client.call_tool("open_file_or_url", {"target": str(tmp_path / "nope.txt")})

    assert result.is_error
    assert "FileNotFoundError" in text(result)


async def test_shortcuts(client: Client) -> None:
    result = await client.call_tool("list_shortcuts", {})
    if result.is_error:
        pytest.skip("the Shortcuts app doesn't answer here: {}".format(text(result)))
    assert result.structured_content is not None
    assert all(isinstance(name, str) for name in result.structured_content["result"])

    result = await client.call_tool("run_shortcut", {"name": "no shortcut is named like this", "timeout_seconds": 60})
    assert result.is_error


async def test_check_user_authentication(client: Client) -> None:
    availability = await call(client, "check_user_authentication")

    assert isinstance(availability["available"], bool)
    assert isinstance(availability["touch_id"], bool)


async def test_get_bluetooth_status(client: Client) -> None:
    result = await client.call_tool("get_bluetooth_status", {})
    if result.is_error:
        # A machine whose Bluetooth can't be asked: said, with what to allow, not guessed.
        assert "Error" in text(result)
        pytest.skip("Bluetooth can't be read here: {}".format(text(result)))

    status = result.structured_content
    assert status is not None
    assert status["power"] in (True, False, None)
    for device in status["devices"]:
        assert device["name"] and isinstance(device["connected"], bool)
        assert all(0 <= level <= 100 for level in device["battery_percent"].values())


async def test_geocoder(client: Client) -> None:
    # Apple's service, over the network: a machine without it, or without an answer in time, skips.
    result = await client.call_tool("geocode_address", {"address": "1 Infinite Loop, Cupertino", "limit": 1})
    if result.is_error:
        assert "MainThreadError" not in text(result), "the geocoder must be asked on the main thread"
        pytest.skip("the geocoder doesn't answer here: {}".format(text(result)))

    assert result.structured_content is not None
    (place,) = result.structured_content["result"]
    assert place["country_code"] == "US"
    assert 37 < place["latitude"] < 38 and -123 < place["longitude"] < -121

    result = await client.call_tool("reverse_geocode", {"latitude": 48.8584, "longitude": 2.2945})
    if result.is_error:
        pytest.skip("the geocoder doesn't answer here: {}".format(text(result)))
    assert result.structured_content is not None
    assert result.structured_content["place"]["country_code"] == "FR"
