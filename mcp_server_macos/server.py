"""The server: what it tells a client about itself, and the command that runs it."""

import argparse
import os
from typing import Iterable, List, Optional, Sequence

from mcp.server.mcpserver import MCPServer

from . import __version__, tools

NAME = "mcp-server-macos"

#: The environment variable that chooses the toolsets, for the clients that can't pass arguments.
TOOLSETS_VARIABLE = "MCP_SERVER_MACOS_TOOLSETS"

INSTRUCTIONS = (
    "Tools that act on the Mac this server runs on, which is the user's own computer. "
    "Reading tools are safe to call at any time. Tools that show, change or send something are seen by the user: "
    "call them when the user asked for it, or when it clearly serves what they asked. "
    "When a tool fails for a missing permission, only the user can grant it: tell them what the error says to "
    "allow and where, and call the tool again once they say it's done."
)


def create_server(toolsets: Optional[Iterable[str]] = None) -> MCPServer:
    """
    A new server, with the tools of :mod:`mcp_server_macos.tools` registered.

    ``toolsets`` names the ones to register (``["system", "notifications"]``): every toolset when
    ``None``. Raises :class:`ValueError` for a name that isn't a toolset.
    """
    server = MCPServer(
        name=NAME,
        title="macOS",
        instructions=INSTRUCTIONS,
        version=__version__,
        website_url="https://github.com/JeanExtreme002/mcp-server-macos",
    )
    tools.register(server, toolsets)
    return server


def _names(text: str) -> List[str]:
    # "system, notifications" -> ["system", "notifications"]
    return [name.strip() for name in text.split(",") if name.strip()]


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Run the server over stdio, which is how MCP clients launch a local server."""
    parser = argparse.ArgumentParser(
        prog=NAME,
        description="An MCP server for automating and controlling macOS. It talks MCP over stdin and stdout: "
        "it's meant to be launched by an MCP client, not used from a terminal.",
    )
    parser.add_argument("--version", action="version", version="{} {}".format(NAME, __version__))
    parser.add_argument(
        "--toolsets",
        metavar="NAMES",
        help="the toolsets to offer, separated by commas: {}. All of them by default. "
        "The {} environment variable does the same, when this isn't given.".format(
            ", ".join(tools.TOOLSETS), TOOLSETS_VARIABLE
        ),
    )
    arguments = parser.parse_args(argv)

    chosen = arguments.toolsets if arguments.toolsets is not None else os.environ.get(TOOLSETS_VARIABLE)
    try:
        server = create_server(None if chosen is None else _names(chosen))
    except ValueError as error:
        parser.error(str(error))

    server.run("stdio")
