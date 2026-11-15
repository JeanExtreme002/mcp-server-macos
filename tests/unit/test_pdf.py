"""The tools of mcp_server_macos.tools.pdf, with macos.pdf faked: no PDF is read or written."""

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple

import macos
import pytest
from mcp import Client
from mcp.types import ImageContent

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio

OUT = Path("/Users/me/out.pdf")


def match(page: int, found: str, x: float) -> Any:
    box = (x, 700.0, 50.0, 12.0)
    return macos.pdf.Match(page=page, text=found, box=box, lines=(box,), font="Helvetica", size=12.0)


async def test_get_pdf_info(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    metadata = macos.pdf.Metadata(
        title="Report",
        author="Ana",
        subject=None,
        keywords=["q3", "sales"],
        creator="Microsoft Word",
        producer="macOS Quartz PDFContext",
        created=datetime(2026, 11, 1, 9, 0),
        modified=None,
    )
    monkeypatch.setattr(macos.pdf, "metadata", recorder.function("metadata", metadata))
    monkeypatch.setattr(macos.pdf, "page_count", recorder.function("page_count", 12))

    result = await client.call_tool("get_pdf_info", {"path": "report.pdf", "password": "1234"})

    assert not result.is_error
    assert result.structured_content == {
        "pages": 12,
        "title": "Report",
        "author": "Ana",
        "subject": None,
        "keywords": ["q3", "sales"],
        "creator": "Microsoft Word",
        "producer": "macOS Quartz PDFContext",
        "created": "2026-11-01T09:00:00",
        "modified": None,
    }
    assert recorder.calls == [
        ("metadata", ("report.pdf",), {"password": "1234"}),
        ("page_count", ("report.pdf",), {"password": "1234"}),
    ]


async def test_encrypted_pdf_without_its_password_says_so_and_nothing_more(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Not a permission of macOS: no app to allow, only a password to give.
    error = macos.PermissionDeniedError("report.pdf is encrypted: pass its password")
    monkeypatch.setattr(macos.pdf, "metadata", Recorder().function("metadata", error=error))

    result = await client.call_tool("get_pdf_info", {"path": "report.pdf"})

    assert result.is_error
    assert "report.pdf is encrypted: pass its password" in text(result)
    assert "System Settings" not in text(result)
    assert "allow" not in text(result)


@pytest.mark.parametrize("arguments, pages", [({}, None), ({"pages": [1, 3]}, [1, 3])])
async def test_read_pdf_text(client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any], pages: Any) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.pdf, "text", recorder.function("text", "Page one\nPage three"))

    result = await client.call_tool("read_pdf_text", {"path": "a.pdf", **arguments})

    assert result.structured_content == {"text": "Page one\nPage three"}
    assert recorder.calls == [("text", ("a.pdf", pages), {"password": None})]


async def test_find_in_pdf(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.pdf, "find", recorder.function("find", [match(1, "Jane Doe", 72.0)]))

    result = await client.call_tool("find_in_pdf", {"path": "a.pdf", "text": "jane doe", "pages": [1]})

    assert result.structured_content == {
        "result": [{"page": 1, "text": "Jane Doe", "box": [72.0, 700.0, 50.0, 12.0], "font": "Helvetica", "size": 12.0}]
    }
    assert recorder.calls == [("find", ("a.pdf", "jane doe"), {"pages": [1], "password": None})]


async def test_find_in_pdf_with_a_regular_expression(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.pdf, "find", recorder.function("find", []))

    await client.call_tool("find_in_pdf", {"path": "a.pdf", "text": r"\d{3}-\d{2}-\d{4}", "regex": True})

    ((_, (_, target), _),) = recorder.calls
    assert isinstance(target, re.Pattern) and target.pattern == r"\d{3}-\d{2}-\d{4}"


async def test_bad_regular_expression_is_refused_before_pymacos_is_asked(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.pdf, "find", recorder.function("find", []))

    result = await client.call_tool("find_in_pdf", {"path": "a.pdf", "text": "(", "regex": True})

    assert result.is_error
    assert "'(' isn't a valid regular expression" in text(result)
    assert recorder.calls == []


async def test_render_pdf_page(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.pdf, "render", recorder.function("render", b"\x89PNG fake"))

    result = await client.call_tool("render_pdf_page", {"path": "a.pdf", "page": 2, "size": 2048})

    assert not result.is_error
    (image,) = result.content
    assert isinstance(image, ImageContent) and image.mime_type == "image/png"
    assert recorder.calls == [("render", ("a.pdf", 2), {"size": 2048, "password": None})]


async def test_bookmarks_and_form_fields(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    marks = [macos.pdf.Bookmark(title="Intro", page=1, level=0), macos.pdf.Bookmark(title="1.1", page=0, level=1)]
    fields = [
        macos.pdf.FormField(name="Full name", kind="text", value=None, options=(), page=1),
        macos.pdf.FormField(name="Plan", kind="choice", value="Pro", options=("Free", "Pro"), page=2),
        macos.pdf.FormField(name="Agree", kind="checkbox", value=False, options=(), page=2),
    ]
    monkeypatch.setattr(macos.pdf, "bookmarks", lambda path, password=None: marks)
    monkeypatch.setattr(macos.pdf, "form_fields", lambda path, password=None: fields)

    listed_marks = await client.call_tool("list_pdf_bookmarks", {"path": "a.pdf"})
    listed_fields = await client.call_tool("list_pdf_form_fields", {"path": "a.pdf"})

    assert listed_marks.structured_content == {
        "result": [{"title": "Intro", "page": 1, "level": 0}, {"title": "1.1", "page": 0, "level": 1}]
    }
    assert listed_fields.structured_content == {
        "result": [
            {"name": "Full name", "kind": "text", "value": None, "options": [], "page": 1},
            {"name": "Plan", "kind": "choice", "value": "Pro", "options": ["Free", "Pro"], "page": 2},
            {"name": "Agree", "kind": "checkbox", "value": False, "options": [], "page": 2},
        ]
    }


# The tools that write a file: each calls its function of pymacos as told, and says where it wrote.
WRITERS: Dict[str, Tuple[Dict[str, Any], str, Tuple[Any, ...], Dict[str, Any]]] = {
    "merge_pdfs": ({"inputs": ["a.pdf", "b.pdf"], "output": "c.pdf"}, "merge", (["a.pdf", "b.pdf"], "c.pdf"), {"password": None}),
    "extract_pdf_pages": (
        {"path": "a.pdf", "output": "b.pdf", "pages": [3, 1]},
        "extract",
        ("a.pdf", "b.pdf", [3, 1]),
        {"password": None},
    ),
    "rotate_pdf_pages": (
        {"path": "scan.pdf", "output": "scan.pdf", "degrees": 90, "pages": [2]},
        "rotate",
        ("scan.pdf", "scan.pdf", 90),
        {"pages": [2], "password": None},
    ),
    "encrypt_pdf": (
        {"path": "a.pdf", "output": "b.pdf", "password": "1234"},
        "encrypt",
        ("a.pdf", "b.pdf", "1234"),
        {"current_password": None, "owner_password": None},
    ),
    "decrypt_pdf": ({"path": "l.pdf", "output": "o.pdf", "password": "1234"}, "decrypt", ("l.pdf", "o.pdf", "1234"), {}),
    "ocr_pdf": (
        {"path": "scan.pdf", "output": "b.pdf", "languages": ["pt-BR"]},
        "ocr",
        ("scan.pdf", "b.pdf"),
        {"languages": ["pt-BR"], "redo": False, "password": None},
    ),
    "watermark_pdf": (
        {"path": "a.pdf", "output": "b.pdf", "text": "DRAFT"},
        "watermark",
        ("a.pdf", "b.pdf", "DRAFT"),
        {"color": "#808080", "opacity": 0.25, "password": None},
    ),
    "compress_pdf": ({"path": "a.pdf", "output": "b.pdf"}, "compress", ("a.pdf", "b.pdf"), {"password": None}),
    "grayscale_pdf": ({"path": "a.pdf", "output": "b.pdf"}, "grayscale", ("a.pdf", "b.pdf"), {"password": None}),
    "images_to_pdf": (
        {"images": ["1.jpg", "2.heic"], "output": "scan.pdf"},
        "from_images",
        (["1.jpg", "2.heic"], "scan.pdf"),
        {},
    ),
    "fill_pdf_form": (
        {"path": "form.pdf", "output": "filled.pdf", "values": {"Full name": "Jane Doe", "Agree": True}},
        "fill_form",
        ("form.pdf", "filled.pdf", {"Full name": "Jane Doe", "Agree": True}),
        {"password": None},
    ),
    "sign_pdf": (
        {"path": "c.pdf", "output": "s.pdf", "image": "sig.png", "near": "Signature:"},
        "sign",
        ("c.pdf", "s.pdf", "sig.png"),
        {"page": None, "position": None, "near": "Signature:", "side": "right", "width": 150.0, "password": None},
    ),
    "add_text_to_pdf": (
        {"path": "a.pdf", "output": "b.pdf", "text": "Jane Doe", "page": 2, "position": [120, 540], "size": 14},
        "add_text",
        ("a.pdf", "b.pdf", "Jane Doe"),
        {
            "page": 2,
            "position": (120.0, 540.0),
            "near": None,
            "side": "right",
            "size": 14.0,
            "color": "#000000",
            "font": None,
            "password": None,
        },
    ),
    "set_pdf_bookmarks": (
        {
            "path": "a.pdf",
            "output": "b.pdf",
            "bookmarks": [{"title": "Intro", "page": 1}, {"title": "1.1", "page": 4, "level": 1}],
        },
        "set_bookmarks",
        ("a.pdf", "b.pdf", [macos.pdf.Bookmark("Intro", 1, 0), macos.pdf.Bookmark("1.1", 4, 1)]),
        {"password": None},
    ),
}


@pytest.mark.parametrize("tool", sorted(WRITERS))
async def test_pdf_is_written_as_asked(client: Client, monkeypatch: pytest.MonkeyPatch, tool: str) -> None:
    arguments, function, args, options = WRITERS[tool]
    recorder = Recorder()
    monkeypatch.setattr(macos.pdf, function, recorder.function(function, OUT))

    result = await client.call_tool(tool, arguments)

    assert not result.is_error, text(result)
    assert result.structured_content == {"path": str(OUT)}
    assert recorder.calls == [(function, args, options)]


@pytest.mark.parametrize("position", ["top_left", "bottom_right"])
async def test_text_goes_to_a_corner(client: Client, monkeypatch: pytest.MonkeyPatch, position: str) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.pdf, "add_text", recorder.function("add_text", OUT))

    await client.call_tool("add_text_to_pdf", {"path": "a.pdf", "output": "b.pdf", "text": "x", "position": position})

    assert recorder.calls[0][2]["position"] == position


async def test_extract_pdf_images(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.pdf, "images", recorder.function("images", [Path("/out/page1-1.jpg"), Path("/out/page2-1.png")]))

    result = await client.call_tool("extract_pdf_images", {"path": "a.pdf", "folder": "/out"})

    assert result.structured_content == {"paths": ["/out/page1-1.jpg", "/out/page2-1.png"]}
    assert recorder.calls == [("images", ("a.pdf", "/out"), {"pages": None, "password": None})]


def done(kind: Any) -> Any:
    return kind(path=OUT, matches={"Jane Doe": 3}, pages={1: 2, 4: 1})


CHANGES = {"path": str(OUT), "matches": {"Jane Doe": 3}, "pages": {"1": 2, "4": 1}}


async def test_redact_pdf(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.pdf, "redact", recorder.function("redact", done(macos.pdf.Redaction)))

    result = await client.call_tool("redact_pdf", {"path": "c.pdf", "output": "p.pdf", "targets": ["Jane Doe"]})

    assert result.structured_content == CHANGES
    assert recorder.calls == [("redact", ("c.pdf", "p.pdf", ["Jane Doe"]), {"password": None})]


async def test_redact_pdf_with_patterns_names_them_by_their_source(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    redaction = macos.pdf.Redaction(path=OUT, matches={r"\d{3}-\d{2}-\d{4}": 2}, pages={1: 2})
    recorder = Recorder()
    monkeypatch.setattr(macos.pdf, "redact", recorder.function("redact", redaction))

    result = await client.call_tool(
        "redact_pdf", {"path": "c.pdf", "output": "p.pdf", "targets": [r"\d{3}-\d{2}-\d{4}"], "regex": True}
    )

    assert result.structured_content == {"path": str(OUT), "matches": {r"\d{3}-\d{2}-\d{4}": 2}, "pages": {"1": 2}}
    ((_, (_, _, targets), _),) = recorder.calls
    assert [target.pattern for target in targets] == [r"\d{3}-\d{2}-\d{4}"]


async def test_redaction_that_finds_nothing_is_an_error(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    error = ValueError("'Nobody' isn't in the PDF, so nothing was written")
    monkeypatch.setattr(macos.pdf, "redact", Recorder().function("redact", error=error))

    result = await client.call_tool("redact_pdf", {"path": "c.pdf", "output": "p.pdf", "targets": ["Nobody"]})

    assert result.is_error
    assert "'Nobody' isn't in the PDF" in text(result)


async def test_erase_from_pdf_everywhere(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.pdf, "erase", recorder.function("erase", done(macos.pdf.Edit)))

    result = await client.call_tool("erase_from_pdf", {"path": "d.pdf", "output": "e.pdf", "targets": ["DRAFT"], "pages": [1]})

    assert result.structured_content == CHANGES
    assert recorder.calls == [("erase", ("d.pdf", "e.pdf", ["DRAFT"]), {"background": "#ffffff", "pages": [1], "password": None})]


async def test_erase_some_of_the_places_a_text_shows(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    hits = [match(1, "DRAFT", 10.0), match(1, "DRAFT", 20.0), match(2, "DRAFT", 30.0)]
    recorder = Recorder()
    monkeypatch.setattr(macos.pdf, "find", recorder.function("find", hits))
    monkeypatch.setattr(macos.pdf, "erase", recorder.function("erase", done(macos.pdf.Edit)))

    result = await client.call_tool(
        "erase_from_pdf", {"path": "d.pdf", "output": "e.pdf", "targets": ["DRAFT"], "occurrences": [3, 1, 3]}
    )

    assert not result.is_error, text(result)
    # The places, as find_in_pdf numbers them, each once.
    assert recorder.calls == [
        ("find", ("d.pdf", "DRAFT"), {"pages": None, "password": None}),
        ("erase", ("d.pdf", "e.pdf", [hits[2], hits[0]]), {"background": "#ffffff", "password": None}),
    ]


@pytest.mark.parametrize(
    "arguments, why",
    [
        ({"targets": ["DRAFT"], "occurrences": [4]}, "occurrences must be from 1 to 3, the times the text shows, not 4"),
        ({"targets": ["DRAFT", "TODO"], "occurrences": [1]}, "occurrences goes with a single text"),
    ],
)
async def test_erase_places_that_are_not_there(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any], why: str
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.pdf, "find", lambda *a, **k: [match(1, "DRAFT", 1.0)] * 3)
    monkeypatch.setattr(macos.pdf, "erase", recorder.function("erase", done(macos.pdf.Edit)))

    result = await client.call_tool("erase_from_pdf", {"path": "d.pdf", "output": "e.pdf", **arguments})

    assert result.is_error
    assert why in text(result)
    assert recorder.calls == []


async def test_replace_in_pdf(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.pdf, "replace", recorder.function("replace", done(macos.pdf.Edit)))

    result = await client.call_tool(
        "replace_in_pdf", {"path": "d.pdf", "output": "f.pdf", "replacements": {"DRAFT": "FINAL", "2026": "2027"}}
    )

    assert result.structured_content == CHANGES
    assert recorder.calls == [
        (
            "replace",
            ("d.pdf", "f.pdf", {"DRAFT": "FINAL", "2026": "2027"}),
            {"color": "#000000", "background": "#ffffff", "font": None, "size": None, "pages": None, "password": None},
        )
    ]


async def test_replace_in_pdf_with_a_pattern_and_its_groups(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.pdf, "replace", recorder.function("replace", done(macos.pdf.Edit)))

    await client.call_tool(
        "replace_in_pdf", {"path": "d.pdf", "output": "f.pdf", "replacements": {r"Ana (\w+)": r"Maria \1"}, "regex": True}
    )

    ((_, (_, _, replacements), _),) = recorder.calls
    ((pattern, new),) = replacements.items()
    assert (pattern.pattern, new) == (r"Ana (\w+)", r"Maria \1")


async def test_replace_some_of_the_places_a_text_shows(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    hits = [match(1, "Ana Souza", 10.0), match(2, "Ana Souza", 20.0)]
    recorder = Recorder()
    monkeypatch.setattr(macos.pdf, "find", recorder.function("find", hits))
    monkeypatch.setattr(macos.pdf, "replace", recorder.function("replace", done(macos.pdf.Edit)))

    result = await client.call_tool(
        "replace_in_pdf",
        {"path": "l.pdf", "output": "r.pdf", "replacements": {"Ana Souza": "Maria Lima"}, "occurrences": [2], "size": 10},
    )

    assert not result.is_error, text(result)
    assert recorder.calls[1] == (
        "replace",
        ("l.pdf", "r.pdf", {hits[1]: "Maria Lima"}),
        {"color": "#000000", "background": "#ffffff", "font": None, "size": 10.0, "password": None},
    )


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("merge_pdfs", {"inputs": [], "output": "c.pdf"}),
        ("extract_pdf_pages", {"path": "a.pdf", "output": "b.pdf", "pages": []}),
        ("extract_pdf_pages", {"path": "a.pdf", "output": "b.pdf", "pages": [0]}),
        ("rotate_pdf_pages", {"path": "a.pdf", "output": "b.pdf", "degrees": 45}),
        ("encrypt_pdf", {"path": "a.pdf", "output": "b.pdf", "password": ""}),
        ("watermark_pdf", {"path": "a.pdf", "output": "b.pdf", "text": "x", "opacity": -0.1}),
        ("render_pdf_page", {"path": "a.pdf", "page": 0}),
        ("render_pdf_page", {"path": "a.pdf", "size": 5000}),
        ("add_text_to_pdf", {"path": "a.pdf", "output": "b.pdf", "text": "x", "position": "middle"}),
        ("add_text_to_pdf", {"path": "a.pdf", "output": "b.pdf", "text": "x", "position": [1]}),
        ("sign_pdf", {"path": "a.pdf", "output": "b.pdf", "image": "s.png", "side": "behind"}),
        ("redact_pdf", {"path": "a.pdf", "output": "b.pdf", "targets": []}),
        ("redact_pdf", {"path": "a.pdf", "output": "b.pdf", "targets": [""]}),
        ("redact_pdf", {"path": "a.pdf", "output": "b.pdf", "targets": ["("], "regex": True}),
        ("replace_in_pdf", {"path": "a.pdf", "output": "b.pdf", "replacements": {}}),
        ("replace_in_pdf", {"path": "a.pdf", "output": "b.pdf", "replacements": {"a": "b", "c": "d"}, "occurrences": [1]}),
        ("set_pdf_bookmarks", {"path": "a.pdf", "output": "b.pdf", "bookmarks": [{"title": "x", "page": -1}]}),
    ],
)
async def test_pdfs_are_not_touched_without_what_they_need(
    client: Client, monkeypatch: pytest.MonkeyPatch, tool: str, arguments: Dict[str, Any]
) -> None:
    recorder = Recorder()
    for name in macos.pdf.__all__:
        if callable(getattr(macos.pdf, name)) and not isinstance(getattr(macos.pdf, name), type):
            monkeypatch.setattr(macos.pdf, name, recorder.function(name, OUT))

    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert recorder.calls == []


async def test_replace_some_places_of_a_pattern_fills_its_groups_in(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    # pymacos writes the text given as it is in place of a match: the groups are filled in for each one.
    hits = [match(1, "Ana Souza", 10.0), match(2, "Ana\nLima", 20.0)]
    recorder = Recorder()
    monkeypatch.setattr(macos.pdf, "find", recorder.function("find", hits))
    monkeypatch.setattr(macos.pdf, "replace", recorder.function("replace", done(macos.pdf.Edit)))

    result = await client.call_tool(
        "replace_in_pdf",
        {
            "path": "l.pdf",
            "output": "r.pdf",
            "replacements": {r"Ana (\w+)": r"Maria \1"},
            "regex": True,
            "occurrences": [1, 2],
        },
    )

    assert not result.is_error, text(result)
    assert recorder.calls[1][1][2] == {hits[0]: "Maria Souza", hits[1]: "Maria Lima"}


async def test_heading_of_the_contents_is_written_back(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    # A page 0 is a heading that opens nothing: what list_pdf_bookmarks gives, set_pdf_bookmarks takes.
    recorder = Recorder()
    monkeypatch.setattr(macos.pdf, "set_bookmarks", recorder.function("set_bookmarks", OUT))

    result = await client.call_tool(
        "set_pdf_bookmarks",
        {
            "path": "a.pdf",
            "output": "b.pdf",
            "bookmarks": [{"title": "Part I", "page": 0}, {"title": "1", "page": 1, "level": 1}],
        },
    )

    assert not result.is_error, text(result)
    marks = recorder.calls[0][1][2]
    assert all(isinstance(mark, macos.pdf.Bookmark) for mark in marks)
    assert [(mark.title, mark.page, mark.level) for mark in marks] == [("Part I", 0, 0), ("1", 1, 1)]


async def test_pdf_descriptions_say_what_is_lost(client: Client) -> None:
    described = {tool.name: tool for tool in (await client.list_tools()).tools}

    # The encryption, for every tool that writes a PDF but the one that encrypts.
    output = described["rotate_pdf_pages"].input_schema["properties"]["output"]["description"]
    assert "The result isn't encrypted" in output
    # The text layer of the pages erasing or replacing redraws.
    for tool in ("erase_from_pdf", "replace_in_pdf"):
        assert "the rest of its text can't be selected" in " ".join((described[tool].description or "").split())


async def test_literal_replacement_of_some_places_of_a_pattern_is_not_matched_again(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A pattern that looks around what it finds ("123" after "ID ") can't match the found text alone:
    # a replacement with no group to fill in is written as it is, without trying.
    hits = [match(1, "123", 10.0)]
    recorder = Recorder()
    monkeypatch.setattr(macos.pdf, "find", recorder.function("find", hits))
    monkeypatch.setattr(macos.pdf, "replace", recorder.function("replace", done(macos.pdf.Edit)))

    result = await client.call_tool(
        "replace_in_pdf",
        {"path": "l.pdf", "output": "r.pdf", "replacements": {r"(?<=ID )\d+": "456"}, "regex": True, "occurrences": [1]},
    )

    assert not result.is_error, text(result)
    assert recorder.calls[1][1][2] == {hits[0]: "456"}


@pytest.mark.parametrize("occurrences", [None, [1]])
async def test_replacement_that_refers_to_a_group_the_pattern_has_not_is_explained(
    client: Client, monkeypatch: pytest.MonkeyPatch, occurrences: Any
) -> None:
    def replace(*args: Any, **options: Any) -> Any:
        # As pymacos does with a mapping of patterns: it fills the groups in, through re.
        re.compile(r"Ana (\w+)").sub(r"Maria \2", "Ana Souza")

    monkeypatch.setattr(macos.pdf, "find", lambda *a, **k: [match(1, "Ana Souza", 10.0)])
    monkeypatch.setattr(macos.pdf, "replace", replace)
    arguments = {"path": "l.pdf", "output": "r.pdf", "replacements": {r"Ana (\w+)": r"Maria \2"}, "regex": True}
    if occurrences:
        arguments["occurrences"] = occurrences

    result = await client.call_tool("replace_in_pdf", arguments)

    assert result.is_error
    assert "isn't a valid replacement for the pattern" in text(result)


async def test_encrypt_pdf_does_not_say_its_result_is_not_encrypted(client: Client) -> None:
    (tool,) = [tool for tool in (await client.list_tools()).tools if tool.name == "encrypt_pdf"]

    assert "isn't encrypted" not in tool.input_schema["properties"]["output"]["description"]
