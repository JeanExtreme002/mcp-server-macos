"""Tools for global keyboard shortcuts, pressed in any app, from ``macos.hotkeys``."""

from typing import Annotated

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._permissions import INPUT_MONITORING_AND_ACCESSIBILITY
from .._registry import LONGEST_WAIT, READ_ONLY, add_tool
from .keyboard import read_layout_on_main_thread


class ShortcutWait(BaseModel):
    """Whether the shortcut was pressed."""

    pressed: bool = Field(description="True when it was pressed, false when the time ran out first.")


def wait_for_shortcut(
    keys: Annotated[
        str,
        Field(
            description="The shortcut, written as for press_keys: 'ctrl+option+s', 'f5'. Not a modifier alone.",
            min_length=1,
        ),
    ],
    timeout_seconds: Annotated[float, Field(description="How long to wait, in seconds.", gt=0, le=LONGEST_WAIT)] = 60.0,
) -> ShortcutWait:
    """
    Wait for the user to press a shortcut, in any app: for them to say they're ready, or that a step is
    done. The app in front doesn't get it, so pick one apps don't use.
    """
    read_layout_on_main_thread()
    return ShortcutWait(pressed=macos.hotkeys.wait(keys, timeout=timeout_seconds))


def register(server: MCPServer) -> None:
    add_tool(
        server,
        wait_for_shortcut,
        title="Wait for a shortcut",
        annotations=READ_ONLY,
        permission=INPUT_MONITORING_AND_ACCESSIBILITY,
    )
