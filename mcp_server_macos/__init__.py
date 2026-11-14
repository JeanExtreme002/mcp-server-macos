"""
mcp-server-macos — an MCP server for automating and controlling macOS.

It exposes features of `pymacos <https://github.com/JeanExtreme002/pymacos>`_ as tools of the
`Model Context Protocol <https://modelcontextprotocol.io>`_, so an MCP client (Claude Desktop, Claude Code,
an IDE...) can use the Mac it runs on.

Run it with the ``mcp-server-macos`` command, or ``python -m mcp_server_macos``. To embed it::

    from mcp_server_macos import create_server

    create_server().run("stdio")
"""

__version__ = "0.1.1"

from .server import create_server, main

__all__ = ["__version__", "create_server", "main"]
