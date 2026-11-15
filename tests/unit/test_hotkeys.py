"""The tools of mcp_server_macos.tools.hotkeys, with macos.hotkeys faked: the keyboard isn't listened to."""

import threading
from typing import Any, List

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("pressed", [True, False])
async def test_wait_for_shortcut(client: Client, monkeypatch: pytest.MonkeyPatch, pressed: bool) -> None:
    threads: List[Any] = []

    def layout() -> str:
        threads.append(("layout", threading.current_thread()))
        return "French"

    def wait(keys: str, *, timeout: float) -> bool:
        threads.append((keys, threading.current_thread()))
        return pressed

    monkeypatch.setattr(macos.keyboard, "layout", layout)
    monkeypatch.setattr(macos.hotkeys, "wait", wait)

    result = await client.call_tool("wait_for_shortcut", {"keys": "ctrl+option+a", "timeout_seconds": 5})

    assert result.structured_content == {"pressed": pressed}
    # The shortcut's "a" is found on the layout the main thread read; the wait stays off the main thread.
    assert [what for what, _ in threads] == ["layout", "ctrl+option+a"]
    assert threads[0][1] is threading.main_thread() and threads[1][1] is not threading.main_thread()


async def test_without_the_permissions_both_are_asked_for(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    asked = Recorder()
    monkeypatch.setattr(macos.keyboard, "layout", lambda: "ABC")
    monkeypatch.setattr(
        macos.hotkeys, "wait", asked.function("wait", error=macos.PermissionDeniedError("no Input Monitoring"))
    )
    monkeypatch.setattr(macos.hotkeys, "request_permission", asked.function("request_permission", False))

    result = await client.call_tool("wait_for_shortcut", {"keys": "f5"})

    assert asked.names == ["wait", "request_permission"]
    assert "Input Monitoring, and › Accessibility" in text(result)


@pytest.mark.parametrize(
    "arguments", [{"keys": ""}, {"keys": "f5", "timeout_seconds": 0}, {"keys": "f5", "timeout_seconds": 601}]
)
async def test_nothing_is_listened_to_without_what_it_needs(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Any
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.hotkeys, "wait", recorder.function("wait"))

    assert (await client.call_tool("wait_for_shortcut", arguments)).is_error
    assert recorder.calls == []
