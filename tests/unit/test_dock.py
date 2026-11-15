"""The tools of mcp_server_macos.tools.dock, with macos.dock faked: the Dock isn't changed or restarted."""

import contextlib
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

import anyio
import macos
import pytest
from mcp import Client

from mcp_server_macos.tools import dock
from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio

SAFARI = macos.dock.DockApp(name="Safari", path=Path("/Applications/Safari.app"), bundle_id="com.apple.Safari")
DOWNLOADS = macos.dock.DockFolder(
    name="Downloads", path=Path("/Users/me/Downloads"), view="grid", sort="date_added", display="stack"
)
GETTERS = {
    "autohide": False,
    "size": 48,
    "position": "bottom",
    "magnification": None,
    "autohide_delay": 0.5,
    "autohide_duration": None,
    "show_recents": False,
    "minimize_effect": "genie",
    "show_indicators": True,
    "minimize_to_app": False,
    "dim_hidden_apps": False,
    "only_open_apps": False,
    "launch_animation": True,
    "auto_rearrange_spaces": True,
    "separate_spaces_per_display": True,
    "group_windows_by_app": False,
    "switch_to_space_with_app": True,
}


@pytest.fixture
def batches(monkeypatch: pytest.MonkeyPatch) -> List[str]:
    """The batches of settings changed, each of which restarts the Dock once at its end."""
    log: List[str] = []

    @contextlib.contextmanager
    def batch() -> Iterator[None]:
        log.append("start")
        yield
        log.append("end")

    monkeypatch.setattr(macos.settings, "batch", batch)
    return log


@pytest.fixture
def mac(monkeypatch: pytest.MonkeyPatch, batches: List[str]) -> Recorder:
    recorder = Recorder()
    for name, value in GETTERS.items():
        monkeypatch.setattr(macos.dock, name, lambda value=value: value)
    monkeypatch.setattr(macos.dock, "hot_corners", lambda: {"top_left": "mission_control", "top_right": None})
    monkeypatch.setattr(macos.dock, "hot_corner_modifiers", lambda: {"top_left": "cmd", "top_right": None})
    monkeypatch.setattr(macos.dock, "apps", lambda: [SAFARI])
    monkeypatch.setattr(macos.dock, "folders", lambda: [DOWNLOADS])
    for name in macos.dock.__all__:
        if name.startswith("set_") or name in ("restart", "add_spacer"):
            monkeypatch.setattr(macos.dock, name, recorder.function(name))
    monkeypatch.setattr(macos.dock, "add_app", recorder.function("add_app", SAFARI))
    monkeypatch.setattr(macos.dock, "add_folder", recorder.function("add_folder", DOWNLOADS))
    monkeypatch.setattr(macos.dock, "remove_app", recorder.function("remove_app", True))
    monkeypatch.setattr(macos.dock, "remove_folder", recorder.function("remove_folder", True))
    monkeypatch.setattr(macos.dock, "remove_spacers", recorder.function("remove_spacers", 2))
    return recorder


async def test_get_dock_settings(client: Client, mac: Recorder) -> None:
    result = await client.call_tool("get_dock_settings", {})

    assert not result.is_error
    settings = result.structured_content
    assert settings is not None
    assert (settings["size"], settings["position"], settings["autohide_delay_seconds"]) == (48, "bottom", 0.5)
    assert settings["hot_corners"] == {
        "top_left": {"action": "mission_control", "modifier": "cmd"},
        "top_right": {"action": None, "modifier": None},
    }
    assert mac.calls == []


async def test_list_dock_items(client: Client, mac: Recorder) -> None:
    result = await client.call_tool("list_dock_items", {})

    assert result.structured_content == {
        "apps": [{"name": "Safari", "path": "/Applications/Safari.app", "bundle_id": "com.apple.Safari"}],
        "folders": [
            {
                "name": "Downloads",
                "path": "/Users/me/Downloads",
                "view": "grid",
                "sort": "date_added",
                "display": "stack",
            }
        ],
    }


async def test_set_dock_settings_restarts_the_dock_once(client: Client, mac: Recorder, batches: List[str]) -> None:
    result = await client.call_tool(
        "set_dock_settings",
        {
            "autohide": True,
            "size": 48,
            "position": "left",
            "magnification": "off",
            "autohide_delay_seconds": 0,
            "autohide_duration_seconds": "default",
            "minimize_effect": "scale",
            "separate_spaces_per_display": False,
        },
    )

    assert not result.is_error, text(result)
    assert batches == ["start", "end"]
    assert mac.calls == [
        ("set_autohide", (True,), {}),
        ("set_size", (48,), {}),
        ("set_position", ("left",), {}),
        ("set_magnification", (None,), {}),
        ("set_autohide_delay", (0.0,), {}),
        ("set_autohide_duration", (None,), {}),
        ("set_minimize_effect", ("scale",), {}),
        ("set_separate_spaces_per_display", (False,), {}),
    ]
    assert text(result).startswith("Changed: autohide, size, position, magnification,")


async def test_every_dock_setter_is_offered(client: Client, mac: Recorder) -> None:
    # Each setting get_dock_settings reads, set_dock_settings changes (the hot corners have their own tool).
    names = {name[len("set_") :] for name in macos.dock.__all__ if name.startswith("set_")} - {"hot_corner"}
    arguments = {
        "autohide": True,
        "size": 32,
        "position": "right",
        "magnification": 64,
        "autohide_delay_seconds": 1,
        "autohide_duration_seconds": 0.2,
        "show_recents": True,
        "minimize_effect": "genie",
        "show_indicators": False,
        "minimize_to_app": True,
        "dim_hidden_apps": True,
        "only_open_apps": True,
        "launch_animation": False,
        "auto_rearrange_spaces": False,
        "separate_spaces_per_display": True,
        "group_windows_by_app": True,
        "switch_to_space_with_app": False,
    }

    result = await client.call_tool("set_dock_settings", arguments)

    assert not result.is_error, text(result)
    assert {name[len("set_") :] for name in mac.names} == names


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"size": 8},
        {"size": 200},
        {"position": "top"},
        {"magnification": "huge"},
        {"minimize_effect": "fade"},
        {"autohide_delay_seconds": -1},
    ],
)
async def test_set_dock_settings_changes_nothing_when_a_setting_is_wrong(
    client: Client, mac: Recorder, batches: List[str], arguments: Dict[str, Any]
) -> None:
    result = await client.call_tool("set_dock_settings", arguments)

    assert result.is_error
    assert mac.calls == []
    assert batches == []


async def test_hot_corner_actions_are_those_of_pymacos() -> None:
    offered = set(dock.Action.__args__)  # type: ignore[attr-defined]

    assert offered == set(macos.dock.HOT_CORNER_ACTIONS)


@pytest.mark.parametrize(
    "arguments, call, said",
    [
        (
            {"corner": "bottom_right", "action": "lock_screen"},
            ("bottom_right", "lock_screen"),
            "The bottom right corner does lock_screen.",
        ),
        (
            {"corner": "top_left", "action": None, "modifier": "cmd"},
            ("top_left", None),
            "The top left corner does nothing.",
        ),
    ],
)
async def test_set_hot_corner(
    client: Client, mac: Recorder, arguments: Dict[str, Any], call: Tuple[Any, ...], said: str
) -> None:
    result = await client.call_tool("set_hot_corner", arguments)

    assert text(result) == said
    assert mac.calls == [("set_hot_corner", call, {"modifier": arguments.get("modifier")})]


async def test_apps_folders_and_spacers(client: Client, mac: Recorder) -> None:
    added = await client.call_tool("add_app_to_dock", {"app": "Safari", "index": 0})
    folder = await client.call_tool("add_folder_to_dock", {"folder": "~/Downloads", "view": "grid"})
    removed = await client.call_tool("remove_app_from_dock", {"app": "Podcasts"})
    spacer = await client.call_tool("add_dock_spacer", {"small": True})
    spacers = await client.call_tool("remove_dock_spacers", {})
    restarted = await client.call_tool("restart_dock", {})

    assert added.structured_content == {
        "name": "Safari",
        "path": "/Applications/Safari.app",
        "bundle_id": "com.apple.Safari",
    }
    assert folder.structured_content is not None and folder.structured_content["view"] == "grid"
    assert [text(result) for result in (removed, spacer, spacers, restarted)] == [
        "Podcasts is out of the Dock.",
        "Spacer added.",
        "2 spacers removed.",
        "The Dock restarted.",
    ]
    assert mac.calls == [
        ("add_app", ("Safari",), {"index": 0}),
        ("add_folder", ("~/Downloads",), {"view": "grid", "sort": "date_added", "display": "stack"}),
        ("remove_app", ("Podcasts",), {}),
        ("add_spacer", (), {"index": None, "small": True}),
        ("remove_spacers", (), {}),
        ("restart", (), {}),
    ]


async def test_what_was_not_in_the_dock_is_said(client: Client, mac: Recorder, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(macos.dock, "remove_app", lambda app: False)
    monkeypatch.setattr(macos.dock, "remove_folder", lambda folder: False)

    app = await client.call_tool("remove_app_from_dock", {"app": "Chess"})
    folder = await client.call_tool("remove_folder_from_dock", {"folder": "~/Projects"})

    assert text(app) == "Chess wasn't in the Dock."
    assert text(folder) == "~/Projects wasn't in the Dock."


async def test_changes_to_the_items_at_once_are_all_kept(
    client: Client, mac: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    # As pymacos does: read the whole list, take a moment, write it back. Two calls at once must not
    # write over each other's change.
    items: List[str] = []

    def change(item: str) -> Any:
        def call(*args: Any, **options: Any) -> Any:
            read = list(items)
            time.sleep(0.05)
            items[:] = read + [item]
            return SAFARI if item == "app" else DOWNLOADS if item == "folder" else 0

        return call

    monkeypatch.setattr(macos.dock, "add_spacer", change("spacer"))
    monkeypatch.setattr(macos.dock, "add_app", change("app"))
    monkeypatch.setattr(macos.dock, "add_folder", change("folder"))

    async with anyio.create_task_group() as group:
        group.start_soon(client.call_tool, "add_dock_spacer", {})
        group.start_soon(client.call_tool, "add_dock_spacer", {"small": True})
        group.start_soon(client.call_tool, "add_app_to_dock", {"app": "Safari"})
        group.start_soon(client.call_tool, "add_folder_to_dock", {"folder": "~/Downloads"})

    assert sorted(items) == ["app", "folder", "spacer", "spacer"]
