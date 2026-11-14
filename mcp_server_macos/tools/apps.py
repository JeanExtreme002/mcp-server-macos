"""Tools for applications: the running and the installed ones, opening, quitting and uninstalling them, from ``macos.apps``."""

import time
from typing import Annotated, List, Optional

import macos
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from .._permissions import AUTOMATION
from .._registry import ADDITIVE, DESTRUCTIVE, OPEN_ENDED, READ_ONLY, REPLACING, add_tool

AppName = Annotated[
    str,
    Field(
        description="The app: its name ('Safari'), its bundle identifier ('com.apple.Safari') or the path of its .app.",
        min_length=1,
    ),
]
Kind = Annotated[
    str,
    Field(description="A kind of file: an extension ('pdf', '.png') or a type identifier ('public.plain-text').", min_length=1),
]
# How long to wait for an app to quit, in seconds, before saying it didn't.
QUIT_TIMEOUT = 10.0

# How long to wait for an app to hide or show, in seconds: macOS does it a moment after it's asked.
HIDE_TIMEOUT = 5.0


class App(BaseModel):
    """A running application."""

    name: Optional[str] = Field(description="Its name, as macOS shows it.")
    bundle_id: Optional[str] = Field(description="Its bundle identifier, such as 'com.apple.Safari'.")
    pid: int = Field(description="Its process ID.")
    path: Optional[str] = Field(description="The path of its .app.")
    is_active: bool = Field(description="Whether it's the app in front, which has the keyboard.")
    is_hidden: bool = Field(description="Whether it's hidden.")


class AppFound(BaseModel):
    """An app that was looked for."""

    app: Optional[App] = Field(description="The app. Null when there's none.")


class InstalledApp(BaseModel):
    """An app installed on this Mac."""

    name: str = Field(description="Its name.")
    bundle_id: Optional[str] = Field(description="Its bundle identifier.")
    version: Optional[str] = Field(description="Its version, as the app shows it.")
    path: str = Field(description="The path of its .app.")


class LoginItem(BaseModel):
    """An app, or a file, opened when the user logs in."""

    name: str = Field(description="Its name, as System Settings shows it.")
    path: Optional[str] = Field(description="Its path.")


class DefaultApp(BaseModel):
    """The app that opens something by default."""

    path: Optional[str] = Field(description="The path of the app. Null when no app opens it.")


class Installed(BaseModel):
    """An app that was installed."""

    path: str = Field(description="The path of the installed app.")


class Quarantine(BaseModel):
    """Whether macOS marked a file as downloaded from the internet."""

    quarantined: bool = Field(description="Whether it has the mark, which makes macOS check it before it first opens.")


class Unquarantined(BaseModel):
    """Files that lost the downloaded-from-the-internet mark."""

    files: int = Field(description="How many files had the mark.")


class Uninstalled(BaseModel):
    """What uninstalling an app moves to the Trash."""

    moved: bool = Field(description="Whether it was moved to the Trash. False for a dry run, which moves nothing.")
    paths: List[str] = Field(description="The app, first, and the files it left in the user's Library.")


def _app(app: "macos.apps.App") -> App:
    return App(
        name=app.name, bundle_id=app.bundle_id, pid=app.pid, path=app.path, is_active=app.is_active, is_hidden=app.is_hidden
    )


def _running(name: str) -> "macos.apps.App":
    app = macos.apps.get(name)
    if app is None:
        raise ToolError("{} isn't running.".format(name))
    return app


def list_running_apps(
    include_background: Annotated[
        bool,
        Field(description="True to add menu bar extras, agents and helpers to the regular apps, the ones with a Dock icon."),
    ] = False,
) -> List[App]:
    """List the running applications, with which one is in front and which are hidden."""
    return [_app(app) for app in macos.apps.running(include_background=include_background)]


def get_frontmost_app() -> AppFound:
    """Get the application in front: the one that has the keyboard, which the user is using."""
    app = macos.apps.frontmost()
    return AppFound(app=None if app is None else _app(app))


def get_running_app(name: AppName) -> AppFound:
    """
    Find a running application by its name, bundle identifier or path. The app is null when it isn't
    running. Names are matched in any case, in the system's language or the app's own.
    """
    app = macos.apps.get(name)
    return AppFound(app=None if app is None else _app(app))


def open_app(
    name: AppName,
    background: Annotated[bool, Field(description="True to open it without bringing it to the front.")] = False,
) -> App:
    """
    Open an application, or bring it to the front if it's already running, and return it. An app is a
    program, which runs with the user's access: open the one the user asked for, not a path taken from
    a web page, a file or a message.
    """
    return _app(macos.apps.open(name, background=background))


def activate_app(name: AppName) -> str:
    """Bring a running application to the front, which takes the keyboard from the app the user is in."""
    if not _running(name).activate():
        raise ToolError("{} didn't come to the front.".format(name))
    return "{} is in front.".format(name)


def set_app_hidden(
    name: AppName,
    hidden: Annotated[bool, Field(description="True to hide the app's windows, false to show them again.")],
) -> str:
    """Hide a running application's windows, like its Hide menu item, or show them again."""
    app = _running(name)
    # What macOS answers to the request doesn't tell: recent versions say no and then do it, a moment
    # later, and an app that's still opening drops it. So it's asked again until the app is as wanted.
    deadline = time.monotonic() + HIDE_TIMEOUT
    while app.is_hidden != hidden:
        if time.monotonic() >= deadline:
            raise ToolError("{} couldn't be {}.".format(name, "hidden" if hidden else "shown"))
        if hidden:
            app.hide()
        else:
            app.unhide()
        time.sleep(0.25)
    return "{} is {}.".format(name, "hidden" if hidden else "shown")


def quit_app(
    name: AppName,
    force: Annotated[
        bool,
        Field(
            description="False asks the app to quit, like its Quit menu item: it may ask to save changes, or refuse. "
            "True ends it at once, like Force Quit: unsaved work is lost."
        ),
    ] = False,
) -> str:
    """Quit a running application, and wait up to 10 seconds for it to be gone."""
    if not _running(name).quit(force=force, timeout=QUIT_TIMEOUT):
        raise ToolError(
            "{} is still running: it may be asking to save changes, or have refused to quit.".format(name)
        )
    return "{} quit.".format(name)


def list_installed_apps(
    search: Annotated[
        Optional[str],
        Field(description="Keep only the apps whose name has this text, in any case. All of them by default."),
    ] = None,
    limit: Annotated[int, Field(description="How many to return, at most.", ge=1, le=2000)] = 200,
) -> List[InstalledApp]:
    """List the applications installed on this Mac, by name, with their version and bundle identifier."""
    apps = macos.apps.installed()
    if search is not None:
        apps = [app for app in apps if search.casefold() in app.name.casefold()]
    return [
        InstalledApp(name=app.name, bundle_id=app.bundle_id, version=app.version, path=str(app.path))
        for app in apps[:limit]
    ]


def get_default_app(
    kind: Annotated[
        str,
        Field(
            description="A kind of file, as an extension ('pdf', '.png') or a type identifier ('public.plain-text'), "
            "or 'browser' for the default web browser.",
            min_length=1,
        ),
    ],
) -> DefaultApp:
    """Get the application that opens a kind of file by default, or the default web browser."""
    if kind.casefold() == "browser":
        return DefaultApp(path=macos.apps.default_browser())
    return DefaultApp(path=macos.apps.default_for(kind))


def set_default_app(kind: Kind, app: AppName) -> str:
    """
    Make an application open a kind of file by default, like Finder's Get Info › Open with › Change
    All. On recent versions of macOS the user is asked to confirm, which this waits for, up to a
    minute. The default web browser can't be set this way: macOS asks for it in System Settings.
    """
    macos.apps.set_default_for(kind, app)
    return "{} now opens {} files.".format(app, kind)


def install_app_from_disk_image(
    image: Annotated[str, Field(description="The path of the disk image (.dmg) that holds the app.", min_length=1)],
    replace: Annotated[
        bool,
        Field(description="True to replace an app of the same name already installed, which must not be running."),
    ] = False,
    app: Annotated[
        Optional[str],
        Field(description="Which app to install, by name, when the image holds several. The first by name otherwise."),
    ] = None,
    destination: Annotated[str, Field(description="The folder to install into.", min_length=1)] = "/Applications",
) -> Installed:
    """
    Install the application a disk image holds, as dragging it to Applications does: the image is
    mounted, the app copied and the image unmounted. Installers (.pkg) aren't run. Only install what
    the user asked for: an app is a program, and runs with the user's access once opened.
    """
    return Installed(path=macos.apps.install_from_dmg(image, destination=destination, replace=replace, app=app))


def uninstall_app(
    name: AppName,
    dry_run: Annotated[
        bool, Field(description="True to only list what would go to the Trash, without moving anything.")
    ] = False,
    include_name_matches: Annotated[
        bool,
        Field(
            description="True to also move the folders named after the app in Application Support, Caches and "
            "Logs. A name can be shared with another app: do a dry run first, and check them. They come last."
        ),
    ] = False,
) -> Uninstalled:
    """
    Uninstall an application: move it to the Trash, with the files it left in the user's Library
    (settings, caches, logs, saved state). The Trash's Put Back undoes it. The app must not be running,
    and the apps that come with macOS can't be uninstalled. Do a dry run first to see what would go.
    """
    paths = macos.apps.uninstall(name, dry_run=dry_run, include_name_matches=include_name_matches)
    return Uninstalled(moved=not dry_run, paths=[str(path) for path in paths])


def list_login_items() -> List[LoginItem]:
    """
    List the applications that open when the user logs in. Apps that register themselves as background
    items, with their own switch in System Settings, aren't listed.
    """
    return [LoginItem(name=item.name, path=item.path) for item in macos.apps.login_items()]


def add_login_item(app: AppName) -> LoginItem:
    """Open an application each time the user logs in. One that's already a login item isn't added twice."""
    item = macos.apps.add_login_item(app)
    return LoginItem(name=item.name, path=item.path)


def remove_login_item(
    app: Annotated[
        str,
        Field(
            description="The login item's name, as list_login_items shows it, or an app's name, bundle identifier "
            "or path.",
            min_length=1,
        ),
    ],
) -> str:
    """Stop opening an application when the user logs in."""
    if macos.apps.remove_login_item(app):
        return "{} no longer opens at login.".format(app)
    return "{} wasn't a login item.".format(app)


def check_quarantine(
    path: Annotated[str, Field(description="The path of a file or an app.", min_length=1)],
) -> Quarantine:
    """
    Check whether macOS marked a file or an app as downloaded from the internet. That mark is what
    makes macOS say an app "is damaged and can't be opened", or ask whether to open it.
    """
    return Quarantine(quarantined=macos.apps.is_quarantined(path))


def remove_quarantine(
    path: Annotated[str, Field(description="The path of a file, an app or a folder.", min_length=1)],
) -> Unquarantined:
    """
    Remove the downloaded-from-the-internet mark from a file and, for an app or a folder, everything
    in it. It skips the check macOS makes the first time something opens: do it only for what the
    user says they trust.
    """
    return Unquarantined(files=macos.apps.unquarantine(path))


def register(server: MCPServer) -> None:
    add_tool(server, list_running_apps, title="List the running apps", annotations=READ_ONLY)
    add_tool(server, get_frontmost_app, title="Get the app in front", annotations=READ_ONLY)
    add_tool(server, get_running_app, title="Find a running app", annotations=READ_ONLY)
    add_tool(server, list_installed_apps, title="List the installed apps", annotations=READ_ONLY)
    # Any .app can be given, and an app is a program: what it does once open can't be told beforehand.
    add_tool(server, open_app, title="Open an app", annotations=OPEN_ENDED)
    add_tool(server, activate_app, title="Bring an app to the front", annotations=REPLACING)
    add_tool(server, set_app_hidden, title="Hide or show an app", annotations=REPLACING)
    # An app that's quit may lose unsaved work.
    add_tool(server, quit_app, title="Quit an app", annotations=DESTRUCTIVE)
    add_tool(server, get_default_app, title="Get the default app for a kind of file", annotations=READ_ONLY)
    add_tool(server, set_default_app, title="Set the default app for a kind of file", annotations=REPLACING)
    # It can replace an app, and what it installs is a program.
    add_tool(server, install_app_from_disk_image, title="Install an app from a disk image", annotations=DESTRUCTIVE)
    add_tool(server, uninstall_app, title="Uninstall an app", annotations=DESTRUCTIVE)
    # The login items are read and changed through System Events, which macOS asks the user to allow.
    add_tool(server, list_login_items, title="List the login items", annotations=READ_ONLY, permission=AUTOMATION)
    add_tool(server, add_login_item, title="Open an app at login", annotations=ADDITIVE, permission=AUTOMATION)
    add_tool(server, remove_login_item, title="Stop opening an app at login", annotations=REPLACING, permission=AUTOMATION)
    add_tool(server, check_quarantine, title="Check the downloaded mark", annotations=READ_ONLY)
    # It takes away a check of macOS's.
    add_tool(server, remove_quarantine, title="Remove the downloaded mark", annotations=DESTRUCTIVE)
