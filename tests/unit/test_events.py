"""The tools of mcp_server_macos.tools.events, with the process that listens faked: nothing is listened to."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, List

import macos
import pytest
from mcp import Client

from mcp_server_macos.tools import events
from tests.helpers import text

pytestmark = pytest.mark.anyio

SAFARI = {"name": "Safari", "bundle_id": "com.apple.Safari", "pid": 7, "path": "/Applications/Safari.app"}


def answering(monkeypatch: pytest.MonkeyPatch, calls: List[Any], **done: Any) -> None:
    def run(command: List[str], **options: Any) -> Any:
        calls.append((command, options))
        if "error" in done:
            raise done["error"]
        return subprocess.CompletedProcess(command, done.get("code", 0), done.get("stdout", ""), done.get("stderr", ""))

    monkeypatch.setattr(subprocess, "run", run)


@pytest.mark.parametrize("found", [{"name": "app_quit", "app": SAFARI, "path": None, "device": None}, None])
async def test_wait_for_event(client: Client, monkeypatch: pytest.MonkeyPatch, found: Any) -> None:
    calls: List[Any] = []
    answering(monkeypatch, calls, stdout="a warning on stdout\n" + json.dumps(found) + "\n")

    result = await client.call_tool("wait_for_event", {"name": "app_quit", "timeout_seconds": 5})

    assert result.structured_content == {"event": found}
    # A process of its own listens on its own main thread, for as long as asked and a moment to start.
    ((command, options),) = calls
    assert command[0] == sys.executable and command[-2:] == ["app_quit", "5.0"]
    assert options["timeout"] == 5.0 + events._STARTING


@pytest.mark.parametrize(
    "done, said",
    [
        ({"code": 1, "stderr": "Traceback...\nmacos.MacOSError: no run loop"}, "macos.MacOSError: no run loop"),
        ({"error": subprocess.TimeoutExpired("python", 35)}, "didn't end in time"),
    ],
)
async def test_a_listening_that_fails(client: Client, monkeypatch: pytest.MonkeyPatch, done: Any, said: str) -> None:
    answering(monkeypatch, [], **done)

    result = await client.call_tool("wait_for_event", {"name": "wake"})

    assert result.is_error and said in text(result)


def test_the_listening_process_says_what_happened(monkeypatch: pytest.MonkeyPatch) -> None:
    app = macos.apps.App(name="Safari", bundle_id="com.apple.Safari", pid=7, path="/Applications/Safari.app")
    happened = {
        "app_quit": macos.events.Event(name="app_quit", app=app, path=None, device=None),
        "volume_mounted": macos.events.Event(name="volume_mounted", app=None, path=Path("/Volumes/USB"), device=None),
    }
    monkeypatch.setattr(macos.events, "wait", lambda name, timeout: happened.get(name))

    assert events._wait_here("app_quit", 1.0) == {"name": "app_quit", "app": SAFARI, "path": None, "device": None}
    assert events._wait_here("volume_mounted", 1.0)["path"] == "/Volumes/USB"  # type: ignore[index]
    assert events._wait_here("wake", 1.0) is None


def test_every_event_of_pymacos_is_offered() -> None:
    assert events.EventName.__args__ == macos.events.NAMES  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "arguments", [{"name": "lunch"}, {"name": "wake", "timeout_seconds": 0}, {"name": "wake", "timeout_seconds": 601}]
)
async def test_nothing_is_listened_to_without_what_it_needs(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Any
) -> None:
    calls: List[Any] = []
    answering(monkeypatch, calls)

    assert (await client.call_tool("wait_for_event", arguments)).is_error
    assert calls == []
