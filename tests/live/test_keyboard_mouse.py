"""
The keyboard and mouse tools against this Mac: read only. No key is pressed, nothing is clicked and the
pointer isn't moved, since whatever is in front would get them.
"""

import pytest
from mcp import Client

from tests.helpers import text
from tests.live.helpers import call

pytestmark = pytest.mark.anyio


async def test_keyboard_is_read(client: Client) -> None:
    status = await call(client, "get_keyboard_status")

    assert status["layout"] in status["layouts"] or status["layouts"] == []
    assert isinstance(status["caps_lock"], bool)
    assert status["backlight"] is None or 0 <= status["backlight"] <= 100

    settings = await call(client, "get_keyboard_settings")
    assert settings["key_repeat_interval_seconds"] > 0
    assert isinstance(settings["system_shortcuts"], dict)
    assert isinstance(await call(client, "get_app_shortcuts"), dict)


async def test_mouse_is_read(client: Client) -> None:
    settings = await call(client, "get_mouse_settings")

    assert 0 <= settings["tracking_speed"] <= 1
    assert settings["double_click_speed_seconds"] > 0


@pytest.mark.parametrize("tool", ["wait_for_key_press", "wait_for_click"])
async def test_nothing_is_pressed_or_clicked_in_a_moment(client: Client, tool: str) -> None:
    result = await client.call_tool(tool, {"timeout_seconds": 0.3})
    if result.is_error:
        # Listening needs Input Monitoring, which a build machine may not grant: the error says so.
        assert "Input Monitoring" in text(result), text(result)
        pytest.skip("Input Monitoring isn't granted here")

    assert result.structured_content in ({"key": None}, {"click": None})
