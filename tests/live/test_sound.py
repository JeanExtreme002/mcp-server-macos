"""The sound tools against this Mac: a sound is played at no volume, and no setting is changed."""

import pytest
from mcp import Client

from tests.helpers import text
from tests.live.helpers import call

pytestmark = pytest.mark.anyio


async def test_sound_settings_are_read_and_none_is_changed(client: Client) -> None:
    settings = await call(client, "get_sound_settings")

    assert 0 <= settings["alert_volume"] <= 100
    assert isinstance(settings["ui_sounds"], bool)
    assert "Glass" in settings["available_alert_sounds"]
    assert settings["alert_sound"] is None or settings["alert_sound"] in settings["available_alert_sounds"]

    # Refused before anything is changed.
    result = await client.call_tool("set_sound_settings", {"alert_sound": "no such sound", "ui_sounds": False})
    assert result.is_error
    assert await call(client, "get_sound_settings") == settings


async def test_sound_is_played_without_being_heard(client: Client) -> None:
    result = await client.call_tool("play_sound", {"sound": "Tink", "volume": 0})

    assert not result.is_error, text(result)
    assert text(result) == "Played Tink."


async def test_sound_that_does_not_exist_is_not_played(client: Client) -> None:
    result = await client.call_tool("play_sound", {"sound": "no such sound"})

    assert result.is_error
