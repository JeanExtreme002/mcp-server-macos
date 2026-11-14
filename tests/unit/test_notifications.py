"""The tools of mcp_server_macos.tools.notifications, with macos.notify faked."""

from typing import Any, Dict, List, Tuple

import macos
import pytest
from mcp import Client

from tests.helpers import text

pytestmark = pytest.mark.anyio

Call = Tuple[Tuple[Any, ...], Dict[str, Any]]


@pytest.fixture
def notified(monkeypatch: pytest.MonkeyPatch) -> List[Call]:
    """The calls made to macos.notify, which posts nothing."""
    calls: List[Call] = []
    monkeypatch.setattr(macos, "notify", lambda *args, **kwargs: calls.append((args, kwargs)))
    return calls


async def test_send_notification(client: Client, notified: List[Call]) -> None:
    result = await client.call_tool("send_notification", {"message": "Build finished"})

    assert not result.is_error
    assert text(result) == "Notification sent."
    assert notified == [(("Build finished",), {"title": None, "subtitle": None, "sound": None})]


async def test_send_notification_with_everything(client: Client, notified: List[Call]) -> None:
    result = await client.call_tool(
        "send_notification", {"message": "Build finished", "title": "CI", "subtitle": "main", "sound": "Glass"}
    )

    assert not result.is_error
    assert notified == [(("Build finished",), {"title": "CI", "subtitle": "main", "sound": "Glass"})]


async def test_send_notification_takes_text_as_it_is(client: Client, notified: List[Call]) -> None:
    # Quotes, newlines and emoji aren't the server's to escape: pymacos passes text as arguments.
    message = "It's \"done\" — 100% ✅\n$(rm -rf ~); `id`"

    result = await client.call_tool("send_notification", {"message": message, "title": "-n"})

    assert not result.is_error
    assert notified == [((message,), {"title": "-n", "subtitle": None, "sound": None})]


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"title": "No message"},
        {"message": ""},
        {"message": None},
        {"message": ["a", "list"]},
        {"message": "ok", "title": {"not": "text"}},
    ],
)
async def test_send_notification_refuses_invalid_arguments(
    client: Client, notified: List[Call], arguments: Dict[str, Any]
) -> None:
    result = await client.call_tool("send_notification", arguments)

    assert result.is_error
    assert "send_notification" in text(result)
    assert notified == []


@pytest.mark.parametrize(
    "error, expected",
    [
        (ValueError("no alert sound is named 'nope'"), "ValueError: no alert sound is named 'nope'"),
        (
            macos.PermissionDeniedError("notifications are turned off for Script Editor"),
            "PermissionDeniedError: notifications are turned off for Script Editor "
            "This needs the Notifications permission, which only the user can grant.",
        ),
        (macos.NotSupportedError("macos.notifications requires macOS"), "NotSupportedError: macos.notifications"),
        (macos.CommandError(["osascript"], 1, "execution error"), "CommandError: "),
    ],
)
async def test_send_notification_reports_what_macos_refused(
    client: Client, monkeypatch: pytest.MonkeyPatch, error: Exception, expected: str
) -> None:
    def notify(*args: Any, **kwargs: Any) -> None:
        raise error

    monkeypatch.setattr(macos, "notify", notify)

    result = await client.call_tool("send_notification", {"message": "hello", "sound": "nope"})

    assert result.is_error
    assert expected in text(result)


async def test_send_notification_is_not_read_only(client: Client) -> None:
    (tool,) = [tool for tool in (await client.list_tools()).tools if tool.name == "send_notification"]

    assert tool.annotations is not None
    assert tool.annotations.read_only_hint is False
    assert tool.annotations.destructive_hint is False
    assert tool.input_schema["required"] == ["message"]
    assert set(tool.input_schema["properties"]) == {"message", "title", "subtitle", "sound"}


async def test_send_notification_says_where_to_turn_notifications_on(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    def notify(*args: Any, **kwargs: Any) -> None:
        calls.append(args)
        raise macos.PermissionDeniedError("notifications are turned off for Script Editor")

    monkeypatch.setattr(macos, "notify", notify)

    result = await client.call_tool("send_notification", {"message": "hello"})

    assert result.is_error
    assert (
        "Ask them to allow Script Editor, which macOS shows the notifications as coming from, "
        "in System Settings › Notifications › Script Editor, and then try again."
    ) in text(result)
    # Not the app that runs the server, as for the other permissions.
    assert "MCP client" not in text(result)
    # macOS has no prompt to show for it, so nothing was asked and nothing run twice.
    assert len(calls) == 1


@pytest.mark.parametrize("allowed", [True, False, None])
async def test_check_notification_permission(client: Client, monkeypatch: pytest.MonkeyPatch, allowed: Any) -> None:
    # None: macOS can't tell, as when Script Editor has never posted a notification.
    monkeypatch.setattr(macos.notifications, "is_allowed", lambda: allowed)

    result = await client.call_tool("check_notification_permission", {})

    assert not result.is_error
    assert result.structured_content == {"allowed": allowed}
