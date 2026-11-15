"""The tools of mcp_server_macos.tools.finder, with macos.finder faked: no file is touched, Finder isn't relaunched."""

import contextlib
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

import macos
import pytest
from mcp import Client
from mcp.types import ImageContent

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


@pytest.fixture
def batches(monkeypatch: pytest.MonkeyPatch) -> List[str]:
    log: List[str] = []

    @contextlib.contextmanager
    def batch() -> Iterator[None]:
        log.append("start")
        yield
        log.append("end")

    monkeypatch.setattr(macos.settings, "batch", batch)
    return log


async def test_get_finder_info(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(macos.finder, "tags", lambda path: ["Work"])
    monkeypatch.setattr(macos.finder, "is_alias", lambda path: True)
    monkeypatch.setattr(macos.finder, "resolve_alias", lambda path: Path("/Users/me/Projects"))
    monkeypatch.setattr(macos.finder, "has_custom_icon", lambda path: False)

    result = await client.call_tool("get_finder_info", {"path": "Projects alias"})

    assert result.structured_content == {
        "tags": ["Work"],
        "is_alias": True,
        "alias_target": "/Users/me/Projects",
        "has_custom_icon": False,
    }


async def test_alias_whose_original_is_gone(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    def gone(path: Any) -> Any:
        raise FileNotFoundError("the original is gone")

    monkeypatch.setattr(macos.finder, "tags", lambda path: [])
    monkeypatch.setattr(macos.finder, "is_alias", lambda path: True)
    monkeypatch.setattr(macos.finder, "resolve_alias", gone)
    monkeypatch.setattr(macos.finder, "has_custom_icon", lambda path: False)

    result = await client.call_tool("get_finder_info", {"path": "Old alias"})

    assert not result.is_error
    assert result.structured_content is not None
    assert (result.structured_content["is_alias"], result.structured_content["alias_target"]) == (True, None)


async def test_get_file_thumbnail(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.finder, "thumbnail", recorder.function("thumbnail", b"\x89PNG fake"))

    result = await client.call_tool("get_file_thumbnail", {"path": "report.pdf", "size": 512})

    (image,) = result.content
    assert isinstance(image, ImageContent)
    assert recorder.calls == [("thumbnail", ("report.pdf",), {"size": 512})]


@pytest.mark.parametrize(
    "tool, arguments, function, answer, args, expected",
    [
        (
            "add_file_tags",
            {"tags": ["Work", "Red"]},
            "add_tags",
            ["Red", "Work"],
            ("a.pdf", "Work", "Red"),
            {"tags": ["Red", "Work"]},
        ),
        ("remove_file_tags", {"tags": ["Red"]}, "remove_tags", ["Work"], ("a.pdf", "Red"), {"tags": ["Work"]}),
    ],
)
async def test_tags_are_added_and_removed(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
    tool: str,
    arguments: Dict[str, Any],
    function: str,
    answer: Any,
    args: Tuple[Any, ...],
    expected: Any,
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.finder, function, recorder.function(function, answer))

    result = await client.call_tool(tool, {"path": "a.pdf", **arguments})

    assert result.structured_content == expected
    assert recorder.calls == [(function, args, {})]


async def test_set_file_tags(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.finder, "set_tags", recorder.function("set_tags"))
    monkeypatch.setattr(macos.finder, "tags", lambda path: [])

    result = await client.call_tool("set_file_tags", {"path": "a.pdf", "tags": []})

    assert result.structured_content == {"tags": []}
    assert recorder.calls == [("set_tags", ("a.pdf", []), {})]


# The tools that act on a file and say where: each calls its function of pymacos as told.
ACTIONS: Dict[str, Tuple[Dict[str, Any], str, Any, Tuple[Any, ...], Dict[str, Any], Any]] = {
    "move_to_trash": (
        {"path": "old.log"},
        "trash",
        Path("/Users/me/.Trash/old.log"),
        ("old.log",),
        {},
        {"path": "/Users/me/.Trash/old.log"},
    ),
    "make_alias": (
        {"target": "a.pdf", "alias": "~/Desktop"},
        "make_alias",
        Path("/Users/me/Desktop/a.pdf alias"),
        ("a.pdf", "~/Desktop"),
        {},
        {"path": "/Users/me/Desktop/a.pdf alias"},
    ),
    "compress_to_zip": (
        {"path": "Project"},
        "compress",
        Path("/Users/me/Project.zip"),
        ("Project", None),
        {},
        {"path": "/Users/me/Project.zip"},
    ),
    "extract_zip": (
        {"archive": "p.zip"},
        "extract",
        Path("/Users/me"),
        ("p.zip", None),
        {"overwrite": False},
        {"path": "/Users/me"},
    ),
    "reveal_in_finder": ({"path": "a.pdf"}, "reveal", None, ("a.pdf",), {}, {"result": "Revealed a.pdf."}),
    "quick_look": ({"path": "a.pdf"}, "quick_look", None, ("a.pdf",), {}, {"result": "Showing a.pdf."}),
    "set_file_icon": (
        {"path": "Projects", "image": "logo.png"},
        "set_icon",
        None,
        ("Projects", "logo.png"),
        {},
        {"result": "Icon set on Projects."},
    ),
    "remove_file_icon": (
        {"path": "Projects"},
        "remove_icon",
        None,
        ("Projects",),
        {},
        {"result": "Icon removed from Projects."},
    ),
    "restart_finder": ({}, "restart", None, (), {}, {"result": "Finder relaunched."}),
}


@pytest.mark.parametrize("tool", sorted(ACTIONS))
async def test_finder_does_as_asked(client: Client, monkeypatch: pytest.MonkeyPatch, tool: str) -> None:
    arguments, function, answer, args, options, expected = ACTIONS[tool]
    recorder = Recorder()
    monkeypatch.setattr(macos.finder, function, recorder.function(function, answer))

    result = await client.call_tool(tool, arguments)

    assert not result.is_error, text(result)
    assert result.structured_content == expected
    assert recorder.calls == [(function, args, options)]


async def test_extract_zip_refuses_to_write_over_files_unless_told(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = FileExistsError("p.zip would write over 2 files in /Users/me")
    monkeypatch.setattr(macos.finder, "extract", Recorder().function("extract", error=error))

    result = await client.call_tool("extract_zip", {"archive": "p.zip"})

    assert result.is_error
    assert "FileExistsError" in text(result)


@pytest.mark.parametrize(
    "found, expected",
    [(None, None), ("change", {"path": "/Users/me/Downloads/a.pdf", "kind": "created", "is_dir": False})],
)
async def test_wait_for_folder_change(
    client: Client, monkeypatch: pytest.MonkeyPatch, found: Any, expected: Any
) -> None:
    recorder = Recorder()
    event = macos.finder.Event(path=Path("/Users/me/Downloads/a.pdf"), kind="created", is_dir=False)
    monkeypatch.setattr(macos.finder, "wait_for_change", recorder.function("wait_for_change", event if found else None))

    result = await client.call_tool("wait_for_folder_change", {"folder": "~/Downloads", "pattern": ["*.pdf"]})

    assert result.structured_content == {"change": expected}
    assert recorder.calls == [
        ("wait_for_change", ("~/Downloads",), {"pattern": ["*.pdf"], "recursive": True, "timeout": 60.0})
    ]


async def test_get_finder_selection(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(macos.finder, "selection", lambda: [Path("/Users/me/a.pdf"), Path("/Users/me/b.png")])
    monkeypatch.setattr(macos.finder, "current_folder", lambda: Path("/Users/me"))

    result = await client.call_tool("get_finder_selection", {})

    assert result.structured_content == {
        "selected": ["/Users/me/a.pdf", "/Users/me/b.png"],
        "current_folder": "/Users/me",
    }


async def test_find_largest_files(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(
        macos.finder, "largest", recorder.function("largest", [(Path("/Users/me/big.mov"), 4_000_000_000)])
    )

    result = await client.call_tool("find_largest_files", {"folder": "~", "count": 5})

    assert result.structured_content == {"result": [{"path": "/Users/me/big.mov", "size_bytes": 4_000_000_000}]}
    assert recorder.calls == [("largest", ("~", 5), {"at_least": 1_000_000})]


SETTINGS = {
    "show_hidden_files": False,
    "show_extensions": True,
    "show_path_bar": True,
    "show_status_bar": False,
    "show_desktop_icons": True,
    "show_library_folder": False,
    "show_full_path_in_title": False,
    "default_view": "list",
    "search_scope": "current_folder",
    "folders_first": True,
    "extension_change_warning": True,
    "remove_old_trash_items": False,
    "quit_menu": False,
}


async def test_get_finder_settings(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in SETTINGS.items():
        monkeypatch.setattr(macos.finder, name, lambda value=value: value)
    monkeypatch.setattr(macos.finder, "new_window_folder", lambda: Path("/Users/me/Downloads"))
    monkeypatch.setattr(
        macos.finder,
        "drives_on_desktop",
        lambda: {"internal": False, "external": True, "removable": True, "servers": False},
    )
    monkeypatch.setattr(
        macos.finder,
        "desktop_view",
        lambda: {
            "icon_size": 64,
            "grid_spacing": 54,
            "text_size": 12,
            "sort": None,
            "show_item_info": False,
            "labels_on_bottom": True,
        },
    )

    result = await client.call_tool("get_finder_settings", {})

    assert not result.is_error, text(result)
    settings = result.structured_content
    assert settings is not None
    assert {name: settings[name] for name in SETTINGS} == SETTINGS
    assert settings["new_window_folder"] == "/Users/me/Downloads"
    assert settings["desktop_view"]["sort"] == "free"  # placed freely, which pymacos says with None


async def test_set_finder_settings_relaunches_finder_once(
    client: Client, monkeypatch: pytest.MonkeyPatch, batches: List[str]
) -> None:
    recorder = Recorder()
    for name in macos.finder.__all__:
        if name.startswith("set_"):
            monkeypatch.setattr(macos.finder, name, recorder.function(name))

    result = await client.call_tool(
        "set_finder_settings",
        {
            "show_hidden_files": True,
            "default_view": "columns",
            "drives_on_desktop": {"external": False, "servers": True},
        },
    )

    assert not result.is_error, text(result)
    assert batches == ["start", "end"]
    assert recorder.calls == [
        ("set_show_hidden_files", (True,), {}),
        ("set_default_view", ("columns",), {}),
        ("set_show_drives_on_desktop", (), {"external": False, "servers": True}),
    ]


async def test_every_finder_setter_is_offered(client: Client) -> None:
    # Each setting of macos.finder is offered by set_finder_settings, but the desktop's view, which has its own tool.
    (tool,) = [tool for tool in (await client.list_tools()).tools if tool.name == "set_finder_settings"]
    offered = set(tool.input_schema["properties"])
    setters = {name[len("set_") :] for name in macos.finder.__all__ if name.startswith("set_")} - {
        "tags",
        "icon",
        "desktop_view",
    }
    named = {"show_drives_on_desktop": "drives_on_desktop"}

    assert {named.get(name, name) for name in setters} == offered


@pytest.mark.parametrize(
    "arguments, options",
    [
        ({"icon_size": 48, "sort": "kind"}, {"icon_size": 48, "sort": "kind"}),
        ({"sort": "free"}, {"sort": None}),
        ({"labels_on_bottom": False, "text_size": 10}, {"text_size": 10, "labels_on_bottom": False}),
    ],
)
async def test_set_desktop_view(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any], options: Dict[str, Any]
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.finder, "set_desktop_view", recorder.function("set_desktop_view"))

    result = await client.call_tool("set_desktop_view", arguments)

    assert not result.is_error, text(result)
    assert recorder.calls == [("set_desktop_view", (), options)]


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("set_finder_settings", {}),
        ("set_finder_settings", {"drives_on_desktop": {}}),
        ("set_finder_settings", {"default_view": "tiles"}),
        ("set_finder_settings", {"drives_on_desktop": {"usb": True}}),
        ("set_desktop_view", {}),
        ("set_desktop_view", {"icon_size": 8}),
        ("set_desktop_view", {"sort": "color"}),
        ("add_file_tags", {"path": "a.pdf", "tags": []}),
        ("move_to_trash", {"path": ""}),
        ("wait_for_folder_change", {"folder": "~", "timeout_seconds": 601}),
        ("find_largest_files", {"folder": "~", "count": 0}),
    ],
)
async def test_finder_is_not_touched_without_what_it_needs(
    client: Client, monkeypatch: pytest.MonkeyPatch, batches: List[str], tool: str, arguments: Dict[str, Any]
) -> None:
    recorder = Recorder()
    for name in macos.finder.__all__:
        if callable(getattr(macos.finder, name)) and not isinstance(getattr(macos.finder, name), type):
            monkeypatch.setattr(macos.finder, name, recorder.function(name))

    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert recorder.calls == []
    assert batches == []
