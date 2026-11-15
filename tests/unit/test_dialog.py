"""The tools of mcp_server_macos.tools.dialog, with macos.dialog faked: no dialog is shown."""

from pathlib import Path
from typing import Any, Dict

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


def fake(monkeypatch: pytest.MonkeyPatch, function: str, answer: Any = None) -> Recorder:
    recorder = Recorder()
    monkeypatch.setattr(macos.dialog, function, recorder.function(function, answer))
    return recorder


@pytest.mark.parametrize(
    "arguments, options",
    [
        ({}, {"detail": None, "timeout": 120.0}),
        ({"detail": "12 files copied", "timeout_seconds": 5}, {"detail": "12 files copied", "timeout": 5.0}),
    ],
)
async def test_show_alert(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any], options: Dict[str, Any]
) -> None:
    recorder = fake(monkeypatch, "alert")

    result = await client.call_tool("show_alert", {"message": "Backup finished", **arguments})

    assert not result.is_error
    assert text(result) == "Alert shown."
    assert recorder.calls == [("alert", ("Backup finished",), options)]


@pytest.mark.parametrize("answer", [True, False])
async def test_ask_confirmation(client: Client, monkeypatch: pytest.MonkeyPatch, answer: bool) -> None:
    recorder = fake(monkeypatch, "confirm", answer)

    result = await client.call_tool(
        "ask_confirmation", {"message": "Delete the old logs?", "title": "Cleanup", "ok": "Delete", "cancel": "Keep"}
    )

    assert not result.is_error
    assert result.structured_content == {"confirmed": answer}
    assert recorder.calls == [
        ("confirm", ("Delete the old logs?",), {"title": "Cleanup", "ok": "Delete", "cancel": "Keep", "timeout": 120.0})
    ]


async def test_ask_confirmation_with_the_buttons_of_macos(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = fake(monkeypatch, "confirm", True)

    await client.call_tool("ask_confirmation", {"message": "Continue?"})

    assert recorder.calls == [
        ("confirm", ("Continue?",), {"title": None, "ok": "OK", "cancel": "Cancel", "timeout": 120.0})
    ]


@pytest.mark.parametrize("answer", ["Jean", "", None])
async def test_ask_text(client: Client, monkeypatch: pytest.MonkeyPatch, answer: Any) -> None:
    # None: the user cancelled, which isn't the same as answering with nothing.
    recorder = fake(monkeypatch, "prompt", answer)

    result = await client.call_tool("ask_text", {"message": "What's your name?"})

    assert not result.is_error
    assert result.structured_content == {"text": answer}
    assert recorder.calls == [
        ("prompt", ("What's your name?",), {"default": "", "title": None, "hidden": False, "timeout": 120.0})
    ]


async def test_ask_text_for_a_password(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = fake(monkeypatch, "prompt", "hunter2")

    result = await client.call_tool(
        "ask_text", {"message": "Password?", "hidden": True, "title": "Login", "default": "x", "timeout_seconds": 30}
    )

    assert result.structured_content == {"text": "hunter2"}
    assert recorder.calls == [
        ("prompt", ("Password?",), {"default": "x", "title": "Login", "hidden": True, "timeout": 30.0})
    ]


@pytest.mark.parametrize("answer", ["Blue", None])
async def test_ask_choice(client: Client, monkeypatch: pytest.MonkeyPatch, answer: Any) -> None:
    recorder = fake(monkeypatch, "choose", answer)

    result = await client.call_tool(
        "ask_choice", {"options": ["Red", "Blue"], "prompt": "Pick a color", "default": "Red", "title": "Colors"}
    )

    assert not result.is_error
    assert result.structured_content == {"choice": answer}
    assert recorder.calls == [
        (
            "choose",
            (["Red", "Blue"],),
            {"prompt": "Pick a color", "default": "Red", "title": "Colors", "timeout": 120.0},
        )
    ]


async def test_ask_for_one_file(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = fake(monkeypatch, "choose_file", Path("/Users/me/a b.pdf"))

    result = await client.call_tool(
        "ask_for_files", {"prompt": "Which report?", "types": ["pdf"], "folder": "~/Documents"}
    )

    assert not result.is_error
    assert result.structured_content == {"paths": ["/Users/me/a b.pdf"]}
    assert recorder.calls == [
        ("choose_file", ("Which report?",), {"types": ["pdf"], "folder": "~/Documents", "timeout": 120.0})
    ]


async def test_ask_for_several_files(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = fake(monkeypatch, "choose_files", [Path("/a.png"), Path("/b.png")])

    result = await client.call_tool("ask_for_files", {"multiple": True})

    assert result.structured_content == {"paths": ["/a.png", "/b.png"]}
    assert recorder.calls == [("choose_files", (None,), {"types": None, "folder": None, "timeout": 120.0})]


@pytest.mark.parametrize(
    "tool, arguments, function, answer",
    [
        ("ask_for_files", {}, "choose_file", None),
        ("ask_for_files", {"multiple": True}, "choose_files", []),
        ("ask_for_folder", {}, "choose_folder", None),
    ],
)
async def test_picker_that_is_cancelled(
    client: Client, monkeypatch: pytest.MonkeyPatch, tool: str, arguments: Dict[str, Any], function: str, answer: Any
) -> None:
    fake(monkeypatch, function, answer)

    result = await client.call_tool(tool, arguments)

    assert not result.is_error
    assert result.structured_content == {"paths": []}


async def test_ask_for_folder(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = fake(monkeypatch, "choose_folder", Path("/Users/me/Projects"))

    result = await client.call_tool("ask_for_folder", {"prompt": "Where?", "folder": "/Users/me"})

    assert result.structured_content == {"paths": ["/Users/me/Projects"]}
    assert recorder.calls == [("choose_folder", ("Where?",), {"folder": "/Users/me", "timeout": 120.0})]


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("show_alert", {}),
        ("show_alert", {"message": ""}),
        ("show_alert", {"message": "Hi", "timeout_seconds": 0}),
        ("show_alert", {"message": "Hi", "timeout_seconds": 601}),
        ("ask_confirmation", {}),
        ("ask_confirmation", {"message": "Sure?", "ok": ""}),
        ("ask_confirmation", {"message": "Sure?", "timeout_seconds": 86400}),
        ("ask_text", {}),
        ("ask_text", {"message": "Name?", "timeout_seconds": -1}),
        ("ask_choice", {}),
        ("ask_choice", {"options": []}),
        ("ask_choice", {"options": "Red"}),
        ("ask_for_files", {"types": "pdf"}),
    ],
)
async def test_dialog_is_not_shown_without_what_it_needs(
    client: Client, monkeypatch: pytest.MonkeyPatch, tool: str, arguments: Dict[str, Any]
) -> None:
    recorder = Recorder()
    for name in ("alert", "confirm", "prompt", "choose", "choose_file", "choose_files", "choose_folder"):
        monkeypatch.setattr(macos.dialog, name, recorder.function(name))

    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert recorder.calls == []


@pytest.mark.parametrize(
    "tool, arguments, function",
    [
        ("ask_choice", {"options": ["Red"], "timeout_seconds": 30}, "choose"),
        ("ask_for_files", {"timeout_seconds": 30}, "choose_file"),
        ("ask_for_files", {"multiple": True, "timeout_seconds": 30}, "choose_files"),
        ("ask_for_folder", {"timeout_seconds": 30}, "choose_folder"),
    ],
)
async def test_the_list_and_pickers_give_up_after_their_timeout(
    client: Client, monkeypatch: pytest.MonkeyPatch, tool: str, arguments: Dict[str, Any], function: str
) -> None:
    # They waited for the user with no time limit: they give up as the other dialogs do now, as cancelled.
    recorder = fake(monkeypatch, function, [] if function == "choose_files" else None)

    result = await client.call_tool(tool, arguments)

    assert not result.is_error, text(result)
    assert recorder.calls[0][2]["timeout"] == 30.0


@pytest.mark.parametrize("tool", ["ask_choice", "ask_for_files", "ask_for_folder"])
async def test_the_list_and_pickers_refuse_a_timeout_past_the_longest_wait(client: Client, tool: str) -> None:
    arguments: Dict[str, Any] = {"timeout_seconds": 601}
    if tool == "ask_choice":
        arguments["options"] = ["Red"]

    assert (await client.call_tool(tool, arguments)).is_error
