"""
The screen tools against this Mac: read only, and screenshots saved in a temporary folder. No setting is
changed, the screen isn't locked nor its resolution touched: the user would see it all.
"""

from pathlib import Path

import pytest
from mcp import Client
from mcp.types import ImageContent, TextContent

from tests.helpers import text
from tests.live.helpers import call

pytestmark = pytest.mark.anyio


async def test_displays_are_read(client: Client) -> None:
    found = await call(client, "get_displays")

    main = found["displays"][0]
    assert (main["number"], main["main"]) == (1, True)
    assert main["pixel_width"] >= main["width"] > 0
    assert main["brightness"] is None or 0 <= main["brightness"] <= 100

    modes = await call(client, "get_display_modes")
    assert modes["available"]
    assert (modes["current"]["width"], modes["current"]["height"]) == (main["width"], main["height"])

    settings = await call(client, "get_display_settings")
    assert isinstance(settings["locked"], bool)
    assert settings["night_shift_schedule"] in ("never", "sunset", None) or set(settings["night_shift_schedule"]) == {
        "start",
        "end",
    }
    screenshots = await call(client, "get_screenshot_settings")
    assert Path(screenshots["folder"]).is_absolute()


async def test_a_display_that_isnt_there_is_refused(client: Client) -> None:
    result = await client.call_tool("get_display_modes", {"display": 99})

    assert result.is_error and "no display 99" in text(result)


async def test_the_screen_is_seen(client: Client, tmp_path: Path) -> None:
    if not (await call(client, "get_display_settings"))["screen_recording_permission"]:
        pytest.skip("Screen Recording isn't granted here")

    result = await client.call_tool("take_screenshot", {"region": {"x": 0, "y": 0, "width": 300, "height": 100}})
    assert not result.is_error, result.content
    image, said = result.content
    assert isinstance(image, ImageContent) and image.mime_type == "image/jpeg"
    assert isinstance(said, TextContent) and "300×100 points" in said.text

    saved = await call(client, "save_screenshot", {"path": str(tmp_path / "screen.png")})
    assert Path(saved["path"]).stat().st_size > 0
    assert (await call(client, "get_screen_color", {"x": 1, "y": 1}))["color"].startswith("#")
    assert await call(client, "find_text_on_screen", {"text": "zq-nowhere-xj"}) == []
