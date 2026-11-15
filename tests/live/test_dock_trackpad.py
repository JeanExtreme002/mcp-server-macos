"""The Dock and trackpad tools against this Mac: read only. A change would restart the Dock in front of the user."""

import macos
import pytest
from mcp import Client

from tests.helpers import text
from tests.live.helpers import call

pytestmark = pytest.mark.anyio


async def test_dock_settings_are_read(client: Client) -> None:
    settings = await call(client, "get_dock_settings")

    assert 16 <= settings["size"] <= 128
    assert settings["position"] in ("left", "bottom", "right")
    assert settings["minimize_effect"] in ("genie", "scale", "suck")
    assert set(settings["hot_corners"]) == {"top_left", "top_right", "bottom_left", "bottom_right"}
    for corner in settings["hot_corners"].values():
        assert corner["action"] is None or corner["action"] in macos.dock.HOT_CORNER_ACTIONS

    items = await call(client, "list_dock_items")
    assert all(app["name"] for app in items["apps"])
    assert all(folder["display"] in ("stack", "folder") for folder in items["folders"])


async def test_trackpad_settings_are_read(client: Client) -> None:
    settings = await call(client, "get_trackpad_settings")

    assert 0 <= settings["tracking_speed"] <= 1
    assert settings["click_pressure"] in ("light", "medium", "firm")
    assert set(settings["gestures"]) <= set(macos.trackpad.GESTURES)


async def test_wrong_settings_change_nothing(client: Client) -> None:
    before = await call(client, "get_trackpad_settings")

    result = await client.call_tool(
        "set_trackpad_settings", {"tap_to_click": not before["tap_to_click"], "gestures": {"pinch": True}}
    )

    assert result.is_error
    assert "gestures must be among" in text(result)
    assert await call(client, "get_trackpad_settings") == before
