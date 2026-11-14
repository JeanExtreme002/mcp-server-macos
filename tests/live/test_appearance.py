"""The appearance tools against this Mac: the settings are read, and none is changed."""

import re

import pytest
from mcp import Client

from tests.helpers import text

pytestmark = pytest.mark.anyio


async def test_get_appearance(client: Client) -> None:
    result = await client.call_tool("get_appearance", {})

    assert not result.is_error, text(result)
    appearance = result.structured_content
    assert appearance is not None
    assert appearance["mode"] in ("dark", "light")
    assert isinstance(appearance["auto"], bool)
    assert re.fullmatch(r"#[0-9a-f]{6}", appearance["accent_color"]), appearance
    assert isinstance(appearance["menu_bar_hidden"], bool)
    assert appearance["scroll_bars"] in ("automatic", "when_scrolling", "always")
    assert isinstance(appearance["font_smoothing"], bool)


async def test_set_appearance_to_a_color_there_is_not_changes_nothing(client: Client) -> None:
    before = (await client.call_tool("get_appearance", {})).structured_content

    result = await client.call_tool("set_appearance", {"accent_color": "teal", "font_smoothing": False})

    assert result.is_error
    assert (await client.call_tool("get_appearance", {})).structured_content == before


async def test_waiting_for_a_switch_that_does_not_come(client: Client) -> None:
    result = await client.call_tool("wait_for_appearance_change", {"timeout_seconds": 1.5})

    assert result.is_error
    assert "WaitTimeoutError" in text(result)
