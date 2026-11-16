"""The server: what it tells a client about itself, and the command that runs it."""

import argparse
import os
from typing import Any, Iterable, List, Optional, Sequence

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
    " Only some of the tools are listed at first, and there's one for most of what a Mac does: files, PDFs, "
    "images, videos, audio, apps, windows, the screen, the keyboard and mouse, the settings. For a task on this "
    "Mac, look for a tool here before writing a script or installing a library: enable_toolsets lists every "
    "toolset with the names of its tools, and adds the toolset a task needs; find_tools searches every tool by "
    "what it does."
)


class _Server(MCPServer):
    """The SDK's server, which may add toolsets for the client before it lists its tools."""

    on_demand: Optional[_on_demand.OnDemand] = None

    async def _handle_list_tools(self, ctx: Any, params: Any) -> Any:
        if self.on_demand is not None:
            client = getattr(getattr(ctx.session, "client_params", None), "client_info", None)
            self.on_demand.for_client(getattr(client, "name", None))
        return await super()._handle_list_tools(ctx, params)


def create_server(toolsets: Optional[Iterable[str]] = None, *, follow_client: bool = False) -> MCPServer:
    """
    A new server, with the tools of :mod:`mcp_server_macos.tools` registered.

    ``toolsets`` names the ones to register (``["system", "notifications"]``): every toolset when
    ``None``. With only some, the others are a call away: ``find_tools`` searches every tool, and
    ``enable_toolsets`` adds toolsets while the server runs (see :mod:`mcp_server_macos._on_demand`).
    Raises :class:`ValueError` for a name that isn't a toolset.

    ``follow_client`` is for toolsets left to the server, as the command's default: a client that defers
    the tools itself (:data:`~mcp_server_macos._on_demand.CLIENTS_THAT_DEFER`) then gets every toolset.
    """
    chosen = list(tools.TOOLSETS) if toolsets is None else list(dict.fromkeys(toolsets))
    on_demand = set(chosen) != set(tools.TOOLSETS)
    server = _Server(
        name=NAME,
        title="macOS",
        instructions=INSTRUCTIONS + (ON_DEMAND_INSTRUCTIONS if on_demand else ""),
        version=__version__,
        website_url="https://github.com/JeanExtreme002/mcp-server-macos",
    )
    tools.register(server, toolsets)
    if on_demand:
        server.on_demand = _on_demand.OnDemand(server, chosen, follow_client=follow_client)
        server.on_demand.register()
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
        server = create_server(None if names == [ALL] else names, follow_client=chosen is None)
    except ValueError as error:
        parser.error(str(error))

    server.run("stdio")
