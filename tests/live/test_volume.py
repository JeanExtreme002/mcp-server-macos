"""The volume tools against this Mac: the volume and the mute are read, and set to what they were."""

import pytest
from mcp import Client

from tests.helpers import text

pytestmark = pytest.mark.anyio


async def test_volume_is_read_and_set_to_what_it_was(client: Client) -> None:
    result = await client.call_tool("get_volume", {})
    assert not result.is_error, text(result)
    volume = result.structured_content
    assert volume is not None

    if volume["level"] is None:
        pytest.skip("the output device has no volume control")
    assert 0 <= volume["level"] <= 100
    assert isinstance(volume["muted"], bool)

    result = await client.call_tool("set_volume", {"level": volume["level"]})
    assert not result.is_error, text(result)
    result = await client.call_tool("set_muted", {"muted": volume["muted"]})
    assert not result.is_error, text(result)

    result = await client.call_tool("get_volume", {})
    assert result.structured_content == volume
