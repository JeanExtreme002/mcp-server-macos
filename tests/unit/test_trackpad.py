"""The tools of mcp_server_macos.tools.trackpad, with macos.trackpad faked: the trackpad isn't changed."""

import contextlib
from typing import Any, Dict, Iterator, List

import macos
import pytest
from mcp import Client

from mcp_server_macos.tools import trackpad
from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


@pytest.fixture
def mac(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    recorder = Recorder()

    @contextlib.contextmanager
    def batch() -> Iterator[None]:
        recorder.calls.append(("batch", (), {}))
        yield

    monkeypatch.setattr(macos.settings, "batch", batch)
    values = {
        "tap_to_click": True,
        "natural_scrolling": True,
        "tracking_speed": 0.5,
        "three_finger_drag": False,
        "secondary_click": "two_fingers",
        "click_pressure": "medium",
        "gestures": {"pinch_to_zoom": True, "mission_control": 3, "launchpad": False},
    }
    for name, value in values.items():
        monkeypatch.setattr(macos.trackpad, name, lambda value=value: value)
    for name in macos.trackpad.__all__:
        if name.startswith("set_"):
            monkeypatch.setattr(macos.trackpad, name, recorder.function(name))
    return recorder


async def test_get_trackpad_settings(client: Client, mac: Recorder) -> None:
    result = await client.call_tool("get_trackpad_settings", {})

    assert result.structured_content == {
        "tap_to_click": True,
        "natural_scrolling": True,
        "tracking_speed": 0.5,
        "three_finger_drag": False,
        "secondary_click": "two_fingers",
        "click_pressure": "medium",
        "gestures": {"pinch_to_zoom": True, "mission_control": 3, "launchpad": False},
    }
    assert mac.calls == []


async def test_set_trackpad_settings(client: Client, mac: Recorder) -> None:
    result = await client.call_tool(
        "set_trackpad_settings",
        {
            "tap_to_click": False,
            "tracking_speed": 0.7,
            "secondary_click": "off",
            "click_pressure": "firm",
            "gestures": {"mission_control": 4, "pinch_to_zoom": False},
        },
    )

    assert not result.is_error, text(result)
    assert mac.calls == [
        ("batch", (), {}),
        ("set_tap_to_click", (False,), {}),
        ("set_tracking_speed", (0.7,), {}),
        ("set_secondary_click", (None,), {}),
        ("set_click_pressure", ("firm",), {}),
        ("set_gesture", ("mission_control", 4), {}),
        ("set_gesture", ("pinch_to_zoom", False), {}),
    ]


async def test_gestures_offered_are_those_of_pymacos() -> None:
    assert set(trackpad._FINGERS) <= set(macos.trackpad.GESTURES)


@pytest.mark.parametrize(
    "arguments, why",
    [
        ({}, "no setting was given"),
        ({"gestures": {"pinch": True}, "tap_to_click": True}, "gestures must be among"),
        ({"gestures": {"rotate": 3}, "tap_to_click": True}, "rotate is on or off"),
        ({"tracking_speed": 1.5}, "set_trackpad_settings"),
        ({"secondary_click": "middle"}, "set_trackpad_settings"),
        ({"gestures": {"mission_control": 5}}, "set_trackpad_settings"),
    ],
)
async def test_set_trackpad_settings_changes_nothing_when_a_setting_is_wrong(
    client: Client, mac: Recorder, arguments: Dict[str, Any], why: str
) -> None:
    result = await client.call_tool("set_trackpad_settings", arguments)

    assert result.is_error
    assert why in text(result)
    assert mac.calls == []


async def test_every_trackpad_gesture_is_described(client: Client) -> None:
    (tool,) = [tool for tool in (await client.list_tools()).tools if tool.name == "set_trackpad_settings"]
    described: List[str] = [
        name for name in macos.trackpad.GESTURES if name in tool.input_schema["properties"]["gestures"]["description"]
    ]

    assert described == list(macos.trackpad.GESTURES)
