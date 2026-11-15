"""The tools of mcp_server_macos.tools.mouse, with macos.mouse faked: the pointer isn't moved, nothing is clicked."""

import contextlib
import time
from typing import Any, Dict, Iterator, List

import anyio
import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


@pytest.fixture
def mac(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    recorder = Recorder()
    for name in (
        "move",
        "click",
        "drag",
        "scroll",
        "set_tracking_speed",
        "set_scroll_speed",
        "set_double_click_speed",
        "set_acceleration",
    ):
        monkeypatch.setattr(macos.mouse, name, recorder.function(name))

    @contextlib.contextmanager
    def hold(*keys: str) -> Iterator[None]:
        # As pymacos does: the keys are let go even when what was done while holding them failed.
        recorder.calls.append(("hold", keys, {}))
        try:
            yield
        finally:
            recorder.calls.append(("release", keys, {}))

    monkeypatch.setattr(macos.keyboard, "hold", hold)
    return recorder


async def test_get_mouse_settings(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(macos.mouse, "position", lambda: (512.0, 384.5))
    for name, value in (
        ("tracking_speed", 0.5),
        ("scroll_speed", 0.3125),
        ("double_click_speed", 0.5),
        ("acceleration", True),
    ):
        monkeypatch.setattr(macos.mouse, name, lambda value=value: value)

    result = await client.call_tool("get_mouse_settings", {})

    assert result.structured_content == {
        "pointer": {"x": 512.0, "y": 384.5},
        "tracking_speed": 0.5,
        "scroll_speed": 0.3125,
        "double_click_speed_seconds": 0.5,
        "acceleration": True,
    }


@pytest.mark.parametrize(
    "tool, arguments, calls, said",
    [
        (
            "move_pointer",
            {"x": 100, "y": 200},
            [("move", (100.0, 200.0), {"duration": 0.0})],
            "The pointer is at (100, 200).",
        ),
        ("click", {}, [("click", (None, None), {"button": "left", "count": 1})], "Clicked where the pointer is."),
        (
            "click",
            {"x": 300, "y": 400, "button": "right", "count": 2},
            [("click", (300.0, 400.0), {"button": "right", "count": 2})],
            "Clicked at (300, 400).",
        ),
        (
            "click",
            {"x": 1, "y": 2, "holding": ["shift"]},
            [
                ("hold", ("shift",), {}),
                ("click", (1.0, 2.0), {"button": "left", "count": 1}),
                ("release", ("shift",), {}),
            ],
            "Clicked at (1, 2).",
        ),
        (
            "drag",
            {"to_x": 600, "to_y": 50, "from_x": 10, "from_y": 20, "holding": ["option"]},
            [
                ("hold", ("option",), {}),
                ("move", (10.0, 20.0), {}),
                ("drag", (600.0, 50.0), {"button": "left", "duration": 0.3}),
                ("release", ("option",), {}),
            ],
            "Dragged to (600, 50).",
        ),
        ("scroll", {"lines": -5}, [("scroll", (-5,), {"horizontal": False})], "Scrolled -5 lines."),
        (
            "set_mouse_settings",
            {"tracking_speed": 0.7, "acceleration": False},
            [("set_tracking_speed", (0.7,), {}), ("set_acceleration", (False,), {})],
            "Changed: tracking speed, acceleration.",
        ),
    ],
)
async def test_mouse_does_as_asked(
    client: Client, mac: Recorder, tool: str, arguments: Dict[str, Any], calls: List[Any], said: str
) -> None:
    result = await client.call_tool(tool, arguments)

    assert not result.is_error, text(result)
    assert text(result) == said
    assert mac.calls == calls


async def test_keys_held_are_released_when_the_click_fails(
    client: Client, mac: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(macos.mouse, "click", mac.function("click", error=macos.MacOSError("the click failed")))

    result = await client.call_tool("click", {"x": 1, "y": 2, "holding": ["cmd"]})

    assert result.is_error
    assert mac.names == ["hold", "click", "release"]


async def test_a_drag_starts_where_it_was_told_while_the_pointer_is_moved(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A drag moves the pointer, then drags from where it is: a move in between would drag from elsewhere.
    pointer = [(0.0, 0.0)]
    started: List[Any] = []

    def move(x: float, y: float, **options: Any) -> None:
        time.sleep(0.02)
        pointer[0] = (x, y)

    def drag(x: float, y: float, **options: Any) -> None:
        time.sleep(0.02)
        started.append(pointer[0])

    monkeypatch.setattr(macos.mouse, "move", move)
    monkeypatch.setattr(macos.mouse, "drag", drag)

    async with anyio.create_task_group() as group:
        group.start_soon(client.call_tool, "drag", {"to_x": 600, "to_y": 50, "from_x": 10, "from_y": 20})
        for _ in range(3):
            group.start_soon(client.call_tool, "move_pointer", {"x": 500, "y": 500})

    assert started == [(10.0, 20.0)]


async def test_click_text(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    found = macos.screen.TextMatch(text="Submit", x=100, y=200, width=60, height=20)
    monkeypatch.setattr(macos.mouse, "click_text", recorder.function("click_text", found))

    result = await client.call_tool("click_text", {"text": "submit", "timeout_seconds": 10})

    assert result.structured_content == {"text": "Submit", "x": 130.0, "y": 210.0}
    assert recorder.calls == [
        ("click_text", ("submit",), {"timeout": 10.0, "button": "left", "count": 1, "languages": None})
    ]


async def test_click_text_without_the_permissions_asks_for_both(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = Recorder()
    monkeypatch.setattr(
        macos.mouse,
        "click_text",
        Recorder().function("click_text", error=macos.PermissionDeniedError("Screen Recording is missing")),
    )
    monkeypatch.setattr(macos.screen, "request_permission", asked.function("screen", False))
    monkeypatch.setattr(macos.keyboard, "request_permission", asked.function("accessibility", True))

    result = await client.call_tool("click_text", {"text": "Submit"})

    assert result.is_error
    assert asked.names == ["screen", "accessibility"]
    assert "Screen & System Audio Recording, and › Accessibility" in text(result)


@pytest.mark.parametrize("clicked", [True, False])
async def test_wait_for_click(client: Client, monkeypatch: pytest.MonkeyPatch, clicked: bool) -> None:
    closed: List[bool] = []

    class Clicks:
        def __iter__(self) -> Iterator[Any]:
            if clicked:
                yield macos.mouse.Click(x=10.0, y=20.0, button="right", count=1)

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(macos.mouse, "watch", lambda timeout: Clicks())

    result = await client.call_tool("wait_for_click", {})

    assert result.structured_content == {
        "click": {"x": 10.0, "y": 20.0, "button": "right", "count": 1} if clicked else None
    }
    assert closed == [True]


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("click", {"x": 10}),
        ("click", {"y": 10}),
        ("click", {"button": "back"}),
        ("click", {"count": 4}),
        ("drag", {"to_x": 1}),
        ("drag", {"to_x": 1, "to_y": 2, "from_x": 3}),
        ("scroll", {}),
        # Held keys are modifiers: a shortcut held down would do what it does, closing a window here.
        ("scroll", {"lines": 0, "holding": ["cmd+w"]}),
        ("click", {"holding": ["w"]}),
        ("move_pointer", {"x": 1, "y": 2, "duration_seconds": 11}),
        ("set_mouse_settings", {}),
        ("set_mouse_settings", {"tracking_speed": 2}),
        ("click_text", {"text": ""}),
    ],
)
async def test_mouse_is_not_touched_without_what_it_needs(
    client: Client, mac: Recorder, tool: str, arguments: Dict[str, Any]
) -> None:
    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert mac.calls == []
