"""
The window, camera, shortcut and event tools against this Mac: read only, and short waits. No window is
moved, resized or closed, the camera doesn't turn on, and nothing is asked of the user.
"""

import pytest
from mcp import Client

from tests.helpers import text
from tests.live.helpers import call

pytestmark = pytest.mark.anyio


async def test_windows_are_read(client: Client) -> None:
    settings = await call(client, "get_window_settings")
    assert settings["double_click_title_bar"] in ("zoom", "fill", "minimize", "nothing")
    if not settings["accessibility_permission"]:
        pytest.skip("Accessibility isn't granted here")

    for window in await call(client, "list_windows"):
        assert window["app"] and window["width"] >= 0 and window["height"] >= 0
    front = (await call(client, "get_front_window"))["window"]
    assert front is None or front["app"]
    assert (
        await call(client, "wait_for_window", {"app": "Finder", "title": "zq-nowhere-xj", "timeout_seconds": 0.5})
    ) == {"window": None}
    result = await client.call_tool("focus_window", {"app": "zq-no-such-app-xj"})
    assert result.is_error and "LookupError" in text(result)


async def test_cameras_are_listed(client: Client) -> None:
    found = await call(client, "list_cameras")

    assert isinstance(found["camera_permission"], bool)
    assert sum(camera["default"] for camera in found["cameras"]) == (1 if found["cameras"] else 0)


async def test_a_shortcut_nobody_presses(client: Client) -> None:
    result = await client.call_tool("wait_for_shortcut", {"keys": "ctrl+option+shift+f13", "timeout_seconds": 0.3})
    if result.is_error:
        # Listening needs Input Monitoring and Accessibility, which a build machine may not grant.
        assert "Input Monitoring" in text(result), text(result)
        pytest.skip("Input Monitoring isn't granted here")

    assert result.structured_content == {"pressed": False}


async def test_an_event_is_waited_for_in_a_process_of_its_own(client: Client) -> None:
    found = (await call(client, "wait_for_event", {"name": "displays_changed", "timeout_seconds": 1}))["event"]

    # Nothing is asked of the user, but a display connected or rearranged meanwhile is a right answer too.
    assert found is None or found["name"] == "displays_changed"
