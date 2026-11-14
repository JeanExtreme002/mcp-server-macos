"""The server as a client sees it: who it is, and which tools it lists."""

import re

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer

import mcp_server_macos
from mcp_server_macos import create_server
from tests.helpers import text

pytestmark = pytest.mark.anyio

# Every tool, by name. A new tool is added here, and only here (test_stdio.py uses this list too): a
# client finds tools by name, so renaming or dropping one breaks whoever relies on it, and shouldn't
# happen unnoticed.
TOOLS = {"get_system_info", "send_notification"}


async def test_server_introduces_itself(client: Client) -> None:
    info = client.server_info

    assert info is not None
    assert info.name == "mcp-server-macos"
    assert info.title == "macOS"
    assert info.version == mcp_server_macos.__version__
    assert client.instructions


async def test_tools_are_the_expected_ones(client: Client) -> None:
    listed = await client.list_tools()

    assert {tool.name for tool in listed.tools} == TOOLS
    assert len(listed.tools) == len(TOOLS), "a tool is listed twice"


async def test_every_tool_is_described(client: Client) -> None:
    for tool in (await client.list_tools()).tools:
        assert re.fullmatch(r"[a-z][a-z0-9]*(_[a-z0-9]+)*", tool.name), "{}: not snake_case".format(tool.name)
        assert tool.title, "{}: no title".format(tool.name)
        assert tool.description and len(tool.description) > 20, "{}: no description".format(tool.name)

        # The hints a client decides with: each tool says whether it only reads, and none is left
        # for the client to assume (it would assume the worst: destructive, open to the world).
        assert tool.annotations is not None, "{}: no annotations".format(tool.name)
        assert tool.annotations.read_only_hint is not None, "{}: readOnlyHint is unset".format(tool.name)
        assert tool.annotations.open_world_hint is not None, "{}: openWorldHint is unset".format(tool.name)
        if not tool.annotations.read_only_hint:
            assert tool.annotations.destructive_hint is not None, "{}: destructiveHint is unset".format(tool.name)
            assert tool.annotations.idempotent_hint is not None, "{}: idempotentHint is unset".format(tool.name)

        for name, argument in tool.input_schema.get("properties", {}).items():
            assert argument.get("description"), "{}: the argument {} isn't described".format(tool.name, name)


async def test_unknown_tool_is_an_error(client: Client) -> None:
    result = await client.call_tool("no_such_tool", {})

    assert result.is_error
    assert "no_such_tool" in text(result)


def test_servers_are_independent() -> None:
    # Nothing is registered on a shared, module-level server: each call builds its own.
    first, second = create_server(), create_server()

    assert first is not second
    assert isinstance(first, MCPServer)
