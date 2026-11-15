"""The tools of mcp_server_macos.tools.windows, with macos.windows faked: no window is moved or closed."""

import contextlib
from typing import Any, Dict, Iterator, List, Optional, Tuple

import macos
import pytest
from mcp import Client
from mcp.server.mcpserver import Image
from mcp.types import ImageContent

from mcp_server_macos.tools import windows
from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


class FakeWindow:
    """A window of pymacos, whose methods are recorded."""

    def __init__(
        self, recorder: Recorder, app: str, title: str, frame: Tuple[float, float, float, float] = (0, 25, 800, 600)
    ) -> None:
        self.app, self.pid, self.title, self.frame = app, 42, title, frame
        self.fullscreen = False
        for name in ("focus", "move", "resize", "set_frame", "snap", "center", "set_fullscreen", "close"):
            setattr(self, name, self._recorded(recorder, name))
        self.screenshot = recorder.function("screenshot", "/tmp/window.png")
        # As macOS does: minimized, or back, only once the animation is over, a few reads later.
        self._minimize, self._restore = self._recorded(recorder, "minimize"), self._recorded(recorder, "restore")
        self._settling: List[bool] = []
        self._shown_minimized = False

    def minimize(self) -> None:
        self._minimize()
        self._settling = [self._shown_minimized] * 3 + [True]

    def restore(self) -> None:
        self._restore()
        self._settling = [self._shown_minimized] * 3 + [False]

    @property
    def minimized(self) -> bool:
        if self._settling:
            self._shown_minimized = self._settling.pop(0)
        return self._shown_minimized

    @minimized.setter
    def minimized(self, value: bool) -> None:
        self._shown_minimized = value

    def _recorded(self, recorder: Recorder, name: str) -> Any:
        call = recorder.function(name)

        def method(*args: Any, **options: Any) -> None:
            call(self.title, *args, **options)

        return method


@pytest.fixture(autouse=True)
def instant(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fake windows take a few reads to change, as macOS's do: read without pausing in between."""
    monkeypatch.setattr(windows, "_pause", lambda seconds: None)


@pytest.fixture
def mac(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    recorder = Recorder()
    shown = [FakeWindow(recorder, "TextEdit", "Notes"), FakeWindow(recorder, "TextEdit", "Report")]
    recorder.windows = shown  # type: ignore[attr-defined]

    def listed(app: Optional[str] = None, *, title: Optional[str] = None) -> List[FakeWindow]:
        return [w for w in shown if (app in (None, w.app)) and (title is None or title.lower() in w.title.lower())]

    monkeypatch.setattr(macos.windows, "list", listed)
    monkeypatch.setattr(macos.windows, "focused", lambda: shown[1])
    monkeypatch.setattr(macos.windows, "tile", recorder.function("tile"))
    monkeypatch.setattr(macos.windows, "tile_all", recorder.function("tile_all", shown))

    @contextlib.contextmanager
    def batch() -> Iterator[None]:
        recorder.calls.append(("batch", (), {}))
        yield

    monkeypatch.setattr(macos.settings, "batch", batch)
    for name in macos.windows.__all__:
        if name.startswith("set_"):
            monkeypatch.setattr(macos.windows, name, recorder.function(name))
    return recorder


async def test_list_windows(client: Client, mac: Recorder) -> None:
    result = await client.call_tool("list_windows", {"app": "TextEdit", "title": "rep"})

    assert result.structured_content == {
        "result": [
            {
                "app": "TextEdit",
                "pid": 42,
                "title": "Report",
                "x": 0.0,
                "y": 25.0,
                "width": 800.0,
                "height": 600.0,
                "minimized": False,
                "fullscreen": False,
            }
        ]
    }


@pytest.mark.parametrize(
    "arguments, which",
    [
        ({}, "Report"),
        ({"app": "TextEdit"}, "Notes"),
        ({"app": "TextEdit", "title": "REPORT"}, "Report"),
        ({"title": "notes"}, "Notes"),
    ],
)
async def test_a_window_is_told_by_its_app_and_title(
    client: Client, mac: Recorder, arguments: Dict[str, Any], which: str
) -> None:
    # Neither: the window in front. An app: its front window. A title: the first that has it.
    result = await client.call_tool("focus_window", arguments)

    assert not result.is_error, text(result)
    assert mac.calls == [("focus", (which,), {})]


async def test_a_window_that_isnt_there(client: Client, mac: Recorder, monkeypatch: pytest.MonkeyPatch) -> None:
    missing = await client.call_tool("close_window", {"app": "Safari"})
    monkeypatch.setattr(macos.windows, "focused", lambda: None)
    none_in_front = await client.call_tool("close_window", {})

    assert "LookupError: no window of Safari" in text(missing)
    assert "the app in front has no window" in text(none_in_front)
    assert mac.calls == []


@pytest.mark.parametrize(
    "arguments, call",
    [
        ({"x": 10, "y": 30, "width": 640, "height": 480}, ("set_frame", ("Report", 10.0, 30.0, 640.0, 480.0), {})),
        ({"x": 10, "y": 30}, ("move", ("Report", 10.0, 30.0), {})),
        ({"width": 640, "height": 480}, ("resize", ("Report", 640.0, 480.0), {})),
    ],
)
async def test_move_window(client: Client, mac: Recorder, arguments: Dict[str, Any], call: Any) -> None:
    result = await client.call_tool("move_window", arguments)

    assert not result.is_error, text(result)
    assert mac.calls == [call]


@pytest.mark.parametrize(
    "arguments, calls",
    [
        ({"layout": "left_third", "display": 2}, [("snap", ("Report", "left_third"), {"display": 2})]),
        ({"layout": "maximize"}, [("snap", ("Report", "maximize"), {"display": None})]),
        ({"layout": "center"}, [("center", ("Report",), {})]),
    ],
)
async def test_snap_window(client: Client, mac: Recorder, arguments: Dict[str, Any], calls: List[Any]) -> None:
    result = await client.call_tool("snap_window", arguments)

    assert not result.is_error, text(result)
    assert mac.calls == calls


def test_every_layout_of_pymacos_is_offered() -> None:
    assert set(windows.Layout.__args__) == set(macos.windows.LAYOUTS) | {"center"}  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "arguments, calls",
    [
        ({"minimized": True}, [("minimize", ("Report",), {})]),
        (
            {"minimized": False, "fullscreen": True},
            [("restore", ("Report",), {}), ("set_fullscreen", ("Report", True), {})],
        ),
        ({"fullscreen": False}, [("set_fullscreen", ("Report", False), {})]),
    ],
)
async def test_set_window_state(client: Client, mac: Recorder, arguments: Dict[str, Any], calls: List[Any]) -> None:
    result = await client.call_tool("set_window_state", arguments)

    assert not result.is_error, text(result)
    assert mac.calls == calls


@pytest.mark.parametrize("minimized", [True, False])
async def test_the_state_told_is_the_one_the_window_is_in(
    client: Client, mac: Recorder, monkeypatch: pytest.MonkeyPatch, minimized: bool
) -> None:
    # macOS says a window is minimized, or back, only once its animation is over: the tool waits for it.
    mac.windows[1].minimized = not minimized  # type: ignore[attr-defined]

    result = await client.call_tool("set_window_state", {"minimized": minimized})

    assert result.structured_content is not None
    assert result.structured_content["minimized"] is minimized


async def test_a_window_that_doesnt_minimize(client: Client, mac: Recorder, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter(range(0, 100))
    monkeypatch.setattr(windows, "_clock", lambda: next(clock))
    stuck = mac.windows[1]  # type: ignore[attr-defined]
    monkeypatch.setattr(stuck, "minimize", lambda: None)  # asked, and nothing happens

    result = await client.call_tool("set_window_state", {"minimized": True})

    assert result.is_error
    assert "WaitTimeoutError: could not minimize the window of TextEdit within 3 seconds" in text(result)


async def test_close_window(client: Client, mac: Recorder) -> None:
    result = await client.call_tool("close_window", {"app": "TextEdit", "title": "notes"})

    assert text(result) == "Closed 'Notes' of TextEdit."
    assert mac.calls == [("close", ("Notes",), {})]


async def test_take_window_screenshot(client: Client, mac: Recorder, monkeypatch: pytest.MonkeyPatch) -> None:
    taken: List[Any] = []

    def look(take: Any) -> Tuple[Image, int, int]:
        taken.append(take("/tmp/picture.png"))
        return Image(data=b"jpeg", format="jpeg"), 1600, 1200

    monkeypatch.setattr(windows, "look", look)

    result = await client.call_tool("take_window_screenshot", {})

    image, said = result.content
    assert isinstance(image, ImageContent)
    assert getattr(said, "text").startswith(
        "The image is 1600×1200 pixels and shows the screen from (0, 25), 800×600 points"
    )
    assert mac.calls == [("screenshot", ("/tmp/picture.png",), {"shadow": False})]


async def test_a_window_screenshot_with_its_shadow_maps_no_points(
    client: Client, mac: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The shadow pads the picture beyond the frame: its pixels don't map onto it, so no map is given.
    monkeypatch.setattr(windows, "look", lambda take: (Image(data=b"jpeg", format="jpeg"), 1700, 1350))

    result = await client.call_tool("take_window_screenshot", {"shadow": True})

    said = getattr(result.content[1], "text")
    assert "with the window's shadow around it: its pixels don't map to points" in said
    assert "px ×" not in said


async def test_save_window_screenshot(client: Client, mac: Recorder) -> None:
    result = await client.call_tool("save_window_screenshot", {"path": "w.png", "app": "TextEdit"})

    assert result.structured_content == {"path": "/tmp/window.png"}
    assert mac.calls == [("screenshot", ("w.png",), {"shadow": False})]


async def test_tile_windows(client: Client, mac: Recorder) -> None:
    some = await client.call_tool(
        "tile_windows",
        {"windows": [{"app": "TextEdit", "title": "report"}, {"app": "TextEdit"}], "columns": 2, "gap": 8},
    )
    every = await client.call_tool("tile_windows", {"app": "TextEdit"})

    assert not some.is_error and not every.is_error
    shown = mac.windows  # type: ignore[attr-defined]
    assert mac.calls == [
        ("tile", ([shown[1], shown[0]],), {"display": None, "columns": 2, "gap": 8}),
        ("tile_all", ("TextEdit",), {"display": None, "columns": None, "gap": 0}),
    ]


async def test_get_window_settings(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    def unsupported() -> bool:
        raise macos.NotSupportedError("needs macOS 15")

    monkeypatch.setattr(macos.windows, "double_click_title_bar", lambda: None)
    monkeypatch.setattr(macos.windows, "tiling", unsupported)
    monkeypatch.setattr(macos.windows, "click_wallpaper_to_show_desktop", lambda: True)
    monkeypatch.setattr(macos.windows, "animations", lambda: False)
    monkeypatch.setattr(macos.windows, "has_permission", lambda: True)

    result = await client.call_tool("get_window_settings", {})

    assert result.structured_content == {
        "double_click_title_bar": "nothing",
        "tiling": None,
        "click_wallpaper_to_show_desktop": True,
        "animations": False,
        "accessibility_permission": True,
    }


async def test_set_window_settings(client: Client, mac: Recorder) -> None:
    result = await client.call_tool("set_window_settings", {"double_click_title_bar": "nothing", "animations": False})

    assert not result.is_error, text(result)
    assert mac.calls == [
        ("batch", (), {}),
        ("set_double_click_title_bar", (None,), {}),
        ("set_animations", (False,), {}),
    ]


async def test_without_the_permission_it_is_asked_for(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    asked = Recorder()
    monkeypatch.setattr(
        macos.windows, "list", asked.function("list", error=macos.PermissionDeniedError("no Accessibility"))
    )
    monkeypatch.setattr(macos.keyboard, "request_permission", asked.function("request_permission", False))

    result = await client.call_tool("list_windows", {})

    assert asked.names == ["list", "request_permission"]
    assert "System Settings › Privacy & Security › Accessibility" in text(result)


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("move_window", {}),
        ("move_window", {"x": 1}),
        ("move_window", {"width": 100}),
        ("move_window", {"width": 0, "height": 10}),
        ("snap_window", {"layout": "center", "display": 2}),
        ("snap_window", {"layout": "middle"}),
        ("set_window_state", {}),
        # A window in full screen can't be minimized: refused before anything is done.
        ("set_window_state", {"minimized": True, "fullscreen": True}),
        ("tile_windows", {"app": "TextEdit", "windows": [{"app": "TextEdit"}]}),
        ("tile_windows", {"windows": []}),
        ("tile_windows", {"columns": 0}),
        ("set_window_settings", {}),
        ("set_window_settings", {"double_click_title_bar": "close"}),
        ("wait_for_window", {"timeout_seconds": 601}),
    ],
)
async def test_windows_are_not_touched_without_what_they_need(
    client: Client, mac: Recorder, monkeypatch: pytest.MonkeyPatch, tool: str, arguments: Dict[str, Any]
) -> None:
    monkeypatch.setattr(macos.windows, "wait_for", mac.function("wait_for"))

    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert mac.calls == []
