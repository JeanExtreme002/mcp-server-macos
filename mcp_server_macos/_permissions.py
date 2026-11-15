"""
The privacy permissions of macOS that tools may need, and what the server does when one is missing.

macOS lets only the user grant a permission: no program can give one to itself. What the server can do
is ask macOS to show its prompt, where it has one, and otherwise tell the model exactly what the user
has to allow and where, so it can ask them.

A permission is granted to the app that runs the server (the MCP client, or the terminal it was started
from), not to the server. Notifications are the exception: they belong to Script Editor, which posts them.
"""

from dataclasses import dataclass
from typing import Callable, Optional

import macos

#: Who the user has to allow, unless the permission says otherwise, in words a model can pass on.
APP = "the app that runs this server (the MCP client, or the terminal it was started from)"


@dataclass(frozen=True)
class Permission:
    """A privacy permission of macOS."""

    #: Its name in System Settings.
    name: str

    #: Where the user grants it.
    where: str

    #: Asks macOS to show its prompt, and returns whether the permission is granted now. ``None`` when
    #: there's nothing to call: macOS asks by itself the first time, or has no prompt for it.
    request: Optional[Callable[[], bool]] = None

    #: Whether the app has to be restarted for the permission to apply.
    restart: bool = False

    #: Who the user has to allow: the app that runs the server, for all but a few.
    app: str = APP

    #: What else the user may need to know.
    note: str = ""

    def instructions(self) -> str:
        """What to ask the user for, once the permission is known to be missing."""
        text = "This needs the {} permission, which only the user can grant. Ask them to allow {} in {}".format(
            self.name, self.app, self.where
        )
        text += ", to restart that app, and then try again." if self.restart else ", and then try again."
        return "{} {}".format(text, self.note) if self.note else text


# The functions of pymacos are looked up when called, not here: the package imports anywhere, and a
# test can replace them.

SCREEN_RECORDING = Permission(
    name="Screen Recording",
    where="System Settings › Privacy & Security › Screen & System Audio Recording",
    request=lambda: macos.screen.request_permission(),
    restart=True,
)

#: Sending keystrokes and mouse events, and controlling the windows of other apps.
ACCESSIBILITY = Permission(
    name="Accessibility",
    where="System Settings › Privacy & Security › Accessibility",
    request=lambda: macos.keyboard.request_permission(),
    restart=True,
)

#: Listening to the keyboard and the mouse.
INPUT_MONITORING = Permission(
    name="Input Monitoring",
    where="System Settings › Privacy & Security › Input Monitoring",
    request=lambda: macos.keyboard.request_listen_permission(),
    restart=True,
)

CAMERA = Permission(
    name="Camera",
    where="System Settings › Privacy & Security › Camera",
    request=lambda: macos.camera.request_permission(),
    restart=True,
)

MICROPHONE = Permission(
    name="Microphone",
    where="System Settings › Privacy & Security › Microphone",
    request=lambda: macos.audio.request_permission(),
    restart=True,
)

#: Controlling another app (Finder, System Events, Music, a browser). macOS asks by itself, the first
#: time an app is controlled.
AUTOMATION = Permission(
    name="Automation",
    where="System Settings › Privacy & Security › Automation",
)

#: Connecting devices and turning Bluetooth on or off. macOS may ask by itself, the first time.
BLUETOOTH = Permission(
    name="Bluetooth",
    where="System Settings › Privacy & Security › Bluetooth",
)

#: Running JavaScript in a browser's tab, which each browser turns on in its own menu.
BROWSER_JAVASCRIPT = Permission(
    name="Allow JavaScript from Apple Events",
    app="the browser",
    where=(
        "its own menu: in Safari, Develop › Allow JavaScript from Apple Events (the Develop menu shows once it's "
        "turned on in Safari › Settings › Advanced); in Chrome and the other Chromium browsers, View › Developer › "
        "Allow JavaScript from Apple Events"
    ),
)

FULL_DISK_ACCESS = Permission(
    name="Full Disk Access",
    where="System Settings › Privacy & Security › Full Disk Access",
    restart=True,
)

#: Notifications are posted through Script Editor, so it's Script Editor that needs them turned on.
NOTIFICATIONS = Permission(
    name="Notifications",
    where="System Settings › Notifications › Script Editor",
    app="Script Editor, which macOS shows the notifications as coming from,",
    note=(
        "If Script Editor isn't listed there yet, the user can open Script Editor, run "
        '`display notification "hi"` once and accept the prompt.'
    ),
)


def missing(error: macos.PermissionDeniedError, permission: Optional[Permission]) -> str:
    """
    The message for a model when ``error`` was raised, and stays: what pymacos said, and for a tool that
    needs ``permission``, what the user has to allow.
    """
    described = "{}: {}".format(type(error).__name__, error)
    if permission is None:
        # The tool needs no privacy permission, so what pymacos refused is something else, which its
        # message says: a PDF's password, a preference a profile manages, a Keychain item the user
        # didn't let through. Telling the model to have an app allowed would send it the wrong way.
        return described
    return "{} {}".format(described, permission.instructions())


def ask(permission: Optional[Permission]) -> bool:
    """
    Ask macOS to show its prompt for ``permission``, and return whether it's granted now.

    ``False`` when there's no prompt to show, when the user declined, and when the permission only
    applies after a restart, which is the usual answer of macOS right after the user allowed it.
    """
    if permission is None or permission.request is None:
        return False
    try:
        return bool(permission.request())
    except macos.MacOSError:
        return False
