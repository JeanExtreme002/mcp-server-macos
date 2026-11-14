"""
Tools about the Mac itself, from ``macos.system``: what it is, how it's doing, its disks, processes,
settings and logs.

``macos.system`` is the largest module of pymacos, so its tools are spread over a few files, by what
they're about. They make one toolset, ``system``.
"""

from mcp.server.mcpserver import MCPServer

from . import diagnostics, disks, info, processes, settings, status


def register(server: MCPServer) -> None:
    for module in (info, status, disks, processes, settings, diagnostics):
        module.register(server)
