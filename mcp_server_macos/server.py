"""The server: what it tells a client about itself, and the command that runs it."""

import argparse
from typing import Optional, Sequence

from mcp.server.mcpserver import MCPServer

from . import __version__, tools

NAME = "mcp-server-macos"

INSTRUCTIONS = (
    "Tools that act on the Mac this server runs on, which is the user's own computer. "
    "Reading tools are safe to call at any time. Tools that show, change or send something are seen by the user: "
    "call them when the user asked for it, or when it clearly serves what they asked."
)


def create_server() -> MCPServer:
    """A new server, with every tool of :mod:`mcp_server_macos.tools` registered."""
    server = MCPServer(
        name=NAME,
        title="macOS",
        instructions=INSTRUCTIONS,
        version=__version__,
        website_url="https://github.com/JeanExtreme002/mcp-server-macos",
    )
    tools.register_all(server)
    return server


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Run the server over stdio, which is how MCP clients launch a local server."""
    parser = argparse.ArgumentParser(
        prog=NAME,
        description="An MCP server for automating and controlling macOS. It talks MCP over stdin and stdout: "
        "it's meant to be launched by an MCP client, not used from a terminal.",
    )
    parser.add_argument("--version", action="version", version="{} {}".format(NAME, __version__))
    parser.parse_args(argv)

    create_server().run("stdio")
