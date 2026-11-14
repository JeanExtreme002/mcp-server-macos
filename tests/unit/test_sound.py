"""The tools of mcp_server_macos.tools.sound, with macos.sound faked."""

from typing import Any, Dict, List

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio

NAMES = ["Basso", "Funk", "Glass", "Ping"]


@pytest.fixture
def sound(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    """A Mac's sound settings, and the calls made to the functions of macos.sound that play or change something."""
    recorder = Recorder()
    monkeypatch.setattr(macos.sound, "names", lambda: list(NAMES))
    monkeypatch.setattr(macos.sound, "alert_sound", lambda: "Funk")
    monkeypatch.setattr(macos.sound, "alert_volume", lambda: 0.754)
    monkeypatch.setattr(macos.sound, "ui_sounds", lambda: True)
    for name in ("play", "beep", "set_alert_sound", "set_alert_volume", "set_ui_sounds"):
        monkeypatch.setattr(macos.sound, name, recorder.function(name))
    return recorder


async def test_get_sound_settings(client: Client, sound: Recorder) -> None:
    result = await client.call_tool("get_sound_settings", {})

    assert not result.is_error
    assert result.structured_content == {
        "alert_sound": "Funk",
        "alert_volume": 75,  # pymacos says 0.0 to 1.0
        "ui_sounds": True,
        "available_alert_sounds": NAMES,
    }
    assert sound.calls == []


async def test_get_sound_settings_with_the_alert_sound_of_macos(
    client: Client, sound: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(macos.sound, "alert_sound", lambda: None)

    result = await client.call_tool("get_sound_settings", {})

    assert result.structured_content is not None
    assert result.structured_content["alert_sound"] is None


@pytest.mark.parametrize(
    "arguments, call, said",
    [
        ({"sound": "Glass"}, ("play", ("Glass",), {"volume": 1.0, "wait": True}), "Played Glass."),
        (
            {"sound": "/Users/me/done.mp3", "volume": 50},
            ("play", ("/Users/me/done.mp3",), {"volume": 0.5, "wait": True}),
            "Played /Users/me/done.mp3.",
        ),
        (
            {"sound": "Ping", "volume": 0, "wait": False},
            ("play", ("Ping",), {"volume": 0.0, "wait": False}),
            "Playing Ping.",
        ),
    ],
)
async def test_play_sound(client: Client, sound: Recorder, arguments: Dict[str, Any], call: Any, said: str) -> None:
    result = await client.call_tool("play_sound", arguments)

    assert not result.is_error
    assert text(result) == said
    assert sound.calls == [call]


@pytest.mark.parametrize(
    "arguments", [{}, {"sound": ""}, {"sound": "Glass", "volume": 101}, {"sound": "Glass", "volume": -1}]
)
async def test_play_sound_refuses_what_it_does_not_take(client: Client, sound: Recorder, arguments: Dict[str, Any]) -> None:
    result = await client.call_tool("play_sound", arguments)

    assert result.is_error
    assert sound.calls == []


async def test_play_sound_that_does_not_exist(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    error = ValueError("no alert sound is named 'Nope'")
    monkeypatch.setattr(macos.sound, "play", Recorder().function("play", error=error))

    result = await client.call_tool("play_sound", {"sound": "Nope"})

    assert result.is_error
    assert "ValueError: no alert sound is named 'Nope'" in text(result)


async def test_play_alert_beep(client: Client, sound: Recorder) -> None:
    result = await client.call_tool("play_alert_beep", {})

    assert not result.is_error
    assert text(result) == "Beeped."
    assert sound.calls == [("beep", (), {})]


@pytest.mark.parametrize(
    "arguments, calls, said",
    [
        ({"alert_sound": "Glass"}, [("set_alert_sound", ("Glass",), {})], "alert sound"),
        ({"alert_sound": "glass"}, [("set_alert_sound", ("glass",), {})], "alert sound"),
        ({"alert_sound": "default"}, [("set_alert_sound", (None,), {})], "alert sound"),
        ({"alert_volume": 30}, [("set_alert_volume", (0.3,), {})], "alert volume"),
        ({"alert_volume": 0}, [("set_alert_volume", (0.0,), {})], "alert volume"),
        ({"ui_sounds": False}, [("set_ui_sounds", (False,), {})], "interface sounds"),
        (
            {"ui_sounds": True, "alert_volume": 100, "alert_sound": "Ping"},
            [("set_alert_sound", ("Ping",), {}), ("set_alert_volume", (1.0,), {}), ("set_ui_sounds", (True,), {})],
            "alert sound, alert volume, interface sounds",
        ),
    ],
)
async def test_set_sound_settings(
    client: Client, sound: Recorder, arguments: Dict[str, Any], calls: List[Any], said: str
) -> None:
    result = await client.call_tool("set_sound_settings", arguments)

    assert not result.is_error, text(result)
    assert text(result) == "Changed: {}.".format(said)
    assert sound.calls == calls


@pytest.mark.parametrize(
    "arguments, why",
    [
        ({}, "no setting was given"),
        ({"alert_sound": "Nope", "ui_sounds": False}, "alert_sound must be 'default' or one of Basso, Funk, Glass, Ping"),
        ({"alert_volume": 101, "ui_sounds": False}, "set_sound_settings"),
        ({"ui_sounds": "sometimes"}, "set_sound_settings"),
    ],
)
async def test_set_sound_settings_changes_nothing_when_a_setting_is_wrong(
    client: Client, sound: Recorder, arguments: Dict[str, Any], why: str
) -> None:
    result = await client.call_tool("set_sound_settings", arguments)

    assert result.is_error
    assert why in text(result)
    assert sound.calls == []
