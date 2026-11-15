"""The tools of mcp_server_macos.tools.printer, with macos.printer faked: nothing is printed."""

from datetime import datetime
from typing import Any, Dict

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio

OFFICE = macos.printer.Printer(
    name="Office_LaserJet",
    description="Office LaserJet",
    model="HP LaserJet",
    location="2nd floor",
    is_default=True,
    state="idle",
)
HOME = macos.printer.Printer(name="Home", description="Home Inkjet", model=None, location=None, is_default=False, state=None)
JOB = macos.printer.PrintJob(
    id=12,
    printer="Office_LaserJet",
    title="report.pdf",
    user="me",
    state="processing",
    size=48,
    created=datetime(2026, 11, 15, 9, 0),
)
LISTED_JOB = {
    "id": 12,
    "printer": "Office_LaserJet",
    "title": "report.pdf",
    "user": "me",
    "state": "processing",
    "size_kilobytes": 48,
    "created": "2026-11-15T09:00:00",
}


@pytest.fixture
def printer(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    recorder = Recorder()
    monkeypatch.setattr(macos.printer, "printers", lambda: [OFFICE, HOME])
    monkeypatch.setattr(macos.printer, "default", lambda: OFFICE)
    monkeypatch.setattr(macos.printer, "jobs", recorder.function("jobs", [JOB]))
    for name in ("set_default", "cancel"):
        monkeypatch.setattr(macos.printer, name, recorder.function(name))
    monkeypatch.setattr(macos.printer, "print_file", recorder.function("print_file", JOB))
    return recorder


async def test_list_printers(client: Client, printer: Recorder) -> None:
    result = await client.call_tool("list_printers", {})

    assert not result.is_error
    assert result.structured_content == {
        "printers": [
            {
                "name": "Office_LaserJet",
                "description": "Office LaserJet",
                "model": "HP LaserJet",
                "location": "2nd floor",
                "is_default": True,
                "state": "idle",
            },
            {"name": "Home", "description": "Home Inkjet", "model": None, "location": None, "is_default": False, "state": None},
        ],
        "default": "Office_LaserJet",
    }


async def test_list_printers_when_there_is_none(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(macos.printer, "printers", lambda: [])
    monkeypatch.setattr(macos.printer, "default", lambda: None)

    result = await client.call_tool("list_printers", {})

    assert result.structured_content == {"printers": [], "default": None}


async def test_set_default_printer(client: Client, printer: Recorder) -> None:
    result = await client.call_tool("set_default_printer", {"printer": "Home Inkjet"})

    assert text(result) == "Home Inkjet is the default printer."
    assert printer.calls == [("set_default", ("Home Inkjet",), {})]


async def test_print_file(client: Client, printer: Recorder) -> None:
    result = await client.call_tool("print_file", {"path": "/Users/me/report.pdf"})

    assert not result.is_error
    assert result.structured_content == LISTED_JOB
    assert printer.calls == [
        (
            "print_file",
            ("/Users/me/report.pdf", None),
            {"copies": 1, "pages": None, "two_sided": False, "black_and_white": False, "paper": None, "title": None},
        )
    ]


async def test_print_file_with_every_option(client: Client, printer: Recorder) -> None:
    await client.call_tool(
        "print_file",
        {
            "path": "/slides.pdf",
            "printer": "Office LaserJet",
            "copies": 2,
            "pages": "1-3,7",
            "two_sided": True,
            "black_and_white": True,
            "paper": "A4",
            "title": "Slides",
        },
    )

    assert printer.calls == [
        (
            "print_file",
            ("/slides.pdf", "Office LaserJet"),
            {"copies": 2, "pages": "1-3,7", "two_sided": True, "black_and_white": True, "paper": "A4", "title": "Slides"},
        )
    ]


@pytest.mark.parametrize(
    "arguments, call",
    [({}, ((None,), {"finished": False})), ({"printer": "Home", "finished": True}, (("Home",), {"finished": True}))],
)
async def test_list_print_jobs(client: Client, printer: Recorder, arguments: Dict[str, Any], call: Any) -> None:
    result = await client.call_tool("list_print_jobs", arguments)

    assert result.structured_content == {"result": [LISTED_JOB]}
    assert printer.calls == [("jobs", *call)]


async def test_cancel_print_job(client: Client, printer: Recorder) -> None:
    result = await client.call_tool("cancel_print_job", {"job_id": 12})

    assert text(result) == "Print job 12 canceled."
    assert printer.calls == [("cancel", (12, None), {})]


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("print_file", {}),
        ("print_file", {"path": ""}),
        ("print_file", {"path": "/a.pdf", "copies": 0}),
        ("print_file", {"path": "/a.pdf", "copies": 1000}),
        ("set_default_printer", {}),
        # 0 is the job printing now, and -1 every job, to CUPS.
        ("cancel_print_job", {"job_id": 0}),
        ("cancel_print_job", {"job_id": -1}),
    ],
)
async def test_printer_is_not_touched_without_knowing_what(
    client: Client, printer: Recorder, tool: str, arguments: Dict[str, Any]
) -> None:
    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert printer.calls == []
