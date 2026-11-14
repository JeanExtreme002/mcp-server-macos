"""
The server as a client really runs it: a process of its own, talking MCP over stdin and stdout.

The other unit tests connect to the server in-process. This one catches what they can't: a command
that doesn't start, or anything but MCP written to stdout, which breaks the protocol.
"""

import sys

import pytest
from mcp import Client, StdioServerParameters

import mcp_server_macos
from tests.unit.test_server import TOOLS

pytestmark = pytest.mark.anyio


async def test_server_runs_over_stdio() -> None:
    command = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server_macos"])

    async with Client(command) as client:
        listed = await client.list_tools()

        assert client.server_info is not None
        assert client.server_info.name == "mcp-server-macos"
        assert client.server_info.version == mcp_server_macos.__version__
        assert {tool.name for tool in listed.tools} == TOOLS
