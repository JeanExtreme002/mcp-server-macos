"""The tools of mcp_server_macos.tools.music, with macos.music faked: no player is touched."""

from typing import Any, Dict

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio

TRACK = macos.music.Track(
    title="Imagine", artist="John Lennon", album="Imagine", duration=183.5, position=42.0, playing=True, app="Music"
)


@pytest.fixture
def music(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    recorder = Recorder()
    monkeypatch.setattr(macos.music, "now_playing", recorder.function("now_playing", TRACK))
    monkeypatch.setattr(macos.music, "volume", recorder.function("volume", 65))
    for name in ("play", "pause", "play_pause", "next", "previous", "set_volume", "seek"):
        monkeypatch.setattr(macos.music, name, recorder.function(name))
    return recorder


async def test_get_now_playing(client: Client, music: Recorder) -> None:
    result = await client.call_tool("get_now_playing", {})

    assert not result.is_error
    assert result.structured_content == {
        "track": {
            "title": "Imagine",
            "artist": "John Lennon",
            "album": "Imagine",
            "duration_seconds": 183.5,
            "position_seconds": 42.0,
            "playing": True,
            "app": "Music",
            "volume": 65,
        }
    }
    # The volume of the player the track is on, whichever was asked for.
    assert music.calls == [("now_playing", (None,), {}), ("volume", ("Music",), {})]


async def test_get_now_playing_when_no_player_runs(client: Client, music: Recorder, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(macos.music, "now_playing", music.function("now_playing", None))

    result = await client.call_tool("get_now_playing", {"app": "Spotify"})

    assert not result.is_error
    assert result.structured_content == {"track": None}
    assert music.calls == [("now_playing", ("Spotify",), {})]


async def test_get_now_playing_of_a_player_that_quits_in_between(
    client: Client, music: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(macos.music, "volume", music.function("volume", error=macos.MacOSError("Music isn't running")))

    result = await client.call_tool("get_now_playing", {})

    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["track"]["volume"] is None


@pytest.mark.parametrize("action", ["play", "pause", "play_pause", "next", "previous"])
@pytest.mark.parametrize("app", [None, "Spotify"])
async def test_control_music(client: Client, music: Recorder, action: str, app: Any) -> None:
    arguments = {"action": action} if app is None else {"action": action, "app": app}

    result = await client.call_tool("control_music", arguments)

    assert not result.is_error
    assert text(result) == "Done: {}.".format(action.replace("_", "/"))
    assert music.calls == [(action, (app,), {})]


async def test_set_music_volume_and_seek(client: Client, music: Recorder) -> None:
    volume = await client.call_tool("set_music_volume", {"level": 30, "app": "Music"})
    seek = await client.call_tool("seek_music", {"seconds": 61.5})

    assert text(volume) == "Player volume set to 30."
    assert text(seek) == "Jumped to 61.5 seconds."
    assert music.calls == [("set_volume", (30, "Music"), {}), ("seek", (61.5, None), {})]


async def test_player_that_is_not_running(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(macos.music, "pause", Recorder().function("pause", error=macos.MacOSError("Spotify isn't running")))

    result = await client.call_tool("control_music", {"action": "pause", "app": "Spotify"})

    assert result.is_error
    assert "MacOSError: Spotify isn't running" in text(result)


async def test_player_that_may_not_be_controlled_says_what_to_allow(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    error = macos.PermissionDeniedError("not allowed to control Music")
    monkeypatch.setattr(macos.music, "next", Recorder().function("next", error=error))

    result = await client.call_tool("control_music", {"action": "next"})

    assert result.is_error
    assert "System Settings › Privacy & Security › Automation" in text(result)


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("control_music", {}),
        ("control_music", {"action": "stop"}),
        ("control_music", {"action": "play", "app": "iTunes"}),
        ("set_music_volume", {"level": 101}),
        ("set_music_volume", {"level": -1}),
        ("seek_music", {"seconds": -5}),
        ("get_now_playing", {"app": "Tidal"}),
    ],
)
async def test_player_is_not_touched_without_knowing_how(
    client: Client, music: Recorder, tool: str, arguments: Dict[str, Any]
) -> None:
    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert music.calls == []
