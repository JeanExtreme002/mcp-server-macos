"""
The tools, one module per module of pymacos (``tools/system.py`` uses ``macos.system``).

Each module defines its tools as plain functions and a ``register(server)`` that adds them with
:func:`mcp_server_macos._registry.add_tool`. A new module is listed in :data:`MODULES` (a test fails
when one is left out).
"""

from types import ModuleType
from typing import Tuple

from mcp.server.mcpserver import MCPServer

from . import notifications, system

#: Every tool module, in the order the tools are listed to a client.
MODULES: Tuple[ModuleType, ...] = (
    notifications,
    system,
)


def register_all(server: MCPServer) -> None:
    """Add the tools of every module to ``server``."""
    for module in MODULES:
        module.register(server)
