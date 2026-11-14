"""get_system_info against this Mac."""

import re

import pytest
from mcp import Client

from tests.helpers import text

pytestmark = pytest.mark.anyio


async def test_get_system_info(client: Client) -> None:
    result = await client.call_tool("get_system_info", {})

    assert not result.is_error, text(result)
    info = result.structured_content
    assert info is not None
    assert re.fullmatch(r"\d+\.\d+(\.\d+)?", info["macos_version"]), info
    assert info["macos_build"]
    assert info["model"]
    assert info["model_identifier"]
    assert info["processor"]
    assert info["memory_bytes"] >= 1024**3
    assert info["computer_name"]
    assert info["uptime_seconds"] > 0
