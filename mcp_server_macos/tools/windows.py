"""
Tools for the windows of running apps: listing, focusing, moving, resizing, snapping, minimizing, full
screen, closing, capturing and tiling them, and the windows' settings, from ``macos.windows``.
"""

from typing import Annotated, Any, Callable, List, Literal, Optional, Tuple, Union

import macos
from mcp.server.mcpserver import Image, MCPServer
from pydantic import BaseModel, Field

from .._permissions import ACCESSIBILITY, SCREEN_RECORDING_AND_ACCESSIBILITY
from .._registry import ADDITIVE, DESTRUCTIVE, LONGEST_WAIT, READ_ONLY, REPLACING, add_tool
from .screen import Saved, look, on_screen

App = Annotated[
    Optional[str],
    Field(
        description="The window's app, by name, bundle identifier or path. With no app nor title, the window in front."
    ),
]
Title = Annotated[
    Optional[str],
    Field(description="A part of the window's title, in any case. The app's front window by default."),
]
DisplayNumber = Annotated[
    Optional[int], Field(description="The display, by its number in get_displays: 1 is the main one.", ge=1)
]
Layout = Literal[
    "left",
    "right",
    "top",
    "bottom",
    "top_left",
    "top_right",
    "bottom_left",
    "bottom_right",
    "left_third",
    "center_third",
    "right_third",
    "left_two_thirds",
    "right_two_thirds",
    "maximize",
    "center",
]
TitleBarAction = Literal["zoom", "fill", "minimize", "nothing"]


class Window(BaseModel):
    """A window of a running app. Positions and sizes are in points, from the top-left of the main display."""

    app: str = Field(description="Its app's name.")
    pid: int = Field(description="Its app's process ID.")
    title: str = Field(description="As its title bar shows it: '' for an untitled window.")
    x: float = Field(description="Its left edge.")
    y: float = Field(description="Its top edge.")
    width: float = Field(description="Its width, title bar included.")
    height: float = Field(description="Its height.")
    minimized: bool = Field(description="Whether it's minimized into the Dock.")
    fullscreen: bool = Field(description="Whether it's in full screen, in a Space of its own.")


class WindowFound(BaseModel):
    """A window, or none."""

    window: Optional[Window] = Field(description="The window. Null when there's none.")


class WindowRef(BaseModel):
    """Which window: its app, and a part of its title."""

    app: str = Field(description="Its app, by name, bundle identifier or path.", min_length=1)
    title: Optional[str] = Field(default=None, description="A part of its title. The app's front window by default.")


class WindowSettings(BaseModel):
    """How windows behave."""

    double_click_title_bar: str = Field(
        description="What a double click on a title bar does: 'zoom', 'fill' (the screen), 'minimize' or 'nothing'."
    )
    tiling: Optional[bool] = Field(
        description="Whether a window dragged to an edge of the screen tiles there. Null before macOS 15."
    )
    click_wallpaper_to_show_desktop: Optional[bool] = Field(
        description="Whether a click on the wallpaper moves the windows away. Null before macOS 14."
    )
    animations: bool = Field(description="Whether windows, sheets and panels open with an animation.")
    accessibility_permission: bool = Field(
        description="Whether the app running the server may control windows, which every window tool needs."
    )


def _described(window: Any) -> Window:
    x, y, width, height = window.frame
    return Window(
        app=window.app,
        pid=window.pid,
        title=window.title,
        x=x,
        y=y,
        width=width,
        height=height,
        minimized=window.minimized,
        fullscreen=window.fullscreen,
    )


def _window(app: Optional[str], title: Optional[str]) -> Any:
    """The window asked for: the app's front one with that title, or the window in front with neither."""
    if app is None and title is None:
        window = macos.windows.focused()
        if window is None:
            raise LookupError("the app in front has no window: name the app")
        return window
    found = macos.windows.list(app, title=title)
    if not found:
        raise LookupError(
            "no window{}{}: list_windows lists them".format(
                " of {}".format(app) if app else "", " titled like {!r}".format(title) if title else ""
            )
        )
    return found[0]


def _maybe(read: Callable[[], Any]) -> Any:
    try:
        return read()
    except macos.NotSupportedError:
        return None


def list_windows(app: App = None, title: Title = None) -> List[Window]:
    """
    List the windows of the running apps, or of one app, front to back within each app, minimized ones
    included. The app and the title are what the other window tools take to tell a window.
    """
    return [_described(window) for window in macos.windows.list(app, title=title)]


def get_front_window() -> WindowFound:
    """Get the window in front: the one keystrokes go to."""
    window = macos.windows.focused()
    return WindowFound(window=None if window is None else _described(window))


def wait_for_window(
    app: App = None,
    title: Title = None,
    timeout_seconds: Annotated[float, Field(description="How long to wait, in seconds.", gt=0, le=LONGEST_WAIT)] = 10.0,
) -> WindowFound:
    """Wait for a window to show up, such as a Save dialog or an app's first window after it's opened."""
    window = macos.windows.wait_for(app, title=title, timeout=timeout_seconds)
    return WindowFound(window=None if window is None else _described(window))


def focus_window(app: App = None, title: Title = None) -> Window:
    """Bring a window to the front, with its app, ready for keystrokes."""
    window = _window(app, title)
    window.focus()
    return _described(window)


def move_window(
    app: App = None,
    title: Title = None,
    x: Annotated[Optional[float], Field(description="Where its left edge goes, in points.")] = None,
    y: Annotated[Optional[float], Field(description="Where its top edge goes, in points.")] = None,
    width: Annotated[Optional[float], Field(description="Its new width, in points.", gt=0)] = None,
    height: Annotated[Optional[float], Field(description="Its new height, in points.", gt=0)] = None,
) -> Window:
    """Move a window, resize it, or both. Apps with a minimum size may stay larger."""
    if (x is None) != (y is None) or (width is None) != (height is None):
        raise ValueError("give x with y, and width with height")
    if x is None and width is None:
        raise ValueError("give where to move it (x, y), its size (width, height), or both")
    window = _window(app, title)
    if x is not None and y is not None and width is not None and height is not None:
        window.set_frame(x, y, width, height)
    elif x is not None and y is not None:
        window.move(x, y)
    elif width is not None and height is not None:
        window.resize(width, height)
    return _described(window)


def snap_window(
    layout: Annotated[
        Layout,
        Field(
            description="Where: a half ('left', 'top'...), a quarter ('top_left'...), a third ('left_third', "
            "'left_two_thirds'...), 'maximize', or 'center' to center it keeping its size."
        ),
    ],
    app: App = None,
    title: Title = None,
    display: DisplayNumber = None,
) -> Window:
    """Fit a window to part of a display, as Rectangle or macOS's own tiling do, leaving out the menu bar and the Dock."""
    window = _window(app, title)
    if layout == "center":
        if display is not None:
            raise ValueError("a window is centered on the display it's on: move it to another with a layout")
        window.center()
    else:
        window.snap(layout, display=display)
    return _described(window)


def set_window_state(
    app: App = None,
    title: Title = None,
    minimized: Annotated[
        Optional[bool], Field(description="True to minimize it into the Dock, false to bring it back.")
    ] = None,
    fullscreen: Annotated[Optional[bool], Field(description="True to enter full screen, false to leave it.")] = None,
) -> Window:
    """Minimize a window or bring it back, or make it full screen or not, as its yellow and green buttons do."""
    if minimized is None and fullscreen is None:
        raise ValueError("say what to change: minimized, fullscreen or both")
    window = _window(app, title)
    if minimized is False:
        window.restore()
    if fullscreen is not None:
        window.set_fullscreen(fullscreen)
    if minimized:
        window.minimize()
    return _described(window)


def close_window(app: App = None, title: Title = None) -> str:
    """
    Close a window, as its red button does. What's unsaved may be lost: most apps ask first, but not
    every app, and not a browser's tabs.
    """
    window = _window(app, title)
    closed = "{} of {}".format(repr(window.title) if window.title else "The untitled window", window.app)
    window.close()
    return "Closed {}.".format(closed)


def take_window_screenshot(
    app: App = None,
    title: Title = None,
    shadow: Annotated[bool, Field(description="True to keep the window's shadow.")] = False,
) -> List[Union[Image, str]]:
    """
    Look at one window, even when others cover it, as an image, with how its pixels map to the points
    that click and move_pointer take.
    """
    window = _window(app, title)
    where = window.frame
    return on_screen(look(lambda path: window.screenshot(path, shadow=shadow)), where)


def save_window_screenshot(
    path: Annotated[
        str,
        Field(
            description="Where to save it. The format follows the extension: .png, .jpg, .heic, .tiff, .gif or .pdf. "
            "A file already there is replaced.",
            min_length=1,
        ),
    ],
    app: App = None,
    title: Title = None,
    shadow: Annotated[bool, Field(description="True to keep the window's shadow.")] = False,
) -> Saved:
    """Save a screenshot of one window to a file, even when others cover it."""
    return Saved(path=str(_window(app, title).screenshot(path, shadow=shadow)))


def tile_windows(
    app: Annotated[Optional[str], Field(description="Only this app's windows. Every app's by default.")] = None,
    windows: Annotated[
        Optional[List[WindowRef]],
        Field(description="Only these windows, rather than every one on screen (or the app's).", min_length=1),
    ] = None,
    display: Annotated[
        Optional[int],
        Field(description="Gather them on this display, by its number. Each stays on its own by default.", ge=1),
    ] = None,
    columns: Annotated[
        Optional[int], Field(description="How many columns. As square as can be by default.", ge=1, le=12)
    ] = None,
    gap: Annotated[int, Field(description="The points between the windows, and around them.", ge=0, le=100)] = 0,
) -> List[Window]:
    """
    Arrange windows side by side in a grid, filling the display: every window on screen, an app's, or
    those given. Minimized and full-screen windows, and those of hidden apps, stay as they are.
    """
    if windows is not None:
        if app is not None:
            raise ValueError("give an app or windows, not both")
        chosen = [_window(window.app, window.title) for window in windows]
        macos.windows.tile(chosen, display=display, columns=columns, gap=gap)
        return [_described(window) for window in chosen]
    return [_described(window) for window in macos.windows.tile_all(app, display=display, columns=columns, gap=gap)]


def get_window_settings() -> WindowSettings:
    """Get how windows behave: a double click on a title bar, tiling at the edges, the wallpaper click, animations."""
    action = macos.windows.double_click_title_bar()
    return WindowSettings(
        double_click_title_bar=action or "nothing",
        tiling=_maybe(macos.windows.tiling),
        click_wallpaper_to_show_desktop=_maybe(macos.windows.click_wallpaper_to_show_desktop),
        animations=macos.windows.animations(),
        accessibility_permission=macos.windows.has_permission(),
    )


def set_window_settings(
    double_click_title_bar: Annotated[
        Optional[TitleBarAction],
        Field(
            description="What a double click on a title bar does: 'zoom', 'fill' the screen, 'minimize' or 'nothing'."
        ),
    ] = None,
    tiling: Annotated[
        Optional[bool], Field(description="False to let windows dragged to an edge go anywhere. macOS 15 and later.")
    ] = None,
    click_wallpaper_to_show_desktop: Annotated[
        Optional[bool],
        Field(description="False to move windows away on a wallpaper click only in Stage Manager. macOS 14 and later."),
    ] = None,
    animations: Annotated[
        Optional[bool], Field(description="False to show windows, sheets and panels at once, for a snappier Mac.")
    ] = None,
) -> str:
    """Change how windows behave. Give only the settings to change."""
    setters: Tuple[Tuple[Any, Callable[[Any], Any], str], ...] = (
        (
            double_click_title_bar,
            lambda action: macos.windows.set_double_click_title_bar(None if action == "nothing" else action),
            "title bar double click",
        ),
        (tiling, macos.windows.set_tiling, "tiling"),
        (
            click_wallpaper_to_show_desktop,
            macos.windows.set_click_wallpaper_to_show_desktop,
            "wallpaper click",
        ),
        (animations, macos.windows.set_animations, "animations"),
    )
    given = [(value, setter, name) for value, setter, name in setters if value is not None]
    if not given:
        raise ValueError("no setting was given: say which one to change")
    with macos.settings.batch():
        for value, setter, _ in given:
            setter(value)
    return "Changed: {}.".format(", ".join(name for _, _, name in given))


def register(server: MCPServer) -> None:
    # Windows are read and controlled through the Accessibility API, which needs its permission.
    for reader, title in (
        (list_windows, "List the windows"),
        (get_front_window, "Get the window in front"),
        (wait_for_window, "Wait for a window"),
    ):
        add_tool(server, reader, title=title, annotations=READ_ONLY, permission=ACCESSIBILITY)
    add_tool(server, get_window_settings, title="Get the window settings", annotations=READ_ONLY)
    # Capturing one window finds it with Accessibility, then captures it with Screen Recording.
    add_tool(
        server,
        take_window_screenshot,
        title="Take a screenshot of a window",
        annotations=READ_ONLY,
        permission=SCREEN_RECORDING_AND_ACCESSIBILITY,
    )
    add_tool(
        server,
        save_window_screenshot,
        title="Save a screenshot of a window",
        annotations=REPLACING,
        permission=SCREEN_RECORDING_AND_ACCESSIBILITY,
    )
    # Bringing a window to the front changes nothing in it, and doing it again leaves it there.
    add_tool(server, focus_window, title="Bring a window to the front", annotations=ADDITIVE, permission=ACCESSIBILITY)
    # These set where a window is, or how it shows: done again, they set the same.
    for setter, title in (
        (move_window, "Move or resize a window"),
        (snap_window, "Snap a window"),
        (set_window_state, "Minimize a window or make it full screen"),
        (tile_windows, "Tile windows"),
    ):
        add_tool(server, setter, title=title, annotations=REPLACING, permission=ACCESSIBILITY)
    add_tool(server, set_window_settings, title="Change the window settings", annotations=REPLACING)
    # A closed window may take what's unsaved in it, and a second call closes another window.
    add_tool(server, close_window, title="Close a window", annotations=DESTRUCTIVE, permission=ACCESSIBILITY)
