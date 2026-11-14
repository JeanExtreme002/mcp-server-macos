"""The speech tools against this Mac: speech is saved to a file, and nothing is said out loud."""

from pathlib import Path

import pytest
from mcp import Client

from tests.helpers import text
from tests.live.helpers import call

pytestmark = pytest.mark.anyio


async def test_list_voices(client: Client) -> None:
    voices = await call(client, "list_voices")

    assert voices, "a Mac has voices"
    assert all(voice["name"] and voice["locale"] for voice in voices)

    english = await call(client, "list_voices", {"locale": "en"})
    assert english
    assert all(voice["locale"].startswith("en") for voice in english)
    assert len(english) <= len(voices)


async def test_speech_is_saved_to_a_file(client: Client, tmp_path: Path) -> None:
    saved = await call(client, "save_speech", {"text": "Saved, not spoken.", "path": str(tmp_path / "speech.aiff")})

    assert Path(saved["path"]).resolve() == (tmp_path / "speech.aiff").resolve()
    assert Path(saved["path"]).stat().st_size > 1000


async def test_speech_is_not_saved_in_a_format_there_is_not(client: Client, tmp_path: Path) -> None:
    result = await client.call_tool("save_speech", {"text": "Never said.", "path": str(tmp_path / "speech.mp3")})

    assert result.is_error
    assert "ValueError" in text(result)
    assert not (tmp_path / "speech.mp3").exists()
