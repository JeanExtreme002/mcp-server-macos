"""Tools for the mouse: the pointer, clicking, dragging and scrolling, and the mouse's settings, from ``macos.mouse``."""

import contextlib
from typing import Annotated, Iterator, List, Literal, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._permissions import ACCESSIBILITY, INPUT_MONITORING, SCREEN_RECORDING_AND_ACCESSIBILITY
from .._registry import ADDITIVE, LONGEST_WAIT, OPEN_ENDED, READ_ONLY, REPLACING, add_tool

X = Annotated[float, Field(description="The x position, in points from the left of the main display.")]
Y = Annotated[float, Field(description="The y position, in points from the top of the main display.")]
Button = Annotated[Literal["left", "right", "middle"], Field(description="The button: 'left', 'right' or 'middle'.")]
Count = Annotated[int, Field(description="How many clicks: 2 for a double click.", ge=1, le=3)]
Holding = Annotated[
    Optional[List[str]],
    Field(
        description="Keys to hold down meanwhile, for a Shift-click, a Cmd-click or an Option-drag: ['shift'], ['cmd', 'option']."
    ),
]


class Pointer(BaseModel):
    """Where the pointer is."""

    x: float = Field(description="Its x position, in points from the left of the main display.")
    y: float = Field(description="Its y position, in points from the top of the main display.")


class MouseSettings(BaseModel):
    """The pointer's position, and the mouse's settings."""

    pointer: Pointer = Field(description="Where the pointer is.")
    tracking_speed: float = Field(description="The pointer speed with a mouse, from 0 (slowest) to 1 (fastest).")
    scroll_speed: float = Field(description="How fast the wheel scrolls: 0.3125 by default, higher is faster.")
    double_click_speed_seconds: float = Field(
        description="The most time between two clicks that still make a double click."
    )
    acceleration: bool = Field(description="Whether the pointer goes farther the faster the mouse moves.")


class Click(BaseModel):
    """A mouse click."""

    x: float = Field(description="Where, in points from the left of the main display.")
    y: float = Field(description="Where, in points from the top of the main display.")
    button: str = Field(description="'left', 'right' or 'middle'.")
    count: int = Field(description="1 for a click, 2 for a double click...")


class ClickWait(BaseModel):
    """What was clicked while the mouse was listened to."""

    click: Optional[Click] = Field(description="The click. Null when the time ran out first.")


class TextClicked(BaseModel):
    """The text that was clicked, where it shows on the screen."""

    text: str = Field(description="The text, as read on the screen.")
    x: float = Field(description="Where it was clicked, in points from the left.")
    y: float = Field(description="Where it was clicked, in points from the top.")


@contextlib.contextmanager
def _holding(keys: Optional[List[str]]) -> Iterator[None]:
    if keys:
        with macos.keyboard.hold(*keys):
            yield
    else:
        yield


def get_mouse_settings() -> MouseSettings:
    """
    Get where the pointer is, and the mouse's settings: the pointer speed, the scroll speed, the double
    click and the acceleration.
    """
    x, y = macos.mouse.position()
    return MouseSettings(
        pointer=Pointer(x=x, y=y),
        tracking_speed=macos.mouse.tracking_speed(),
        scroll_speed=macos.mouse.scroll_speed(),
        double_click_speed_seconds=macos.mouse.double_click_speed(),
        acceleration=macos.mouse.acceleration(),
    )


def move_pointer(
    x: X,
    y: Y,
    duration_seconds: Annotated[
        float, Field(description="Glide there over this long, rather than jump.", ge=0, le=10)
    ] = 0.0,
) -> str:
    """Move the pointer, as a real mouse would: apps see hover effects and tooltips."""
    macos.mouse.move(x, y, duration=duration_seconds)
    return "The pointer is at ({:g}, {:g}).".format(x, y)


def click(
    x: Annotated[
        Optional[float],
        Field(description="Where to click, from the left of the main display. Where the pointer is by default."),
    ] = None,
    y: Annotated[
        Optional[float],
        Field(description="Where to click, from the top of the main display. Where the pointer is by default."),
    ] = None,
    button: Button = "left",
    count: Count = 1,
    holding: Holding = None,
) -> str:
    """
    Click somewhere on the screen, as the user would. It does whatever the click does there, a button
    that sends, deletes or buys included: know what's under it first, with a screenshot.
    """
    if (x is None) != (y is None):
        raise ValueError("give both x and y, or neither to click where the pointer is")
    with _holding(holding):
        macos.mouse.click(x, y, button=button, count=count)
    where = "where the pointer is" if x is None else "at ({:g}, {:g})".format(x, y or 0)
    return "Clicked {}.".format(where)


def click_text(
    text: Annotated[
        str, Field(description="The text to click, as it shows on the screen: a button's label, a link.", min_length=1)
    ],
    timeout_seconds: Annotated[
        Optional[float], Field(description="Wait up to this long for it to show up, in seconds.", gt=0, le=LONGEST_WAIT)
    ] = None,
    button: Button = "left",
    count: Count = 1,
    languages: Annotated[
        Optional[List[str]], Field(description="The languages to read the screen in, such as ['pt-BR'].")
    ] = None,
) -> TextClicked:
    """
    Click a text where it shows on the screen, read as Live Text reads it, in any case: the first match
    from the top. It does whatever the click does there. Fails when the text isn't on the screen.
    """
    found = macos.mouse.click_text(text, timeout=timeout_seconds, button=button, count=count, languages=languages)
    return TextClicked(text=found.text, x=found.x + found.width / 2, y=found.y + found.height / 2)


def drag(
    to_x: Annotated[float, Field(description="Where to drop, from the left of the main display.")],
    to_y: Annotated[float, Field(description="Where to drop, from the top of the main display.")],
    from_x: Annotated[
        Optional[float], Field(description="Where to start, from the left. Where the pointer is by default.")
    ] = None,
    from_y: Annotated[
        Optional[float], Field(description="Where to start, from the top. Where the pointer is by default.")
    ] = None,
    button: Button = "left",
    duration_seconds: Annotated[float, Field(description="How long the drag takes.", gt=0, le=10)] = 0.3,
    holding: Holding = None,
) -> str:
    """Drag from one place to another, with a button held: to move a window, select text, or drop a file somewhere."""
    if (from_x is None) != (from_y is None):
        raise ValueError("give both from_x and from_y, or neither to start where the pointer is")
    with _holding(holding):
        if from_x is not None and from_y is not None:
            macos.mouse.move(from_x, from_y)
        macos.mouse.drag(to_x, to_y, button=button, duration=duration_seconds)
    return "Dragged to ({:g}, {:g}).".format(to_x, to_y)


def scroll(
    lines: Annotated[
        int, Field(description="How far: positive scrolls down (or right), negative up (or left).", ge=-10000, le=10000)
    ],
    horizontal: Annotated[bool, Field(description="True to scroll sideways.")] = False,
    holding: Holding = None,
) -> str:
    """Scroll what's under the pointer, as a mouse wheel would. Holding cmd zooms in many apps."""
    with _holding(holding):
        macos.mouse.scroll(lines, horizontal=horizontal)
    return "Scrolled {} line{}.".format(lines, "" if abs(lines) == 1 else "s")


def wait_for_click(
    timeout_seconds: Annotated[float, Field(description="How long to wait, in seconds.", gt=0, le=LONGEST_WAIT)] = 60.0,
) -> ClickWait:
    """Wait for the user to click, in any app, and say where: to have them point at something. The click still reaches the app."""
    clicks = macos.mouse.watch(timeout=timeout_seconds)
    try:
        clicked = next(iter(clicks), None)
    finally:
        close = getattr(clicks, "close", None)
        if close is not None:
            close()
    if clicked is None:
        return ClickWait(click=None)
    return ClickWait(click=Click(x=clicked.x, y=clicked.y, button=clicked.button, count=clicked.count))


def set_mouse_settings(
    tracking_speed: Annotated[
        Optional[float],
        Field(description="The pointer speed, from 0 to 1. Takes effect at the next login.", ge=0, le=1),
    ] = None,
    scroll_speed: Annotated[
        Optional[float],
        Field(description="The wheel's speed: 0.3125 by default. Takes effect at the next login.", ge=0, le=10),
    ] = None,
    double_click_speed_seconds: Annotated[
        Optional[float], Field(description="The most time between the clicks of a double click.", gt=0, le=5)
    ] = None,
    acceleration: Annotated[
        Optional[bool], Field(description="False for the pointer to move in proportion to the mouse.")
    ] = None,
) -> str:
    """Change the mouse's settings. Give only the settings to change: the others stay as they are."""
    changed: List[str] = []
    if tracking_speed is not None:
        macos.mouse.set_tracking_speed(tracking_speed)
        changed.append("tracking speed")
    if scroll_speed is not None:
        macos.mouse.set_scroll_speed(scroll_speed)
        changed.append("scroll speed")
    if double_click_speed_seconds is not None:
        macos.mouse.set_double_click_speed(double_click_speed_seconds)
        changed.append("double click speed")
    if acceleration is not None:
        macos.mouse.set_acceleration(acceleration)
        changed.append("acceleration")
    if not changed:
        raise ValueError("no setting was given: say which one to change")
    return "Changed: {}.".format(", ".join(changed))


def register(server: MCPServer) -> None:
    add_tool(server, get_mouse_settings, title="Get the pointer and the mouse's settings", annotations=READ_ONLY)
    add_tool(server, set_mouse_settings, title="Change the mouse's settings", annotations=REPLACING)
    # Moving the pointer only hovers.
    add_tool(server, move_pointer, title="Move the pointer", annotations=ADDITIVE, permission=ACCESSIBILITY)
    # Scrolling twice goes farther, and changes nothing but what's shown.
    add_tool(server, scroll, title="Scroll", annotations=ADDITIVE, permission=ACCESSIBILITY)
    # A click or a drag does whatever it does where it lands: anything.
    add_tool(server, click, title="Click", annotations=OPEN_ENDED, permission=ACCESSIBILITY)
    add_tool(server, drag, title="Drag", annotations=OPEN_ENDED, permission=ACCESSIBILITY)
    add_tool(
        server,
        click_text,
        title="Click a text on the screen",
        annotations=OPEN_ENDED,
        permission=SCREEN_RECORDING_AND_ACCESSIBILITY,
    )
    add_tool(server, wait_for_click, title="Wait for a click", annotations=READ_ONLY, permission=INPUT_MONITORING)
