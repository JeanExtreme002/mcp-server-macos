"""The tools of mcp_server_macos.tools.shortcuts, with macos.shortcuts faked: no shortcut is run."""

from pathlib import Path
from typing import Any, Dict

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


@pytest.fixture
def shortcuts(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    recorder = Recorder()
    monkeypatch.setattr(macos.shortcuts, "list", recorder.function("list", ["Make GIF", "Translate"]))
    monkeypatch.setattr(macos.shortcuts, "run", recorder.function("run", "Hello"))
    return recorder


@pytest.mark.parametrize("arguments, folder", [({}, None), ({"folder": "Work"}, "Work"), ({"folder": "none"}, "none")])
async def test_list_shortcuts(client: Client, shortcuts: Recorder, arguments: Dict[str, Any], folder: Any) -> None:
    result = await client.call_tool("list_shortcuts", arguments)

    assert not result.is_error
    assert result.structured_content == {"result": ["Make GIF", "Translate"]}
    assert shortcuts.calls == [("list", (), {"folder": folder})]


async def test_list_shortcuts_of_a_folder_there_is_not(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(macos.shortcuts, "list", Recorder().function("list", error=LookupError("no folder named 'Nope'")))

    result = await client.call_tool("list_shortcuts", {"folder": "Nope"})

    assert result.is_error
    assert "no folder named 'Nope'" in text(result)


@pytest.mark.parametrize(
    "arguments, options",
    [
        ({}, {"input": None, "output": None, "timeout": 120.0}),
        ({"input_text": "Hola"}, {"input": "Hola", "output": None, "timeout": 120.0}),
        ({"input_text": ""}, {"input": "", "output": None, "timeout": 120.0}),
        (
            {"input_files": ["/a b.png", "/c.png"], "output_path": "/out.gif", "timeout_seconds": 30},
            {"input": [Path("/a b.png"), Path("/c.png")], "output": "/out.gif", "timeout": 30.0},
        ),
    ],
)
async def test_run_shortcut(client: Client, shortcuts: Recorder, arguments: Dict[str, Any], options: Dict[str, Any]) -> None:
    result = await client.call_tool("run_shortcut", {"name": "Translate", **arguments})

    assert not result.is_error, text(result)
    assert result.structured_content == {"output": "Hello"}
    assert shortcuts.calls == [("run", ("Translate",), options)]


async def test_run_shortcut_gives_files_as_files(client: Client, shortcuts: Recorder) -> None:
    # A path given as text would reach the shortcut as text, not as the file.
    await client.call_tool("run_shortcut", {"name": "Make GIF", "input_files": ["/a.png"]})

    ((_, _, options),) = shortcuts.calls
    assert all(isinstance(file, Path) for file in options["input"])


async def test_run_shortcut_without_a_text_output(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(macos.shortcuts, "run", Recorder().function("run", None))

    result = await client.call_tool("run_shortcut", {"name": "Make GIF"})

    assert not result.is_error
    assert result.structured_content == {"output": None}


@pytest.mark.parametrize(
    "error, expected",
    [
        (macos.ShortcutNotFoundError(["shortcuts"], 1, "Couldn't find shortcut"), "ShortcutNotFoundError"),
        (macos.CommandTimeoutError(["shortcuts"], 120.0), "CommandTimeoutError"),
    ],
)
async def test_run_shortcut_that_fails(
    client: Client, monkeypatch: pytest.MonkeyPatch, error: Exception, expected: str
) -> None:
    monkeypatch.setattr(macos.shortcuts, "run", Recorder().function("run", error=error))

    result = await client.call_tool("run_shortcut", {"name": "Nope"})

    assert result.is_error
    assert expected in text(result)


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"name": ""},
        {"name": "x", "input_text": "a", "input_files": ["/b"]},
        {"name": "x", "input_files": []},
        {"name": "x", "input_files": "/a.png"},
        {"name": "x", "timeout_seconds": 0},
        {"name": "x", "timeout_seconds": 601},
    ],
)
async def test_run_shortcut_refuses_what_it_does_not_take(
    client: Client, shortcuts: Recorder, arguments: Dict[str, Any]
) -> None:
    result = await client.call_tool("run_shortcut", arguments)

    assert result.is_error
    assert shortcuts.calls == []


async def test_run_shortcut_is_marked_as_able_to_do_anything(client: Client) -> None:
    (tool,) = [tool for tool in (await client.list_tools()).tools if tool.name == "run_shortcut"]

    assert tool.annotations is not None
    assert tool.annotations.destructive_hint is True
    assert tool.annotations.open_world_hint is True
