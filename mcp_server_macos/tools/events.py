"""Tools for what happens on the Mac: sleep and wake, the screen locking, apps opening and quitting..., from ``macos.events``."""

from typing import Annotated, Any, Dict, Literal, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .. import _elsewhere
from .._registry import LONGEST_WAIT, READ_ONLY, add_tool

EventName = Literal[
    "sleep",
    "wake",
    "display_sleep",
    "display_wake",
    "screen_locked",
    "screen_unlocked",
    "space_changed",
    "app_launched",
    "app_quit",
    "app_activated",
    "app_hidden",
    "app_unhidden",
    "volume_mounted",
    "volume_unmounted",
    "power_connected",
    "power_disconnected",
    "network_changed",
    "usb_connected",
    "usb_disconnected",
    "displays_changed",
]


class EventApp(BaseModel):
    """The app an event is about."""

    name: Optional[str] = Field(description="Its name.")
    bundle_id: Optional[str] = Field(description="Its bundle identifier, such as 'com.apple.Safari'.")
    pid: int = Field(description="Its process ID.")
    path: Optional[str] = Field(description="Where it is.")


class Event(BaseModel):
    """Something that happened."""

    name: str = Field(description="What happened, as asked for.")
    app: Optional[EventApp] = Field(description="The app, for the app_ events.")
    path: Optional[str] = Field(description="The disk's mount point, for volume_mounted and volume_unmounted.")
    device: Optional[str] = Field(description="The device's name, for usb_connected and usb_disconnected.")


class EventWait(BaseModel):
    """What happened while the Mac was listened to."""

    event: Optional[Event] = Field(description="The event. Null when the time ran out first.")


def _wait_here(name: str, timeout: float) -> Optional[Dict[str, Any]]:
    """
    Wait for ``name`` on this process's main thread, which macOS delivers the events to: the event as JSON
    can carry it, or None. Run by the process wait_for_event starts.
    """
    event = macos.events.wait(name, timeout=timeout)
    if event is None:
        return None
    app = event.app
    return {
        "name": event.name,
        "app": (
            None if app is None else {"name": app.name, "bundle_id": app.bundle_id, "pid": app.pid, "path": app.path}
        ),
        "path": None if event.path is None else str(event.path),
        "device": event.device,
    }


def wait_for_event(
    name: Annotated[
        EventName,
        Field(
            description="What to wait for: the Mac or the displays going to 'sleep' and waking, the screen locked or "
            "unlocked, another Space shown, an app launched, quit, activated, hidden or unhidden, a disk mounted or "
            "unmounted, the charger connected or not, the network changed, a USB device connected or not, a display "
            "connected or rearranged."
        ),
    ],
    timeout_seconds: Annotated[float, Field(description="How long to wait, in seconds.", gt=0, le=LONGEST_WAIT)] = 60.0,
) -> EventWait:
    """
    Wait for something to happen on the Mac, such as an app to quit, the screen to be unlocked or a USB
    drive to be plugged in, and say what. It listens from about a second after the call: what happened
    before isn't seen. Needs no permission.
    """
    # macOS delivers these events to the main thread, which is the server's: it would answer nothing else
    # meanwhile. A process of its own waits on its own main thread instead, and says what happened.
    found = _elsewhere.call("mcp_server_macos.tools.events:_wait_here", [name, timeout_seconds], lasts=timeout_seconds)
    return EventWait(event=None if found is None else Event.model_validate(found))


def register(server: MCPServer) -> None:
    add_tool(server, wait_for_event, title="Wait for something to happen", annotations=READ_ONLY)
