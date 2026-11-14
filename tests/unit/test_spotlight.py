"""The tools of mcp_server_macos.tools.spotlight, with macos.spotlight faked."""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio

FOUND = [Path("/Users/me/Documents/invoice 1.pdf"), Path("/Users/me/Downloads/invoice-2.pdf")]


@pytest.fixture
def spotlight(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    recorder = Recorder()
    monkeypatch.setattr(macos.spotlight, "search", recorder.function("search", list(FOUND)))
    monkeypatch.setattr(macos.spotlight, "search_name", recorder.function("search_name", list(FOUND)))
    return recorder


@pytest.mark.parametrize(
    "tool, function, argument", [("search_files", "search", "query"), ("search_files_by_name", "search_name", "name")]
)
async def test_search(client: Client, spotlight: Recorder, tool: str, function: str, argument: str) -> None:
    result = await client.call_tool(tool, {argument: "kind:pdf invoice"})

    assert not result.is_error
    assert result.structured_content == {
        "result": ["/Users/me/Documents/invoice 1.pdf", "/Users/me/Downloads/invoice-2.pdf"]
    }
    # 50 files at most, and a search that doesn't end is stopped after a minute.
    assert spotlight.calls == [(function, ("kind:pdf invoice",), {"folder": None, "limit": 50, "timeout": 60.0})]


@pytest.mark.parametrize(
    "tool, function, argument", [("search_files", "search", "query"), ("search_files_by_name", "search_name", "name")]
)
async def test_search_in_a_folder(client: Client, spotlight: Recorder, tool: str, function: str, argument: str) -> None:
    result = await client.call_tool(tool, {argument: "report", "folder": "~/Documents", "limit": 3})

    assert not result.is_error
    assert spotlight.calls == [(function, ("report",), {"folder": "~/Documents", "limit": 3, "timeout": 60.0})]


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("search_files", {}),
        ("search_files", {"query": ""}),
        ("search_files", {"query": "a", "limit": 0}),
        ("search_files", {"query": "a", "limit": 1001}),
        ("search_files_by_name", {}),
        ("search_files_by_name", {"name": ""}),
        ("search_files_by_name", {"name": "a", "limit": "all"}),
    ],
)
async def test_search_refuses_what_it_does_not_take(
    client: Client, spotlight: Recorder, tool: str, arguments: Dict[str, Any]
) -> None:
    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert spotlight.calls == []


async def test_search_that_does_not_end(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    error = macos.CommandTimeoutError(["mdfind"], 60.0)
    monkeypatch.setattr(macos.spotlight, "search", Recorder().function("search", error=error))

    result = await client.call_tool("search_files", {"query": "anything"})

    assert result.is_error
    assert "CommandTimeoutError" in text(result)


async def test_get_file_metadata(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    metadata = {
        "kMDItemContentType": "com.adobe.pdf",
        "kMDItemNumberOfPages": 3,
        "kMDItemFSSize": 48213,
        "kMDItemContentCreationDate": datetime(2026, 11, 14, 8, 37, 14),
        "kMDItemAuthors": ["Ana", "Bo"],
        "kMDItemPixelHeight": 1080.5,
        "kMDItemFSIsExtensionHidden": False,
    }
    monkeypatch.setattr(macos.spotlight, "metadata", recorder.function("metadata", metadata))

    result = await client.call_tool("get_file_metadata", {"path": "/Users/me/report.pdf"})

    assert not result.is_error
    assert result.structured_content == {
        "result": {
            "kMDItemContentType": "com.adobe.pdf",
            "kMDItemNumberOfPages": 3,
            "kMDItemFSSize": 48213,
            "kMDItemContentCreationDate": "2026-11-14T08:37:14",  # JSON has no date
            "kMDItemAuthors": ["Ana", "Bo"],
            "kMDItemPixelHeight": 1080.5,
            "kMDItemFSIsExtensionHidden": False,
        }
    }
    assert recorder.calls == [("metadata", ("/Users/me/report.pdf",), {})]


@pytest.mark.parametrize(
    "error, expected",
    [
        (FileNotFoundError("/nope"), "FileNotFoundError: /nope"),
        (PermissionError(13, "Permission denied", "/private/x"), "PermissionError"),
    ],
)
async def test_get_file_metadata_of_a_file_it_cannot_reach(
    client: Client, monkeypatch: pytest.MonkeyPatch, error: Exception, expected: str
) -> None:
    monkeypatch.setattr(macos.spotlight, "metadata", Recorder().function("metadata", error=error))

    result = await client.call_tool("get_file_metadata", {"path": "/nope"})

    assert result.is_error
    assert expected in text(result)
