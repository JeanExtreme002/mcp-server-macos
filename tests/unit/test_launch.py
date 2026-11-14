"""The tool of mcp_server_macos.tools.launch, with macos.launch and macos.apps faked."""

from typing import Any, Dict

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    """The calls made to the two functions that open something: nothing is opened."""
    recorder = Recorder()
    monkeypatch.setattr(macos.launch, "open", recorder.function("open"))
    monkeypatch.setattr(macos.apps, "open_with", recorder.function("open_with"))
    return recorder


@pytest.mark.parametrize(
    "arguments, call",
    [
        ({"target": "/Users/me/report.pdf"}, ("open", ("/Users/me/report.pdf",), {"background": False})),
        ({"target": "https://python.org", "background": True}, ("open", ("https://python.org",), {"background": True})),
        (
            {"target": "/Users/me/photo.png", "app": "Preview"},
            ("open_with", ("/Users/me/photo.png", "Preview"), {"background": False}),
        ),
        (
            {"target": "notes.md", "app": "com.apple.TextEdit", "background": True},
            ("open_with", ("notes.md", "com.apple.TextEdit"), {"background": True}),
        ),
    ],
)
async def test_open_file_or_url(client: Client, opened: Recorder, arguments: Dict[str, Any], call: Any) -> None:
    result = await client.call_tool("open_file_or_url", arguments)

    assert not result.is_error
    assert text(result) == "Opened {}.".format(arguments["target"])
    assert opened.calls == [call]


@pytest.mark.parametrize(
    "error, expected",
    [
        (FileNotFoundError("/nope/file.txt"), "FileNotFoundError: /nope/file.txt"),
        (macos.CommandError(["open"], 1, "No application knows how to open URL x://y"), "No application knows how to open"),
    ],
)
async def test_open_file_or_url_that_does_not_open(
    client: Client, monkeypatch: pytest.MonkeyPatch, error: Exception, expected: str
) -> None:
    monkeypatch.setattr(macos.launch, "open", Recorder().function("open", error=error))

    result = await client.call_tool("open_file_or_url", {"target": "/nope/file.txt"})

    assert result.is_error
    assert expected in text(result)


@pytest.mark.parametrize("arguments", [{}, {"target": ""}, {"target": None}, {"target": ["a", "b"]}])
async def test_open_file_or_url_needs_a_target(client: Client, opened: Recorder, arguments: Dict[str, Any]) -> None:
    result = await client.call_tool("open_file_or_url", arguments)

    assert result.is_error
    assert opened.calls == []


async def test_open_file_or_url_is_marked_as_able_to_do_anything(client: Client) -> None:
    # A file that's a script runs, and a URL goes wherever it says: a client should ask the user first.
    (tool,) = [tool for tool in (await client.list_tools()).tools if tool.name == "open_file_or_url"]

    assert tool.annotations is not None
    assert tool.annotations.destructive_hint is True
    assert tool.annotations.open_world_hint is True
    assert tool.annotations.read_only_hint is False
