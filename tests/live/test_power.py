"""The power tools against this Mac: it's kept awake for a moment, and never put to sleep."""

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer

from mcp_server_macos import create_server

from tests.helpers import text

pytestmark = pytest.mark.anyio


@pytest.fixture
def server() -> MCPServer:
    """A server for each test: what keep_awake holds is the server's, and mustn't carry from one test to the next."""
    return create_server()


async def test_get_power_status(client: Client) -> None:
    result = await client.call_tool("get_power_status", {})

    assert not result.is_error, text(result)
    status = result.structured_content
    assert status is not None
    assert isinstance(status["low_power_mode"], bool)
    if status["battery"] is not None:  # a laptop
        assert 0 <= status["battery"]["percent"] <= 100
        assert isinstance(status["battery"]["charging"], bool)
        assert isinstance(status["battery"]["plugged_in"], bool)


async def test_keep_awake_shows_among_the_sleep_blockers_until_sleep_is_allowed(client: Client) -> None:
    def ours(result: object) -> list:  # type: ignore[type-arg]
        blockers = result.structured_content["result"]  # type: ignore[attr-defined]
        return [blocker for blocker in blockers if blocker["reason"] == "mcp-server-macos keep_awake"]

    assert ours(await client.call_tool("get_sleep_blockers", {})) == []

    result = await client.call_tool("keep_awake", {"minutes": 1})
    assert not result.is_error, text(result)
    try:
        (blocker,) = ours(await client.call_tool("get_sleep_blockers", {}))
        assert blocker["display"] is False
        assert blocker["kind"] == "PreventUserIdleSystemSleep"
    finally:
        result = await client.call_tool("allow_sleep", {})

    assert text(result) == "The Mac may sleep again."
    assert ours(await client.call_tool("get_sleep_blockers", {})) == []

    result = await client.call_tool("allow_sleep", {})
    assert text(result) == "The Mac wasn't being kept awake by this server."
