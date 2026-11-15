"""The tools of mcp_server_macos.tools.document, with macos.document faked."""

import threading
from pathlib import Path
from typing import Any, Dict, List

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


async def test_read_document_text(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.document, "text", recorder.function("text", "Meeting minutes\n..."))

    result = await client.call_tool("read_document_text", {"path": "/Users/me/minutes.docx"})

    assert not result.is_error
    assert result.structured_content == {"text": "Meeting minutes\n..."}
    # Nothing a page refers to is fetched unless asked for: a page could make this Mac fetch what it wants.
    assert recorder.calls == [("text", ("/Users/me/minutes.docx",), {"resources": False})]


@pytest.mark.parametrize(
    "arguments, options",
    [
        ({}, {"paper": None, "margin": 72.0, "resources": False}),
        ({"paper": "a4", "margin_points": 36, "resources": True}, {"paper": "a4", "margin": 36.0, "resources": True}),
    ],
)
async def test_convert_document(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any], options: Dict[str, Any]
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.document, "convert", recorder.function("convert", Path("/Users/me/report.pdf")))

    result = await client.call_tool("convert_document", {"source": "report.docx", "output": "report.pdf", **arguments})

    assert not result.is_error
    assert result.structured_content == {"path": "/Users/me/report.pdf"}
    assert recorder.calls == [("convert", ("report.docx", "report.pdf"), options)]


async def test_documents_are_read_on_the_main_thread(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    # HTML is read by WebKit, which macOS only allows there: pymacos refuses elsewhere.
    threads: List[threading.Thread] = []

    def read(path: str, resources: bool) -> str:
        threads.append(threading.current_thread())
        return ""

    def convert(*args: Any, **options: Any) -> Path:
        threads.append(threading.current_thread())
        return Path("/x")

    monkeypatch.setattr(macos.document, "text", read)
    monkeypatch.setattr(macos.document, "convert", convert)

    await client.call_tool("read_document_text", {"path": "page.html"})
    await client.call_tool("convert_document", {"source": "page.html", "output": "page.txt"})

    assert threads == [threading.main_thread(), threading.main_thread()]


async def test_document_in_a_format_there_is_not(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    error = ValueError("can't write '.pages' documents")
    monkeypatch.setattr(macos.document, "convert", Recorder().function("convert", error=error))

    result = await client.call_tool("convert_document", {"source": "a.docx", "output": "a.pages"})

    assert result.is_error
    assert "can't write '.pages' documents" in text(result)


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("read_document_text", {}),
        ("read_document_text", {"path": ""}),
        ("convert_document", {"source": "a.docx"}),
        ("convert_document", {"source": "a.docx", "output": "a.pdf", "paper": "a3"}),
        ("convert_document", {"source": "a.docx", "output": "a.pdf", "margin_points": -1}),
    ],
)
async def test_documents_are_not_touched_without_knowing_which(
    client: Client, monkeypatch: pytest.MonkeyPatch, tool: str, arguments: Dict[str, Any]
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.document, "text", recorder.function("text", ""))
    monkeypatch.setattr(macos.document, "convert", recorder.function("convert", Path("/x")))

    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert recorder.calls == []
