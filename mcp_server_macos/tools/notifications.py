"""Tools that notify the user, from ``macos.notifications``."""

from typing import Annotated, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import Field

from .._registry import ADDITIVE, add_tool


def send_notification(
    message: Annotated[str, Field(description="The notification's text.", min_length=1)],
    title: Annotated[Optional[str], Field(description="The title, in bold above the text.")] = None,
    subtitle: Annotated[Optional[str], Field(description="A line between the title and the text.")] = None,
    sound: Annotated[
        Optional[str],
        Field(description="The name of a system alert sound to play, e.g. 'Glass', 'Ping' or 'Basso'. Silent by default."),
    ] = None,
) -> str:
    """
    Show a notification on this Mac, in the top-right corner of the screen and in Notification Center.

    macOS shows it as coming from Script Editor. Text over 4096 characters is clipped. Don't put a secret
    in a notification: other processes of the user can see its text while it's being posted.
    """
    macos.notify(message, title=title, subtitle=subtitle, sound=sound)
    return "Notification sent."


def register(server: MCPServer) -> None:
    add_tool(server, send_notification, title="Send a notification", annotations=ADDITIVE)
