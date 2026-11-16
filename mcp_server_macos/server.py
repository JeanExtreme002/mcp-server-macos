"""The server: what it tells a client about itself, and the command that runs it."""

import argparse
import os
from typing import Iterable, List, Optional, Sequence

from mcp.server.mcpserver import MCPServer

from . import __version__, _on_demand, tools

NAME = "mcp-server-macos"

#: What --toolsets takes for every toolset, enabled from the start.
ALL = "all"

#: The environment variable that chooses the toolsets, for the clients that can't pass arguments.
TOOLSETS_VARIABLE = "MCP_SERVER_MACOS_TOOLSETS"

INSTRUCTIONS = (
    "Tools that act on the Mac this server runs on, which is the user's own computer. "
    "Reading tools are safe to call at any time. Tools that show, change or send something are seen by the user: "
    "call them when the user asked for it, or when it clearly serves what they asked. "
    "When a tool fails for a missing permission, only the user can grant it: tell them what the error says to "
    "allow and where, and call the tool again once they say it's done."
)

#: Added to the instructions of a server started with some of the toolsets only.
ON_DEMAND_INSTRUCTIONS = (
    " Only some of the tools are listed at first. When a task needs one that isn't, enable_toolsets adds "
    "the toolset it's in (its description lists them all), and find_tools searches every tool by what it does."
)


def create_server(toolsets: Optional[Iterable[str]] = None) -> MCPServer:
    """
    A new server, with the tools of :mod:`mcp_server_macos.tools` registered.

    ``toolsets`` names the ones to register (``["system", "notifications"]``): every toolset when
    ``None``. With only some, the others are a call away: ``find_tools`` searches every tool, and
    ``enable_toolsets`` adds toolsets while the server runs (see :mod:`mcp_server_macos._on_demand`).
    Raises :class:`ValueError` for a name that isn't a toolset.
    """
    chosen = list(tools.TOOLSETS) if toolsets is None else list(dict.fromkeys(toolsets))
    on_demand = set(chosen) != set(tools.TOOLSETS)
    server = MCPServer(
        name=NAME,
        title="macOS",
        instructions=INSTRUCTIONS + (ON_DEMAND_INSTRUCTIONS if on_demand else ""),
        version=__version__,
        website_url="https://github.com/JeanExtreme002/mcp-server-macos",
    )
    tools.register(server, toolsets)
    if on_demand:
        _on_demand.OnDemand(server, chosen).register()
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
        help="the toolsets to start with, separated by commas, or 'all': {}. By default, {}: the model "
        "finds and enables the others as a task needs them, so a client isn't sent every tool before its "
        "first question. The {} environment variable does the same, when this isn't given.".format(
            ", ".join(tools.TOOLSETS), ", ".join(_on_demand.CORE), TOOLSETS_VARIABLE
        ),
    )
    arguments = parser.parse_args(argv)

    chosen = arguments.toolsets if arguments.toolsets is not None else os.environ.get(TOOLSETS_VARIABLE)
    names = list(_on_demand.CORE) if chosen is None else _names(chosen)
    try:
        server = create_server(None if names == [ALL] else names)
    except ValueError as error:
        parser.error(str(error))

    server.run("stdio")
