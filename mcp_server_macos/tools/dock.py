"""Tools for the Dock: its settings, the apps and folders kept in it, and the hot corners, from ``macos.dock``."""

from typing import Annotated, Any, Callable, Dict, List, Literal, Optional, Tuple, Union

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._registry import ADDITIVE, READ_ONLY, REPLACING, add_tool

AppName = Annotated[
    str,
    Field(description="The app: its name ('Safari'), its bundle identifier or the path of its .app.", min_length=1),
]
Index = Annotated[
    Optional[int],
    Field(
        description="Where to put it among the Dock's apps, counted as list_dock_items gives them: 0 is right after "
        "Finder, -1 before the last. At the end by default."
    ),
]
Corner = Literal["top_left", "top_right", "bottom_left", "bottom_right"]
Action = Literal[
    "mission_control",
    "app_windows",
    "desktop",
    "start_screensaver",
    "disable_screensaver",
    "display_sleep",
    "launchpad",
    "notification_center",
    "lock_screen",
    "quick_note",
]
Seconds = Annotated[float, Field(ge=0, le=10)]


class DockApp(BaseModel):
    """An app kept in the Dock."""

    name: str = Field(description="Its name.")
    path: Optional[str] = Field(description="The path of its .app.")
    bundle_id: Optional[str] = Field(description="Its bundle identifier.")


class DockFolder(BaseModel):
    """A folder kept in the Dock, next to the Trash."""

    name: str = Field(description="Its name.")
    path: Optional[str] = Field(description="Its path.")
    view: str = Field(description="How it opens: 'automatic', 'fan', 'grid' or 'list'.")
    sort: str = Field(
        description="The order of its items: 'name', 'date_added', 'date_modified', 'date_created' or 'kind'."
    )
    display: str = Field(description="Its icon: a 'stack' of its items, or the 'folder'.")


class DockItems(BaseModel):
    """What's kept in the Dock."""

    apps: List[DockApp] = Field(
        description="The apps kept in it, in order. Finder, always first, isn't listed, nor are the running apps not "
        "kept, nor spacers."
    )
    folders: List[DockFolder] = Field(description="The folders kept in it, next to the Trash, in order.")


class HotCorner(BaseModel):
    """What moving the pointer into a corner of the screen does."""

    action: Optional[str] = Field(
        description="What it does, such as 'mission_control' or 'lock_screen'. Null for nothing."
    )
    modifier: Optional[str] = Field(description="The keys it waits for to be held down, such as 'cmd'. Null for none.")


class DockSettings(BaseModel):
    """The settings of the Dock, Mission Control and the hot corners."""

    autohide: bool = Field(description="Whether the Dock hides until the pointer reaches the edge of the screen.")
    size: int = Field(description="The size of its icons, in points, from 16 to 128.")
    position: str = Field(description="Where it is: 'left', 'bottom' or 'right'.")
    magnification: Optional[int] = Field(
        description="The size icons grow to under the pointer, in points. Null when they don't."
    )
    autohide_delay_seconds: float = Field(description="How long a hidden Dock waits before showing.")
    autohide_duration_seconds: Optional[float] = Field(
        description="How long a hidden Dock takes to slide in. Null for macOS's own."
    )
    show_recents: bool = Field(description="Whether it shows recent apps not kept in it, in their own section.")
    minimize_effect: str = Field(description="How windows minimize into it: 'genie', 'scale' or 'suck'.")
    show_indicators: bool = Field(description="Whether it shows a dot under the open apps.")
    minimize_to_app: bool = Field(description="Whether minimized windows go into their app's icon.")
    dim_hidden_apps: bool = Field(description="Whether the icons of hidden apps are translucent.")
    only_open_apps: bool = Field(description="Whether it shows only the open apps, like a taskbar.")
    launch_animation: bool = Field(description="Whether an app's icon bounces while it opens.")
    auto_rearrange_spaces: bool = Field(
        description="Whether Mission Control reorders the spaces by the most recently used."
    )
    separate_spaces_per_display: bool = Field(description="Whether each display has its own spaces and menu bar.")
    group_windows_by_app: bool = Field(description="Whether Mission Control groups the windows by app.")
    switch_to_space_with_app: bool = Field(
        description="Whether switching to an app moves to a space where it has windows open."
    )
    hot_corners: Dict[str, HotCorner] = Field(
        description="What each corner does, by name: top_left, top_right, bottom_left, bottom_right."
    )


def get_dock_settings() -> DockSettings:
    """
    Get the settings of the Dock (size, position, hiding, magnification, effects), of Mission Control
    and its spaces, and what each hot corner does. What's kept in the Dock is list_dock_items's.
    """
    actions, modifiers = macos.dock.hot_corners(), macos.dock.hot_corner_modifiers()
    return DockSettings(
        autohide=macos.dock.autohide(),
        size=macos.dock.size(),
        position=macos.dock.position(),
        magnification=macos.dock.magnification(),
        autohide_delay_seconds=macos.dock.autohide_delay(),
        autohide_duration_seconds=macos.dock.autohide_duration(),
        show_recents=macos.dock.show_recents(),
        minimize_effect=macos.dock.minimize_effect(),
        show_indicators=macos.dock.show_indicators(),
        minimize_to_app=macos.dock.minimize_to_app(),
        dim_hidden_apps=macos.dock.dim_hidden_apps(),
        only_open_apps=macos.dock.only_open_apps(),
        launch_animation=macos.dock.launch_animation(),
        auto_rearrange_spaces=macos.dock.auto_rearrange_spaces(),
        separate_spaces_per_display=macos.dock.separate_spaces_per_display(),
        group_windows_by_app=macos.dock.group_windows_by_app(),
        switch_to_space_with_app=macos.dock.switch_to_space_with_app(),
        hot_corners={
            corner: HotCorner(action=action, modifier=modifiers.get(corner)) for corner, action in actions.items()
        },
    )


def set_dock_settings(
    autohide: Annotated[
        Optional[bool], Field(description="True to hide the Dock until the pointer reaches the edge.")
    ] = None,
    size: Annotated[Optional[int], Field(description="The size of its icons, in points.", ge=16, le=128)] = None,
    position: Annotated[Optional[Literal["left", "bottom", "right"]], Field(description="Where it goes.")] = None,
    magnification: Annotated[
        Optional[Union[Annotated[int, Field(ge=16, le=128)], Literal["off"]]],
        Field(description="The size icons grow to under the pointer, from 16 to 128 points, or 'off'."),
    ] = None,
    autohide_delay_seconds: Annotated[
        Optional[Seconds], Field(description="How long a hidden Dock waits before showing: 0 shows it at once.")
    ] = None,
    autohide_duration_seconds: Annotated[
        Optional[Union[Seconds, Literal["default"]]],
        Field(
            description="How long a hidden Dock takes to slide in: 0 for no animation, or 'default' for macOS's own."
        ),
    ] = None,
    show_recents: Annotated[Optional[bool], Field(description="True to show recent apps in their own section.")] = None,
    minimize_effect: Annotated[
        Optional[Literal["genie", "scale", "suck"]],
        Field(description="How windows minimize: 'genie', 'scale' or 'suck'."),
    ] = None,
    show_indicators: Annotated[Optional[bool], Field(description="True to show a dot under the open apps.")] = None,
    minimize_to_app: Annotated[
        Optional[bool], Field(description="True to minimize windows into their app's icon.")
    ] = None,
    dim_hidden_apps: Annotated[
        Optional[bool], Field(description="True to make the icons of hidden apps translucent.")
    ] = None,
    only_open_apps: Annotated[
        Optional[bool], Field(description="True to show only the open apps. The apps kept aren't lost.")
    ] = None,
    launch_animation: Annotated[
        Optional[bool], Field(description="True to bounce an app's icon while it opens.")
    ] = None,
    auto_rearrange_spaces: Annotated[
        Optional[bool], Field(description="True to let Mission Control reorder the spaces by use.")
    ] = None,
    separate_spaces_per_display: Annotated[
        Optional[bool], Field(description="True to give each display its own spaces. Takes effect at the next login.")
    ] = None,
    group_windows_by_app: Annotated[
        Optional[bool], Field(description="True to group windows by app in Mission Control.")
    ] = None,
    switch_to_space_with_app: Annotated[
        Optional[bool], Field(description="True to move to a space where an app has windows when switching to it.")
    ] = None,
) -> str:
    """
    Change the settings of the Dock and Mission Control, like System Settings › Desktop & Dock. Give only
    the settings to change: the others stay as they are. The Dock restarts once, at the end, and
    disappears for a second.
    """
    setters: Tuple[Tuple[Any, Callable[[Any], Any], str], ...] = (
        (autohide, macos.dock.set_autohide, "autohide"),
        (size, macos.dock.set_size, "size"),
        (position, macos.dock.set_position, "position"),
        (magnification, lambda value: macos.dock.set_magnification(None if value == "off" else value), "magnification"),
        (autohide_delay_seconds, macos.dock.set_autohide_delay, "autohide delay"),
        (
            autohide_duration_seconds,
            lambda value: macos.dock.set_autohide_duration(None if value == "default" else value),
            "autohide duration",
        ),
        (show_recents, macos.dock.set_show_recents, "recent apps"),
        (minimize_effect, macos.dock.set_minimize_effect, "minimize effect"),
        (show_indicators, macos.dock.set_show_indicators, "indicators"),
        (minimize_to_app, macos.dock.set_minimize_to_app, "minimize to app"),
        (dim_hidden_apps, macos.dock.set_dim_hidden_apps, "dimmed hidden apps"),
        (only_open_apps, macos.dock.set_only_open_apps, "only open apps"),
        (launch_animation, macos.dock.set_launch_animation, "launch animation"),
        (auto_rearrange_spaces, macos.dock.set_auto_rearrange_spaces, "rearranged spaces"),
        (separate_spaces_per_display, macos.dock.set_separate_spaces_per_display, "spaces per display"),
        (group_windows_by_app, macos.dock.set_group_windows_by_app, "windows grouped by app"),
        (switch_to_space_with_app, macos.dock.set_switch_to_space_with_app, "switching to an app's space"),
    )
    given = [(value, setter, name) for value, setter, name in setters if value is not None]
    if not given:
        raise ValueError("no setting was given: say which one to change")
    # One restart of the Dock at the end, rather than one per setting.
    with macos.settings.batch():
        for value, setter, _ in given:
            setter(value)
    return "Changed: {}.".format(", ".join(name for _, _, name in given))


def set_hot_corner(
    corner: Annotated[
        Corner, Field(description="The corner: 'top_left', 'top_right', 'bottom_left' or 'bottom_right'.")
    ],
    action: Annotated[
        Optional[Action],
        Field(
            description="What moving the pointer there does: mission_control, app_windows, desktop, start_screensaver, "
            "disable_screensaver, display_sleep, launchpad, notification_center, lock_screen or quick_note. Null for nothing."
        ),
    ],
    modifier: Annotated[
        Optional[str],
        Field(
            description="Keys to hold down for it to fire, so it doesn't by accident: 'cmd', 'option', 'cmd+shift'..."
        ),
    ] = None,
) -> str:
    """Make moving the pointer into a corner of the screen do something, like System Settings › Desktop & Dock › Hot Corners."""
    macos.dock.set_hot_corner(corner, action, modifier=modifier)
    return "The {} corner {}.".format(corner.replace("_", " "), "does {}".format(action) if action else "does nothing")


def list_dock_items() -> DockItems:
    """List the apps and the folders kept in the Dock, in order."""
    return DockItems(
        apps=[
            DockApp(name=app.name, path=None if app.path is None else str(app.path), bundle_id=app.bundle_id)
            for app in macos.dock.apps()
        ],
        folders=[
            DockFolder(
                name=folder.name,
                path=None if folder.path is None else str(folder.path),
                view=folder.view,
                sort=folder.sort,
                display=folder.display,
            )
            for folder in macos.dock.folders()
        ],
    )


def add_app_to_dock(app: AppName, index: Index = None) -> DockApp:
    """
    Keep an app in the Dock. One kept already isn't added twice, and what the Dock kept at the app's path
    as something else (a folder tile) is taken out. The Dock restarts.
    """
    added = macos.dock.add_app(app, index=index)
    return DockApp(name=added.name, path=None if added.path is None else str(added.path), bundle_id=added.bundle_id)


def remove_app_from_dock(app: AppName) -> str:
    """Take an app out of the Dock. It stays installed. The Dock restarts."""
    if macos.dock.remove_app(app):
        return "{} is out of the Dock.".format(app)
    return "{} wasn't in the Dock.".format(app)


def add_folder_to_dock(
    folder: Annotated[str, Field(description="The folder's path, such as '~/Downloads'.", min_length=1)],
    view: Annotated[
        Literal["automatic", "fan", "grid", "list"],
        Field(description="How it opens: 'automatic', 'fan', 'grid' or 'list'."),
    ] = "automatic",
    sort: Annotated[
        Literal["name", "date_added", "date_modified", "date_created", "kind"],
        Field(description="The order of its items."),
    ] = "date_added",
    display: Annotated[
        Literal["stack", "folder"], Field(description="Its icon: a 'stack' of its items, or the 'folder'.")
    ] = "stack",
) -> DockFolder:
    """Keep a folder in the Dock, next to the Trash. One kept already is updated. The Dock restarts."""
    added = macos.dock.add_folder(folder, view=view, sort=sort, display=display)
    return DockFolder(
        name=added.name,
        path=None if added.path is None else str(added.path),
        view=added.view,
        sort=added.sort,
        display=added.display,
    )


def remove_folder_from_dock(folder: Annotated[str, Field(description="The folder's path.", min_length=1)]) -> str:
    """Take a folder out of the Dock. The folder itself stays. The Dock restarts."""
    if macos.dock.remove_folder(folder):
        return "{} is out of the Dock.".format(folder)
    return "{} wasn't in the Dock.".format(folder)


def add_dock_spacer(
    index: Index = None,
    small: Annotated[bool, Field(description="True for a narrower space.")] = False,
) -> str:
    """Add a blank space between the Dock's apps, to group them. The Dock restarts."""
    macos.dock.add_spacer(index=index, small=small)
    return "Spacer added."


def remove_dock_spacers() -> str:
    """Take every blank space out of the Dock's apps. The Dock restarts."""
    count = macos.dock.remove_spacers()
    return "{} spacer{} removed.".format(count, "" if count == 1 else "s")


def restart_dock() -> str:
    """Restart the Dock, so it reads its settings again: when it shows something stale. It disappears for a second."""
    macos.dock.restart()
    return "The Dock restarted."


def register(server: MCPServer) -> None:
    add_tool(server, get_dock_settings, title="Get the Dock's settings", annotations=READ_ONLY)
    add_tool(server, list_dock_items, title="List what's in the Dock", annotations=READ_ONLY)
    # These set something to a value: doing it again changes nothing more.
    for setter, title in (
        (set_dock_settings, "Change the Dock's settings"),
        (set_hot_corner, "Set a hot corner"),
        (remove_app_from_dock, "Take an app out of the Dock"),
        (remove_folder_from_dock, "Take a folder out of the Dock"),
        (remove_dock_spacers, "Remove the Dock's spacers"),
        (restart_dock, "Restart the Dock"),
        # Keeping a folder kept already updates it: how it opened and sorted is replaced.
        (add_folder_to_dock, "Keep a folder in the Dock"),
        # Keeping an app takes out what the Dock kept at its path as something else, a folder tile say.
        (add_app_to_dock, "Keep an app in the Dock"),
    ):
        add_tool(server, setter, title=title, annotations=REPLACING)
    # These add to the Dock: a spacer added again is another one.
    for adder, title in ((add_dock_spacer, "Add a spacer to the Dock"),):
        add_tool(server, adder, title=title, annotations=ADDITIVE)
