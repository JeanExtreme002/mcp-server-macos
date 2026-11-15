"""
The tools, one module per module of pymacos (``tools/system.py`` uses ``macos.system``).

Each module defines its tools as plain functions and a ``register(server)`` that adds them with
:func:`mcp_server_macos._registry.add_tool`. A new module is listed in :data:`MODULES` (a test fails
when one is left out).

A module is also a toolset, named after it: the server can be started with only some of them (see
:func:`register`), for a client or a user that doesn't want every tool listed.
"""

from types import ModuleType
from typing import Dict, Iterable, Optional, Tuple

from mcp.server.mcpserver import MCPServer

from . import (
    appearance,
    apps,
    audio,
    auth,
    bluetooth,
    browser,
    camera,
    clipboard,
    defaults,
    dialog,
    dock,
    document,
    events,
    finder,
    hotkeys,
    image,
    keyboard,
    keychain,
    language,
    launch,
    maps,
    mouse,
    music,
    network,
    notifications,
    pdf,
    power,
    printer,
    schedule,
    screen,
    settings,
    shortcuts,
    sound,
    speech,
    spotlight,
    system,
    time_machine,
    trackpad,
    video,
    vision,
    volume,
    windows,
)

#: Every tool module, in the order the tools are listed to a client.
MODULES: Tuple[ModuleType, ...] = (
    appearance,
    apps,
    audio,
    auth,
    bluetooth,
    browser,
    camera,
    clipboard,
    defaults,
    dialog,
    dock,
    document,
    events,
    finder,
    hotkeys,
    image,
    keyboard,
    keychain,
    language,
    launch,
    maps,
    mouse,
    music,
    network,
    notifications,
    pdf,
    power,
    printer,
    schedule,
    screen,
    settings,
    shortcuts,
    sound,
    speech,
    spotlight,
    system,
    time_machine,
    trackpad,
    video,
    vision,
    volume,
    windows,
)

#: The modules by the name of their toolset: ``"system"`` for ``tools/system.py``.
TOOLSETS: Dict[str, ModuleType] = {module.__name__.rpartition(".")[2]: module for module in MODULES}


def register(server: MCPServer, toolsets: Optional[Iterable[str]] = None) -> None:
    """
    Add the tools of ``toolsets`` to ``server``: all of them when ``None``.

    Raises :class:`ValueError` for a name that isn't a toolset, or when ``toolsets`` is empty: a server
    with no tools is a mistake in its configuration, better said than obeyed.
    """
    if toolsets is None:
        chosen = list(TOOLSETS)
    else:
        chosen = list(dict.fromkeys(toolsets))  # without repetitions, in the order given
        unknown = [name for name in chosen if name not in TOOLSETS]
        if unknown:
            raise ValueError(
                "unknown toolset{}: {}. The toolsets are: {}".format(
                    "s" if len(unknown) > 1 else "", ", ".join(unknown), ", ".join(TOOLSETS)
                )
            )
        if not chosen:
            raise ValueError("no toolset was chosen. The toolsets are: {}".format(", ".join(TOOLSETS)))

    # In the order of MODULES, whatever the order asked for: the list a client sees doesn't depend on it.
    for name, module in TOOLSETS.items():
        if name in chosen:
            module.register(server)
