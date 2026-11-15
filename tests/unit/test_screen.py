"""The tools of mcp_server_macos.tools.screen, with macos.screen faked: nothing is captured, no setting changed."""

import contextlib
import datetime
import pathlib
from typing import Any, Dict, Iterator, List

import macos
import pytest
from mcp import Client
from mcp.types import ImageContent, TextContent

from mcp_server_macos.tools import screen
from tests.helpers import Recorder, png, text

pytestmark = pytest.mark.anyio

BUILT_IN = macos.screen.Display(
    id=1,
    name="Built-in Retina Display",
    width=1512,
    height=982,
    x=0,
    y=0,
    pixel_width=3024,
    pixel_height=1964,
    scale=2.0,
    refresh_rate=120.0,
    is_main=True,
    is_builtin=True,
)
EXTERNAL = macos.screen.Display(
    id=7,
    name="LG",
    width=2560,
    height=1440,
    x=1512,
    y=0,
    pixel_width=2560,
    pixel_height=1440,
    scale=1.0,
    refresh_rate=None,
    is_main=False,
    is_builtin=False,
)


def unsupported(*args: Any, **options: Any) -> Any:
    raise macos.NotSupportedError("not on this Mac")


def said(result: Any) -> str:
    """What a screenshot's result says of the image, after it."""
    block = result.content[1]
    assert isinstance(block, TextContent)
    return block.text


@pytest.fixture
def mac(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    recorder = Recorder()
    monkeypatch.setattr(macos.screen, "displays", lambda: [BUILT_IN, EXTERNAL])

    @contextlib.contextmanager
    def batch() -> Iterator[None]:
        recorder.calls.append(("batch", (), {}))
        yield

    monkeypatch.setattr(macos.settings, "batch", batch)
    for name in macos.screen.__all__:
        if name.startswith(("set_", "mirror", "stop_", "start_")) or name in ("lock", "find_text", "wait_for_text"):
            monkeypatch.setattr(macos.screen, name, recorder.function(name, [] if name == "find_text" else None))
    return recorder


@pytest.fixture
def capture(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    """screencapture, and the image functions that scale its picture, without macOS: a PNG of the size asked."""
    recorder = Recorder()
    monkeypatch.setattr(macos.screen, "displays", lambda: [BUILT_IN, EXTERNAL])
    sizes: Dict[str, Any] = {}

    def screenshot(path: Any, **options: Any) -> pathlib.Path:
        recorder.calls.append(("screenshot", (), options))
        region = options.get("region")
        sizes[str(path)] = (region[2] * 2, region[3] * 2) if region else (3024, 1964)
        pathlib.Path(path).write_bytes(png())
        return pathlib.Path(path)

    def info(path: Any) -> Any:
        width, height = sizes[str(path)]
        return macos.image.ImageInfo(
            width=width, height=height, format="png", has_alpha=False, orientation=1, dpi=144.0
        )

    def scaled(name: str) -> Any:
        def call(source: Any, output: Any, **options: Any) -> pathlib.Path:
            recorder.calls.append((name, (), options))
            width, height = sizes[str(source)]
            if name == "resize":
                # As pymacos does: the picture fits within the bounds, its longest side rounded at that scale.
                scale = min(options["width"] / width, options["height"] / height, 1.0)
                longest = max(1, round(max(width, height) * scale))
                ratio = longest / max(width, height)
                width, height = (longest, round(height * ratio)) if width >= height else (round(width * ratio), longest)
            sizes[str(output)] = (width, height)
            pathlib.Path(output).write_bytes(b"jpeg of " + pathlib.Path(source).name.encode())
            return pathlib.Path(output)

        return call

    monkeypatch.setattr(macos.screen, "screenshot", screenshot)
    monkeypatch.setattr(macos.image, "info", info)
    monkeypatch.setattr(macos.image, "resize", scaled("resize"))
    monkeypatch.setattr(macos.image, "convert", scaled("convert"))
    return recorder


async def test_a_whole_screenshot_is_scaled_down_and_says_how_to_click_it(client: Client, capture: Recorder) -> None:
    result = await client.call_tool("take_screenshot", {})

    assert not result.is_error
    image, said = result.content
    assert isinstance(image, ImageContent) and image.mime_type == "image/jpeg"
    assert isinstance(said, TextContent)
    # A Retina display's 3024 pixels are more than the model takes: scaled to 1568, its points told.
    assert capture.calls == [
        ("screenshot", (), {"cursor": False, "display": 1}),
        ("resize", (), {"width": 1568, "height": 1018}),
    ]
    # The size of the picture sent: resize's own rounding makes it 1567 wide, not the 1568 asked for.
    assert said.text.startswith("The image is 1567×1018 pixels and shows the screen from (0, 0), 1512×982 points")
    assert "(0 + px × 0.9649, 0 + py × 0.9646)" in said.text


async def test_a_screenshot_of_a_region_or_of_another_display(client: Client, capture: Recorder) -> None:
    region = await client.call_tool("take_screenshot", {"region": {"x": 100, "y": 50, "width": 400, "height": 200}})
    other = await client.call_tool("take_screenshot", {"display": 2, "cursor": True})

    assert capture.calls[:2] == [
        ("screenshot", (), {"cursor": False, "region": (100, 50, 400, 200)}),
        ("convert", (), {}),  # small enough already
    ]
    assert "800×400 pixels and shows the screen from (100, 50), 400×200 points" in said(region)
    assert capture.calls[2] == ("screenshot", (), {"cursor": True, "display": 2})
    assert "from (1512, 0), 2560×1440 points" in said(other)


async def test_a_screenshot_without_the_permission_asks_for_it(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    asked = Recorder()
    monkeypatch.setattr(macos.screen, "displays", lambda: [BUILT_IN])
    monkeypatch.setattr(
        macos.screen,
        "screenshot",
        asked.function("screenshot", error=macos.PermissionDeniedError("no Screen Recording")),
    )
    monkeypatch.setattr(macos.screen, "request_permission", asked.function("request_permission", False))

    result = await client.call_tool("take_screenshot", {})

    assert result.is_error
    assert asked.names == ["screenshot", "request_permission"]
    assert "Screen & System Audio Recording" in text(result)


@pytest.mark.parametrize(
    "tool, arguments, call",
    [
        ("save_screenshot", {"path": "a.png"}, ("screenshot", ("a.png",), {"cursor": False, "display": 1})),
        (
            "save_screenshot",
            {"path": "a.jpg", "region": {"x": 0, "y": 0, "width": 10, "height": 10}, "display": 2},
            ("screenshot", ("a.jpg",), {"cursor": False, "region": (0, 0, 10, 10)}),
        ),
        (
            "record_screen",
            {"path": "a.mov", "seconds": 5, "audio": True},
            ("record", ("a.mov", 5.0), {"audio": True, "clicks": False, "display": 1}),
        ),
    ],
)
async def test_screen_files(
    client: Client, monkeypatch: pytest.MonkeyPatch, tool: str, arguments: Any, call: Any
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.screen, "displays", lambda: [BUILT_IN, EXTERNAL])
    # A recording with sound checks the microphone first: here, without macOS's.
    monkeypatch.setattr(macos.audio, "has_permission", lambda: True)
    monkeypatch.setattr(macos.screen, call[0], recorder.function(call[0], pathlib.Path(call[1][0])))

    result = await client.call_tool(tool, arguments)

    assert result.structured_content == {"path": call[1][0]}
    assert recorder.calls == [call]


async def test_a_recording_with_sound_asks_for_the_microphone(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    # Screen Recording is the tool's, the microphone only with sound: when that's the one missing, it's
    # the one asked for and told of, and nothing is recorded.
    asked = Recorder()
    monkeypatch.setattr(macos.screen, "displays", lambda: [BUILT_IN])
    monkeypatch.setattr(macos.screen, "record", asked.function("record"))
    monkeypatch.setattr(macos.screen, "request_permission", asked.function("screen", True))
    monkeypatch.setattr(macos.audio, "has_permission", lambda: False)
    monkeypatch.setattr(macos.audio, "request_permission", asked.function("microphone", False))

    result = await client.call_tool("record_screen", {"path": "a.mov", "seconds": 3, "audio": True})

    assert result.is_error
    assert asked.names == ["microphone"]
    assert "System Settings › Privacy & Security › Microphone" in text(result)
    assert "Screen & System Audio Recording" not in text(result)


async def test_find_text_on_screen(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.screen, "displays", lambda: [BUILT_IN])
    found = [macos.screen.TextMatch(text="Submit", x=100, y=200, width=60, height=21)]
    monkeypatch.setattr(macos.screen, "find_text", recorder.function("find_text", found))

    result = await client.call_tool("find_text_on_screen", {"text": "submit", "languages": ["pt-BR"]})

    assert result.structured_content == {
        "result": [
            {"text": "Submit", "x": 100, "y": 200, "width": 60, "height": 21, "center_x": 130.0, "center_y": 210.5}
        ]
    }
    assert recorder.calls == [("find_text", ("submit",), {"languages": ["pt-BR"], "display": 1})]


async def test_wait_for_text_on_screen_that_never_shows(client: Client, mac: Recorder) -> None:
    result = await client.call_tool("wait_for_text_on_screen", {"text": "Done", "timeout_seconds": 2})

    assert result.structured_content == {"found": None}
    assert mac.calls == [("wait_for_text", ("Done",), {"timeout": 2.0, "languages": None, "display": 1})]


async def test_get_displays(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(macos.screen, "displays", lambda: [BUILT_IN, EXTERNAL])
    monkeypatch.setattr(macos.screen, "brightness", lambda display: 0.426 if display is BUILT_IN else unsupported())
    monkeypatch.setattr(
        macos.screen, "wallpaper", lambda display: pathlib.Path("/w.jpg") if display is BUILT_IN else None
    )
    monkeypatch.setattr(macos.screen, "is_asleep", lambda display: display is EXTERNAL)
    monkeypatch.setattr(macos.screen, "mirrored", lambda: False)

    result = await client.call_tool("get_displays", {})

    assert result.structured_content is not None
    built_in, external = result.structured_content["displays"]
    assert (built_in["number"], built_in["brightness"], built_in["wallpaper"], built_in["asleep"]) == (
        1,
        43,
        "/w.jpg",
        False,
    )
    # An external display macOS can't dim, without a picture file, nor a refresh rate it tells.
    assert (external["number"], external["brightness"], external["wallpaper"], external["asleep"]) == (
        2,
        None,
        None,
        True,
    )
    assert external["refresh_rate"] is None
    assert result.structured_content["mirrored"] is False


async def test_get_display_modes(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    sharp = macos.screen.DisplayMode(width=1512, height=982, pixel_width=3024, pixel_height=1964, refresh_rate=120.0)
    full = macos.screen.DisplayMode(width=3024, height=1964, pixel_width=3024, pixel_height=1964, refresh_rate=60.0)
    monkeypatch.setattr(macos.screen, "displays", lambda: [BUILT_IN, EXTERNAL])
    monkeypatch.setattr(macos.screen, "display_mode", lambda display: sharp if display is EXTERNAL else None)
    monkeypatch.setattr(macos.screen, "display_modes", lambda display: [full, sharp] if display is EXTERNAL else [])

    result = await client.call_tool("get_display_modes", {"display": 2})

    assert result.structured_content is not None
    assert result.structured_content["current"]["hidpi"] is True
    assert [mode["hidpi"] for mode in result.structured_content["available"]] == [False, True]


@pytest.mark.parametrize(
    "tool, arguments, call",
    [
        (
            "set_display_brightness",
            {"brightness": 50, "display": 2},
            ("set_brightness", (0.5,), {"display_id": EXTERNAL}),
        ),
        ("set_display_brightness", {"brightness": 0}, ("set_brightness", (0.0,), {"display_id": BUILT_IN})),
        (
            "set_display_mode",
            {"width": 1728, "height": 1117},
            ("set_display_mode", (1728, 1117), {"refresh_rate": None, "hidpi": None, "display": BUILT_IN}),
        ),
        ("set_main_display", {"display": 2}, ("set_main_display", (EXTERNAL,), {})),
        ("mirror_display", {"display": 2}, ("mirror", (EXTERNAL, None), {})),
        ("mirror_display", {"display": 1, "of": 2}, ("mirror", (BUILT_IN, EXTERNAL), {})),
        ("stop_mirroring", {}, ("stop_mirroring", (), {})),
        ("set_wallpaper", {"path": "/w.jpg"}, ("set_wallpaper", ("/w.jpg",), {"display_id": None})),
        ("set_wallpaper", {"path": "/w.jpg", "display": 2}, ("set_wallpaper", ("/w.jpg",), {"display_id": EXTERNAL})),
        ("start_screensaver", {}, ("start_screensaver", (), {})),
        ("lock_screen", {}, ("lock", (), {})),
    ],
)
async def test_displays_are_told_by_their_number(
    client: Client, mac: Recorder, monkeypatch: pytest.MonkeyPatch, tool: str, arguments: Dict[str, Any], call: Any
) -> None:
    mode = macos.screen.DisplayMode(width=1728, height=1117, pixel_width=3456, pixel_height=2234, refresh_rate=120.0)
    monkeypatch.setattr(macos.screen, "set_display_mode", mac.function("set_display_mode", mode))

    result = await client.call_tool(tool, arguments)

    assert not result.is_error, text(result)
    assert mac.calls == [call]


@pytest.mark.parametrize(
    "schedule, shown",
    [
        (None, "never"),
        ("sunset", "sunset"),
        ((datetime.time(22, 0), datetime.time(7, 30)), {"start": "22:00", "end": "07:30"}),
    ],
)
async def test_get_display_settings(client: Client, monkeypatch: pytest.MonkeyPatch, schedule: Any, shown: Any) -> None:
    for name, value in (
        ("night_shift", True),
        ("night_shift_schedule", schedule),
        ("night_shift_strength", 0.5),
        ("screensaver_delay", None),
        ("is_locked", False),
        ("has_permission", True),
    ):
        monkeypatch.setattr(macos.screen, name, lambda value=value: value)
    monkeypatch.setattr(macos.screen, "true_tone", unsupported)

    result = await client.call_tool("get_display_settings", {})

    assert result.structured_content == {
        "night_shift": True,
        "night_shift_schedule": shown,
        "night_shift_strength": 0.5,
        "true_tone": None,
        "screensaver_delay_minutes": None,
        "locked": False,
        "screen_recording_permission": True,
    }


async def test_a_mac_without_night_shift(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("night_shift", "night_shift_schedule", "night_shift_strength", "true_tone"):
        monkeypatch.setattr(macos.screen, name, unsupported)
    for name, value in (("screensaver_delay", 5.0), ("is_locked", False), ("has_permission", False)):
        monkeypatch.setattr(macos.screen, name, lambda value=value: value)

    result = await client.call_tool("get_display_settings", {})

    assert result.structured_content is not None
    assert result.structured_content["night_shift_schedule"] is None  # not "never": there's none to schedule


@pytest.mark.parametrize(
    "arguments, calls",
    [
        ({"night_shift_schedule": "never"}, [("set_night_shift_schedule", (None,), {})]),
        (
            {"night_shift_schedule": {"start": "22:00", "end": "07:00"}, "night_shift": True},
            [("set_night_shift_schedule", (("22:00", "07:00"),), {}), ("set_night_shift", (True,), {})],
        ),
        ({"screensaver_delay_minutes": 0}, [("set_screensaver_delay", (None,), {})]),
        (
            {"screensaver_delay_minutes": 2.5, "true_tone": False},
            [("set_true_tone", (False,), {}), ("set_screensaver_delay", (2.5,), {})],
        ),
    ],
)
async def test_set_display_settings(client: Client, mac: Recorder, arguments: Dict[str, Any], calls: List[Any]) -> None:
    result = await client.call_tool("set_display_settings", arguments)

    assert not result.is_error, text(result)
    assert mac.calls == calls


async def test_set_screenshot_settings(client: Client, mac: Recorder) -> None:
    result = await client.call_tool(
        "set_screenshot_settings", {"name": "", "format": "jpg", "folder": "~/Pictures", "target": "clipboard"}
    )

    assert not result.is_error, text(result)
    # The folder first, as it's the one that can be refused: '' names them as macOS does.
    assert mac.calls == [
        ("batch", (), {}),
        ("set_screenshot_folder", ("~/Pictures",), {}),
        ("set_screenshot_format", ("jpg",), {}),
        ("set_screenshot_name", (None,), {}),
        ("set_screenshot_target", ("clipboard",), {}),
    ]


async def test_a_missing_screenshot_folder_changes_no_other_setting(
    client: Client, mac: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        macos.screen,
        "set_screenshot_folder",
        mac.function("set_screenshot_folder", error=FileNotFoundError("no folder")),
    )

    result = await client.call_tool("set_screenshot_settings", {"format": "jpg", "folder": "~/Nowhere"})

    assert result.is_error
    assert mac.names == ["batch", "set_screenshot_folder"]


async def test_get_screenshot_settings(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in (
        ("screenshot_folder", pathlib.Path("/Users/me/Desktop")),
        ("screenshot_format", "png"),
        ("screenshot_shadow", True),
        ("screenshot_thumbnail", False),
        ("screenshot_name", None),
        ("screenshot_target", "file"),
    ):
        monkeypatch.setattr(macos.screen, name, lambda value=value: value)

    result = await client.call_tool("get_screenshot_settings", {})

    assert result.structured_content == {
        "folder": "/Users/me/Desktop",
        "format": "png",
        "shadow": True,
        "thumbnail": False,
        "name": None,
        "target": "file",
    }


async def test_get_screen_color(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(macos.screen, "color_at", lambda x, y: "#00ff00" if (x, y) == (10.5, 20.0) else "#000000")

    assert (await client.call_tool("get_screen_color", {"x": 10.5, "y": 20})).structured_content == {"color": "#00ff00"}


def test_screenshots_sent_are_no_larger_than_the_model_reads() -> None:
    assert screen._LARGEST_SIDE == 1568


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("take_screenshot", {"display": 3}),
        ("take_screenshot", {"display": 0}),
        ("take_screenshot", {"region": {"x": 0, "y": 0, "width": 0, "height": 10}}),
        ("set_display_brightness", {"brightness": 101}),
        ("set_display_brightness", {"brightness": 50, "display": 3}),
        ("set_main_display", {"display": 3}),
        ("mirror_display", {"display": 2, "of": 5}),
        ("set_wallpaper", {"path": "/w.jpg", "display": 3}),
        ("set_display_settings", {}),
        ("set_display_settings", {"night_shift_schedule": "always"}),
        ("set_display_settings", {"night_shift_schedule": {"start": "10pm", "end": "7am"}}),
        ("set_display_settings", {"night_shift_strength": 2}),
        ("set_screenshot_settings", {}),
        ("set_screenshot_settings", {"format": "webp"}),
        ("record_screen", {"path": "a.mov", "seconds": 0}),
        ("find_text_on_screen", {"text": ""}),
        # A display that isn't connected is refused before anything is asked of macOS.
        ("save_screenshot", {"path": "a.png", "display": 3}),
        ("record_screen", {"path": "a.mov", "seconds": 1, "display": 3, "audio": True}),
        ("find_text_on_screen", {"text": "Submit", "display": 3}),
        ("wait_for_text_on_screen", {"text": "Submit", "display": 3}),
        # As pymacos refuses it, before any other setting is written: a name with / or :, or of spaces.
        ("set_screenshot_settings", {"format": "jpg", "name": "bad/name"}),
        ("set_screenshot_settings", {"format": "jpg", "name": "a:b"}),
        ("set_screenshot_settings", {"format": "jpg", "name": "   "}),
    ],
)
async def test_screen_is_not_touched_without_what_it_needs(
    client: Client,
    mac: Recorder,
    capture: Recorder,
    monkeypatch: pytest.MonkeyPatch,
    tool: str,
    arguments: Dict[str, Any],
) -> None:
    monkeypatch.setattr(macos.screen, "record", mac.function("record"))
    monkeypatch.setattr(macos.screen, "screenshot", mac.function("screenshot"))
    monkeypatch.setattr(macos.screen, "request_permission", mac.function("request_permission"))
    monkeypatch.setattr(macos.audio, "has_permission", mac.function("has_permission"))
    monkeypatch.setattr(macos.audio, "request_permission", mac.function("request_permission"))

    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert mac.calls == [] and capture.calls == []
