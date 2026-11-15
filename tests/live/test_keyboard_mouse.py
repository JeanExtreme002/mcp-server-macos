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
async def test_waiting_ends_in_a_moment(client: Client, tool: str) -> None:
    # Listening needs Input Monitoring, which a build machine may not grant: checked first, since a tool
    # missing it asks macOS to prompt the user.
    if not (await call(client, "get_keyboard_status"))["input_monitoring_permission"]:
        pytest.skip("Input Monitoring isn't granted here")

    result = await client.call_tool(tool, {"timeout_seconds": 0.3})
    assert not result.is_error, text(result)

    # Nothing is asked of the user, but a key pressed or a click made meanwhile is a right answer too.
    name, event = result.structured_content.popitem() if result.structured_content else (None, None)
    assert name == ("key" if tool == "wait_for_key_press" else "click")
    if event is not None:
        assert set(event) >= ({"key", "modifiers", "shortcut"} if name == "key" else {"x", "y", "button", "count"})
