"""The tools of mcp_server_macos.tools.volume, with macos.volume faked."""

from typing import Any, Dict, Optional

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


@pytest.fixture
def volume(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    """The calls made to the functions of macos.volume that change something."""
    recorder = Recorder()
    for name in ("set", "mute", "unmute"):
        monkeypatch.setattr(macos.volume, name, recorder.function(name))
    return recorder


@pytest.mark.parametrize("level, muted", [(38, False), (0, True), (None, None)])
async def test_get_volume(
    client: Client, monkeypatch: pytest.MonkeyPatch, level: Optional[int], muted: Optional[bool]
) -> None:
    # None: an output device with no volume control, like some HDMI displays.
    monkeypatch.setattr(macos.volume, "get", lambda: level)
    monkeypatch.setattr(macos.volume, "is_muted", lambda: muted)

    result = await client.call_tool("get_volume", {})

    assert not result.is_error
    assert result.structured_content == {"level": level, "muted": muted}


@pytest.mark.parametrize("level", [0, 30, 100])
async def test_set_volume(client: Client, volume: Recorder, level: int) -> None:
    result = await client.call_tool("set_volume", {"level": level})

    assert not result.is_error
    assert text(result) == "Volume set to {}.".format(level)
    assert volume.calls == [("set", (level,), {})]


@pytest.mark.parametrize("arguments", [{}, {"level": -1}, {"level": 101}, {"level": "loud"}, {"level": None}])
async def test_set_volume_refuses_what_is_not_a_level(client: Client, volume: Recorder, arguments: Dict[str, Any]) -> None:
    result = await client.call_tool("set_volume", arguments)

    assert result.is_error
    assert volume.calls == []


@pytest.mark.parametrize("muted, called, said", [(True, "mute", "Output muted."), (False, "unmute", "Output unmuted.")])
async def test_set_muted(client: Client, volume: Recorder, muted: bool, called: str, said: str) -> None:
    result = await client.call_tool("set_muted", {"muted": muted})

    assert not result.is_error
    assert text(result) == said
    assert volume.calls == [(called, (), {})]


async def test_set_muted_needs_to_be_told_which(client: Client, volume: Recorder) -> None:
    result = await client.call_tool("set_muted", {})

    assert result.is_error
    assert volume.calls == []


async def test_volume_reports_what_macos_refused(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    def get() -> int:
        raise macos.CommandError(["osascript"], 1, "execution error")

    monkeypatch.setattr(macos.volume, "get", get)

    result = await client.call_tool("get_volume", {})

    assert result.is_error
    assert "CommandError" in text(result)
