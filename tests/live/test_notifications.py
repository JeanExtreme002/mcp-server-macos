"""send_notification against this Mac: a notification shows up."""

import pytest
from mcp import Client

from tests.helpers import text

pytestmark = pytest.mark.anyio


async def test_send_notification(client: Client) -> None:
    result = await client.call_tool(
        "send_notification", {"message": "A test of send_notification.", "title": "mcp-server-macos"}
    )

    if result.is_error and "PermissionDeniedError" in text(result):
        pytest.skip("notifications are turned off for Script Editor on this Mac")
    assert not result.is_error, text(result)
    assert text(result) == "Notification sent."


async def test_send_notification_refuses_an_unknown_sound(client: Client) -> None:
    result = await client.call_tool("send_notification", {"message": "Never shown.", "sound": "no-such-sound"})

    assert result.is_error
    assert "ValueError" in text(result)


async def test_check_notification_permission(client: Client) -> None:
    result = await client.call_tool("check_notification_permission", {})

    assert not result.is_error, text(result)
    assert result.structured_content is not None
    assert result.structured_content["allowed"] in (True, False, None)
