"""
Fixtures for every test: a server, and a client connected to it in-process.

The tests are async (the MCP client is), and run by the pytest plugin of anyio, which comes with the
MCP SDK: an async test is marked with ``pytest.mark.anyio``, usually for its whole module.
"""

import sys
from typing import AsyncIterator

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer

from mcp_server_macos import create_server


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    # Everything under tests/live talks to the real system: marked here, so no file can forget to,
    # and skipped outside macOS.
    for item in items:
        if "live" in item.path.parts:
            item.add_marker(pytest.mark.live)
            if sys.platform != "darwin":
                item.add_marker(pytest.mark.skip(reason="the live tests need macOS"))


@pytest.fixture
def anyio_backend() -> str:
    # asyncio only, which is what the server runs on (anyio would run each test on trio too).
    return "asyncio"


@pytest.fixture(scope="session")
def server() -> MCPServer:
    """
    One server for the whole run: building one registers every tool, which takes a moment, and most
    tests need nothing of their own from it. The tools look the functions of pymacos up when they're
    called, so a test that fakes one still gets its fake. A test whose tools keep state (keeping the Mac
    awake) gives itself a server of its own, by defining this fixture again.
    """
    return create_server()


@pytest.fixture
async def client(server: MCPServer) -> AsyncIterator[Client]:
    """A client connected to the server through the protocol, with no process or pipe in between."""
    async with Client(server) as connected:
        yield connected
