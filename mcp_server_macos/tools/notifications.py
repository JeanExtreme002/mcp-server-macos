"""Tools that notify the user, from ``macos.notifications``."""

from typing import Annotated, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._permissions import NOTIFICATIONS
from .._registry import ADDITIVE, READ_ONLY, add_tool


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


class NotificationPermission(BaseModel):
    """Whether notifications can be shown."""

    allowed: Optional[bool] = Field(
        description="Whether macOS lets Script Editor, which posts the notifications, show them. Null when it "
        "can't tell: Script Editor has never posted one yet, or the settings couldn't be read."
    )


def check_notification_permission() -> NotificationPermission:
    """
    Check whether send_notification can show notifications, without sending one. A Focus mode such as
    Do Not Disturb can still hide notifications that are allowed.
    """
    return NotificationPermission(allowed=macos.notifications.is_allowed())


def register(server: MCPServer) -> None:
    add_tool(server, check_notification_permission, title="Check whether notifications are allowed", annotations=READ_ONLY)
    add_tool(server, send_notification, title="Send a notification", annotations=ADDITIVE, permission=NOTIFICATIONS)
