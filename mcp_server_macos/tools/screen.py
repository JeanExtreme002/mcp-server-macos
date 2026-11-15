"""
Tools for the screen: screenshots and recordings, text found on it, the displays and their resolution,
brightness, wallpaper and Night Shift, the screen saver and the lock, from ``macos.screen``.
"""

import pathlib
import tempfile
from typing import Annotated, Any, Callable, Dict, List, Literal, Optional, Tuple, TypeVar, Union

import macos
from mcp.server.mcpserver import Image, MCPServer
from pydantic import BaseModel, Field

from .. import _permissions
from .._permissions import MICROPHONE, SCREEN_RECORDING
from .._registry import DESTRUCTIVE, LONGEST_WAIT, READ_ONLY, REPLACING, add_tool

T = TypeVar("T")

DisplayNumber = Annotated[
    int, Field(description="The display, by its number in get_displays: 1 is the main one, with the menu bar.", ge=1)
]
OneDisplay = Annotated[
    Optional[int],
    Field(description="The display, by its number in get_displays: 1 is the main one, the default.", ge=1),
]
Languages = Annotated[
    Optional[List[str]],
    Field(
        description="The languages to read the screen in, most likely first, such as ['pt-BR']. Detected by default."
    ),
]
Output = Annotated[str, Field(description="Where to save it. A file already there is replaced.", min_length=1)]

# The longest side of a screenshot sent to the model: larger ones are scaled down, as the model would do
# anyway, which keeps them under the size a client accepts. A saved screenshot keeps every pixel.
_LARGEST_SIDE = 1568


class Region(BaseModel):
    """A part of the screen, in points from the top-left corner of the main display."""

    x: int = Field(description="Its left edge.")
    y: int = Field(description="Its top edge.")
    width: int = Field(description="Its width.", gt=0)
    height: int = Field(description="Its height.", gt=0)


RegionArgument = Annotated[
    Optional[Region],
    Field(description="Only this part of the screen, in points. The whole display by default."),
]


class TextFound(BaseModel):
    """A text on the screen, and where it is, in points from the top-left corner of the main display."""

    text: str = Field(description="The text, as read on the screen.")
    x: int = Field(description="The left edge of its box.")
    y: int = Field(description="The top edge of its box.")
    width: int = Field(description="Its box's width.")
    height: int = Field(description="Its box's height.")
    center_x: float = Field(description="The middle of its box, from the left: where to click it.")
    center_y: float = Field(description="The middle of its box, from the top.")


class TextWait(BaseModel):
    """What showed up on the screen while it was watched."""

    found: Optional[TextFound] = Field(
        description="The text, the first from the top. Null when the time ran out first."
    )


class ScreenColor(BaseModel):
    """The color of a point on the screen."""

    color: str = Field(description="As '#rrggbb'.")


class Saved(BaseModel):
    """A file that was written."""

    path: str = Field(description="The path of the file.")


class Display(BaseModel):
    """A connected display. Sizes and positions are in points, which a Retina display draws with more pixels."""

    number: int = Field(description="The number other tools take for it: 1 is the main one, with the menu bar.")
    name: Optional[str] = Field(description="Its name, such as 'Built-in Retina Display'. Null when macOS gives none.")
    x: int = Field(description="Its left edge, from the main display's left.")
    y: int = Field(description="Its top edge, from the main display's top.")
    width: int = Field(description="Its width.")
    height: int = Field(description="Its height.")
    pixel_width: int = Field(description="Its width in pixels.")
    pixel_height: int = Field(description="Its height in pixels.")
    scale: float = Field(description="Pixels per point: 2 on a Retina display.")
    refresh_rate: Optional[float] = Field(description="Its refresh rate, in hertz. Null when macOS gives none.")
    main: bool = Field(description="Whether it's the main one, with the menu bar and the Dock.")
    built_in: bool = Field(description="Whether it's built into the Mac, as a MacBook's.")
    asleep: bool = Field(description="Whether it's asleep, turned off to save energy.")
    brightness: Optional[int] = Field(description="Its brightness, from 0 to 100. Null when macOS can't read it.")
    wallpaper: Optional[str] = Field(
        description="The picture on its desktop. Null for a solid color, or a dynamic wallpaper that isn't a file."
    )


class Displays(BaseModel):
    """The connected displays."""

    displays: List[Display] = Field(description="The displays, the main one first.")
    mirrored: bool = Field(description="Whether some display shows the same picture as another.")


class DisplayMode(BaseModel):
    """A resolution a display can use."""

    width: int = Field(description="Its width, in points.")
    height: int = Field(description="Its height, in points.")
    pixel_width: int = Field(description="Its width in pixels.")
    pixel_height: int = Field(description="Its height in pixels.")
    refresh_rate: float = Field(description="Its refresh rate, in hertz.")
    hidpi: bool = Field(description="Whether it's a sharp Retina mode, drawn with more pixels than points.")


class DisplayModes(BaseModel):
    """The resolution a display uses, and those it can."""

    current: DisplayMode = Field(description="The one it uses now.")
    available: List[DisplayMode] = Field(description="Those it can use, largest first.")


class NightShiftHours(BaseModel):
    """The hours Night Shift is on."""

    start: str = Field(description="When it turns on, as 'HH:MM' (24 hours).", pattern=r"^\d{1,2}:\d{2}$")
    end: str = Field(description="When it turns off, as 'HH:MM'.", pattern=r"^\d{1,2}:\d{2}$")


class DisplaySettings(BaseModel):
    """Night Shift, True Tone, the screen saver and the lock."""

    night_shift: Optional[bool] = Field(description="Whether Night Shift is on now. Null on a Mac without it.")
    night_shift_schedule: Union[Literal["never", "sunset"], NightShiftHours, None] = Field(
        description="When it turns on by itself: 'never', 'sunset' (to sunrise) or between two times. Null without it."
    )
    night_shift_strength: Optional[float] = Field(description="How warm it makes the display, from 0 to 1.")
    true_tone: Optional[bool] = Field(description="Whether True Tone is on. Null on a Mac without it.")
    screensaver_delay_minutes: Optional[float] = Field(
        description="The minutes without use before the screen saver starts. Null when it never does."
    )
    locked: bool = Field(description="Whether the screen is locked.")
    screen_recording_permission: bool = Field(
        description="Whether the app running the server may capture the screen, which screenshots and reading need."
    )


ScreenshotFormat = Literal["png", "jpg", "heic", "tiff", "gif", "pdf", "bmp"]
ScreenshotTarget = Literal["file", "clipboard", "preview", "mail", "messages"]


class ScreenshotSettings(BaseModel):
    """How the screenshot shortcuts (⌘⇧3, ⌘⇧4, ⌘⇧5) save."""

    folder: str = Field(description="Where they save screenshots: the Desktop unless changed.")
    format: str = Field(description="The format they save in: 'png' unless changed.")
    shadow: bool = Field(description="Whether a screenshot of a window keeps its shadow.")
    thumbnail: bool = Field(description="Whether a thumbnail shows in the corner, to edit or drag, before it's saved.")
    name: Optional[str] = Field(description="What the files' names start with. Null for macOS's own ('Screenshot').")
    target: str = Field(description="Where they go: 'file', 'clipboard', 'preview', 'mail' or 'messages'.")


def _maybe(read: Callable[[], T]) -> Optional[T]:
    """What ``read`` returns, or None on a Mac or a display without it."""
    try:
        return read()
    except macos.NotSupportedError:
        return None


def _display(number: int) -> Any:
    """The display of pymacos with this number: its position in displays(), from 1, as screenshots take it."""
    displays = macos.screen.displays()
    if number > len(displays):
        raise ValueError("there's no display {}: {} connected".format(number, len(displays)))
    return displays[number - 1]


def _where(region: Optional[Region], display: Optional[int]) -> Dict[str, Any]:
    """
    Where to capture, as pymacos's screenshot, recording and reading take it: the region, or the display's
    number, checked to be connected before anything is asked of macOS (a permission, a capture).
    """
    if region is not None:
        return {"region": (region.x, region.y, region.width, region.height)}
    _display(display or 1)
    return {"display": display or 1}


def _region(region: Optional[Region]) -> Optional[Tuple[int, int, int, int]]:
    return None if region is None else (region.x, region.y, region.width, region.height)


def _found(match: Any) -> TextFound:
    return TextFound(
        text=match.text,
        x=match.x,
        y=match.y,
        width=match.width,
        height=match.height,
        center_x=match.x + match.width / 2,
        center_y=match.y + match.height / 2,
    )


def _mode(mode: Any) -> DisplayMode:
    return DisplayMode(
        width=mode.width,
        height=mode.height,
        pixel_width=mode.pixel_width,
        pixel_height=mode.pixel_height,
        refresh_rate=mode.refresh_rate,
        hidpi=mode.pixel_width > mode.width,
    )


def take_screenshot(
    region: RegionArgument = None,
    display: OneDisplay = None,
    cursor: Annotated[bool, Field(description="True to show the mouse pointer.")] = False,
) -> List[Union[Image, str]]:
    """
    Look at the screen: a screenshot of a display, or of part of it, as an image, with how its pixels
    map to the points that click, move_pointer and the regions take. To keep it as a file, use
    save_screenshot.
    """
    where = _region(region)
    if where is None:
        shown = _display(display or 1)
        where = (shown.x, shown.y, shown.width, shown.height)
        capture: Dict[str, Any] = {"display": display or 1}
    else:
        capture = {"region": where}
    with tempfile.TemporaryDirectory(prefix="mcp-server-macos-") as folder:
        taken = macos.screen.screenshot(pathlib.Path(folder) / "screen.png", cursor=cursor, **capture)
        info = macos.image.info(taken)
        width, height = info.width, info.height
        if max(width, height) > _LARGEST_SIDE:
            scale = _LARGEST_SIDE / max(width, height)
            width, height = max(1, round(width * scale)), max(1, round(height * scale))
            taken = macos.image.resize(taken, pathlib.Path(folder) / "screen.jpg", width=width, height=height)
        else:
            taken = macos.image.convert(taken, pathlib.Path(folder) / "screen.jpg")
        # The size of what's sent, as resize fits the picture within those bounds by its own rounding:
        # a pixel off would shift the points worked out from the picture.
        sent = macos.image.info(taken)
        width, height = sent.width, sent.height
        image = Image(data=taken.read_bytes(), format="jpeg")
    x, y, points_wide, points_high = where
    return [
        image,
        "The image is {}×{} pixels and shows the screen from ({}, {}), {}×{} points: the pixel (px, py) is the "
        "point ({} + px × {:.4g}, {} + py × {:.4g}).".format(
            width, height, x, y, points_wide, points_high, x, points_wide / width, y, points_high / height
        ),
    ]


def save_screenshot(
    path: Annotated[
        str,
        Field(
            description="Where to save it. The format follows the extension: .png, .jpg, .heic, .tiff, .gif or .pdf. "
            "A file already there is replaced.",
            min_length=1,
        ),
    ],
    region: RegionArgument = None,
    display: OneDisplay = None,
    cursor: Annotated[bool, Field(description="True to show the mouse pointer.")] = False,
) -> Saved:
    """Save a screenshot of a display, or of part of it, to a file, with every pixel."""
    capture: Dict[str, Any] = _where(region, display)
    return Saved(path=str(macos.screen.screenshot(path, cursor=cursor, **capture)))


def record_screen(
    path: Annotated[
        str, Field(description="Where to save the video, a .mov. A file already there is replaced.", min_length=1)
    ],
    seconds: Annotated[float, Field(description="How long to record. Whole seconds.", ge=1, le=LONGEST_WAIT)],
    region: RegionArgument = None,
    display: OneDisplay = None,
    audio: Annotated[bool, Field(description="True to record the microphone too.")] = False,
    clicks: Annotated[bool, Field(description="True to show the mouse clicks.")] = False,
) -> Saved:
    """Record the screen, or part of it, into a video. It returns when the recording ends."""
    capture: Dict[str, Any] = _where(region, display)
    if audio:
        # The tool needs Screen Recording, and the microphone only with sound: asked for here, with its
        # own instructions, rather than as Screen Recording when it's the one missing.
        _permissions.require(MICROPHONE, macos.audio.has_permission)
    return Saved(path=str(macos.screen.record(path, seconds, audio=audio, clicks=clicks, **capture)))


def find_text_on_screen(
    text: Annotated[str, Field(description="The text to look for, in any case.", min_length=1)],
    region: RegionArgument = None,
    display: OneDisplay = None,
    languages: Languages = None,
) -> List[TextFound]:
    """
    Find a text on the screen, in any app and in images too, read as Live Text reads it: where each
    match is, from the top. Empty when it isn't there.
    """
    where: Dict[str, Any] = _where(region, display)
    return [_found(match) for match in macos.screen.find_text(text, languages=languages, **where)]


def wait_for_text_on_screen(
    text: Annotated[str, Field(description="The text to wait for, in any case.", min_length=1)],
    timeout_seconds: Annotated[float, Field(description="How long to wait, in seconds.", gt=0, le=LONGEST_WAIT)] = 30.0,
    region: RegionArgument = None,
    display: OneDisplay = None,
    languages: Languages = None,
) -> TextWait:
    """Wait for a text to show up on the screen: a page loaded, a message received, a task done."""
    where: Dict[str, Any] = _where(region, display)
    match = macos.screen.wait_for_text(text, timeout=timeout_seconds, languages=languages, **where)
    return TextWait(found=None if match is None else _found(match))


def get_screen_color(
    x: Annotated[float, Field(description="The point's x, in points from the left of the main display.")],
    y: Annotated[float, Field(description="The point's y, in points from the top of the main display.")],
) -> ScreenColor:
    """Get the color of a point on the screen: to check a status light, or whether a button turned green."""
    return ScreenColor(color=macos.screen.color_at(x, y))


def get_displays() -> Displays:
    """List the connected displays: their size and place, resolution, brightness, wallpaper, and whether they're asleep."""
    found = []
    for number, display in enumerate(macos.screen.displays(), start=1):
        brightness = _maybe(lambda: macos.screen.brightness(display))
        wallpaper = macos.screen.wallpaper(display)
        found.append(
            Display(
                number=number,
                name=display.name,
                x=display.x,
                y=display.y,
                width=display.width,
                height=display.height,
                pixel_width=display.pixel_width,
                pixel_height=display.pixel_height,
                scale=display.scale,
                refresh_rate=display.refresh_rate,
                main=display.is_main,
                built_in=display.is_builtin,
                asleep=macos.screen.is_asleep(display),
                brightness=None if brightness is None else round(brightness * 100),
                wallpaper=None if wallpaper is None else str(wallpaper),
            )
        )
    return Displays(displays=found, mirrored=macos.screen.mirrored())


def get_display_modes(display: OneDisplay = None) -> DisplayModes:
    """Get the resolution a display uses, and those it can use, for set_display_mode."""
    shown = _display(display or 1)
    return DisplayModes(
        current=_mode(macos.screen.display_mode(shown)),
        available=[_mode(mode) for mode in macos.screen.display_modes(shown)],
    )


def set_display_mode(
    width: Annotated[int, Field(description="The width, in points: one of get_display_modes.", gt=0)],
    height: Annotated[int, Field(description="The height, in points.", gt=0)],
    refresh_rate: Annotated[
        Optional[float], Field(description="The refresh rate, in hertz: the closest one. The highest by default.", gt=0)
    ] = None,
    hidpi: Annotated[
        Optional[bool], Field(description="True for the sharp Retina mode, false for the other. Retina if there's one.")
    ] = None,
    display: OneDisplay = None,
) -> DisplayMode:
    """
    Change a display's resolution, as System Settings › Displays does, and kept after a restart. More
    points show more at once, smaller. Read get_display_modes first, to go back to it.
    """
    mode = macos.screen.set_display_mode(
        width, height, refresh_rate=refresh_rate, hidpi=hidpi, display=_display(display or 1)
    )
    return _mode(mode)


def set_main_display(display: DisplayNumber) -> str:
    """Make a display the main one, with the menu bar and the Dock. The displays' numbers change with it."""
    macos.screen.set_main_display(_display(display))
    return "Display {} is the main one now: it's number 1.".format(display)


def mirror_display(
    display: DisplayNumber,
    of: Annotated[
        Optional[int], Field(description="The display it shows the picture of. The main one by default.", ge=1)
    ] = None,
) -> str:
    """
    Make a display show the same picture as another, as Mirror Displays does: for a projector or a TV.
    It leaves the list of get_displays then, and the displays after it move up a number.
    """
    macos.screen.mirror(_display(display), None if of is None else _display(of))
    return "Display {} mirrors display {}.".format(display, of or 1)


def stop_mirroring() -> str:
    """Give every display its own picture again, extending the desktop across them."""
    macos.screen.stop_mirroring()
    return "Every display has its own picture."


def set_display_brightness(
    brightness: Annotated[int, Field(description="From 0 (darkest, not off) to 100.", ge=0, le=100)],
    display: OneDisplay = None,
) -> str:
    """Set a display's brightness, as the slider in Control Center does."""
    macos.screen.set_brightness(brightness / 100, display_id=_display(display or 1))
    return "The brightness is {}.".format(brightness)


def set_wallpaper(
    path: Annotated[
        str,
        Field(description="The picture: JPEG, PNG, HEIC... macOS keeps using the file: leave it there.", min_length=1),
    ],
    display: Annotated[
        Optional[int], Field(description="Only this display, by its number. Every display by default.", ge=1)
    ] = None,
) -> str:
    """Set the desktop picture, on every display or on one."""
    macos.screen.set_wallpaper(path, display_id=None if display is None else _display(display))
    return "The wallpaper is {}.".format(path)


def get_display_settings() -> DisplaySettings:
    """Get Night Shift, True Tone, the screen saver's delay, whether the screen is locked, and the Screen Recording permission."""
    shown: Union[Literal["never", "sunset"], NightShiftHours, None]
    try:
        schedule = macos.screen.night_shift_schedule()
    except macos.NotSupportedError:
        shown = None  # no Night Shift on this Mac
    else:
        if isinstance(schedule, tuple):
            start, end = schedule
            shown = NightShiftHours(start=start.strftime("%H:%M"), end=end.strftime("%H:%M"))
        else:
            shown = "sunset" if schedule == "sunset" else "never"  # pymacos says never with None
    return DisplaySettings(
        night_shift=_maybe(macos.screen.night_shift),
        night_shift_schedule=shown,
        night_shift_strength=_maybe(macos.screen.night_shift_strength),
        true_tone=_maybe(macos.screen.true_tone),
        screensaver_delay_minutes=macos.screen.screensaver_delay(),
        locked=macos.screen.is_locked(),
        screen_recording_permission=macos.screen.has_permission(),
    )


def set_display_settings(
    night_shift: Annotated[Optional[bool], Field(description="True to turn Night Shift on now, false off.")] = None,
    night_shift_schedule: Annotated[
        Union[Literal["never", "sunset"], NightShiftHours, None],
        Field(
            description="When Night Shift turns on by itself: 'never', 'sunset' (to sunrise, needs Location Services) "
            "or {'start': '22:00', 'end': '07:00'}."
        ),
    ] = None,
    night_shift_strength: Annotated[
        Optional[float], Field(description="How warm Night Shift makes the display, from 0 to 1.", ge=0, le=1)
    ] = None,
    true_tone: Annotated[Optional[bool], Field(description="True to turn True Tone on, false off.")] = None,
    screensaver_delay_minutes: Annotated[
        Optional[float],
        Field(description="Start the screen saver after this many minutes without use. 0 for never.", ge=0, le=1440),
    ] = None,
) -> str:
    """Change Night Shift, True Tone and the screen saver's delay. Give only the settings to change."""
    schedule: Any = night_shift_schedule
    if isinstance(night_shift_schedule, NightShiftHours):
        schedule = (night_shift_schedule.start, night_shift_schedule.end)
    elif night_shift_schedule == "never":
        schedule = None
    setters: Tuple[Tuple[Any, Callable[[Any], Any], str], ...] = (
        (night_shift_schedule, lambda _: macos.screen.set_night_shift_schedule(schedule), "Night Shift schedule"),
        (night_shift, macos.screen.set_night_shift, "Night Shift"),
        (night_shift_strength, macos.screen.set_night_shift_strength, "Night Shift strength"),
        (true_tone, macos.screen.set_true_tone, "True Tone"),
        (
            screensaver_delay_minutes,
            lambda minutes: macos.screen.set_screensaver_delay(minutes or None),
            "screen saver delay",
        ),
    )
    given = [(value, setter, name) for value, setter, name in setters if value is not None]
    if not given:
        raise ValueError("no setting was given: say which one to change")
    for value, setter, _ in given:
        setter(value)
    return "Changed: {}.".format(", ".join(name for _, _, name in given))


def get_screenshot_settings() -> ScreenshotSettings:
    """Get how the screenshot shortcuts (⌘⇧3, ⌘⇧4, ⌘⇧5) save: the folder, the format, the file names..."""
    return ScreenshotSettings(
        folder=str(macos.screen.screenshot_folder()),
        format=macos.screen.screenshot_format(),
        shadow=macos.screen.screenshot_shadow(),
        thumbnail=macos.screen.screenshot_thumbnail(),
        name=macos.screen.screenshot_name(),
        target=macos.screen.screenshot_target(),
    )


def set_screenshot_settings(
    folder: Annotated[Optional[str], Field(description="Save them in this folder, which must exist.")] = None,
    format: Annotated[Optional[ScreenshotFormat], Field(description="Save them in this format.")] = None,
    shadow: Annotated[
        Optional[bool], Field(description="False to leave a window's shadow out of a screenshot of it.")
    ] = None,
    thumbnail: Annotated[
        Optional[bool], Field(description="False to save at once, without the thumbnail in the corner.")
    ] = None,
    name: Annotated[
        Optional[str],
        Field(
            description="Start the files' names with this, such as 'Capture', without / or :. '' for macOS's own.",
            # As pymacos takes it ('' aside, which is macOS's own name): checked here, before any setting
            # is written, as nothing is written back when one is refused.
            pattern=r"^(?:|[^/:]*[^/:\s][^/:]*)$",
        ),
    ] = None,
    target: Annotated[
        Optional[ScreenshotTarget],
        Field(description="Send them to a 'file', the 'clipboard', or open them in 'preview', 'mail' or 'messages'."),
    ] = None,
) -> str:
    """Change how the screenshot shortcuts save, as the Options menu of ⌘⇧5 does. Give only the settings to change."""
    # The folder goes first: it's the one setting that can be refused (a folder that isn't there), and
    # nothing is written back when one is, so it must be refused before any other setting is changed.
    setters: Tuple[Tuple[Any, Callable[[Any], Any], str], ...] = (
        (folder, macos.screen.set_screenshot_folder, "folder"),
        (format, macos.screen.set_screenshot_format, "format"),
        (shadow, macos.screen.set_screenshot_shadow, "shadow"),
        (thumbnail, macos.screen.set_screenshot_thumbnail, "thumbnail"),
        (name, lambda name: macos.screen.set_screenshot_name(name or None), "name"),
        (target, macos.screen.set_screenshot_target, "target"),
    )
    given = [(value, setter, setting) for value, setter, setting in setters if value is not None]
    if not given:
        raise ValueError("no setting was given: say which one to change")
    with macos.settings.batch():
        for value, setter, _ in given:
            setter(value)
    return "Changed: {}.".format(", ".join(setting for _, _, setting in given))


def start_screensaver() -> str:
    """Start the screen saver now, as a hot corner does."""
    macos.screen.start_screensaver()
    return "The screen saver is on."


def lock_screen() -> str:
    """Lock the screen now, as ⌃⌘Q does: the user's password unlocks it. What's running keeps running."""
    macos.screen.lock()
    return "The screen is locked."


def register(server: MCPServer) -> None:
    # What's on the screen is read by capturing it, which needs Screen Recording.
    for reader, title in (
        (take_screenshot, "Take a screenshot"),
        (find_text_on_screen, "Find text on the screen"),
        (wait_for_text_on_screen, "Wait for text on the screen"),
        (get_screen_color, "Get a color on the screen"),
    ):
        add_tool(server, reader, title=title, annotations=READ_ONLY, permission=SCREEN_RECORDING)
    for getter, title in (
        (get_displays, "List the displays"),
        (get_display_modes, "Get a display's resolutions"),
        (get_display_settings, "Get the display settings"),
        (get_screenshot_settings, "Get the screenshot settings"),
    ):
        add_tool(server, getter, title=title, annotations=READ_ONLY)
    # These write a file made from scratch: done again, they write the same one again.
    add_tool(server, save_screenshot, title="Save a screenshot", annotations=REPLACING, permission=SCREEN_RECORDING)
    add_tool(server, record_screen, title="Record the screen", annotations=REPLACING, permission=SCREEN_RECORDING)
    # These set something to a value: done again, they set the same. Locking and the screen saver leave
    # things as they were once the user is back, as turning the display off does.
    for setter, title in (
        (set_display_mode, "Change a display's resolution"),
        (stop_mirroring, "Stop mirroring displays"),
        (set_display_brightness, "Set a display's brightness"),
        (set_wallpaper, "Set the wallpaper"),
        (set_display_settings, "Change the display settings"),
        (set_screenshot_settings, "Change the screenshot settings"),
        (start_screensaver, "Start the screen saver"),
        (lock_screen, "Lock the screen"),
    ):
        add_tool(server, setter, title=title, annotations=REPLACING)
    # Displays are told by their number, which these change. The main one is number 1: the same call made
    # again makes the other display the main one, back as it was. A display that mirrors another leaves
    # the list (only the one it shows the picture of is in it), and the next ones move up: the same call
    # made again mirrors another display. Not to retry, then.
    add_tool(server, set_main_display, title="Choose the main display", annotations=DESTRUCTIVE)
    add_tool(server, mirror_display, title="Mirror a display", annotations=DESTRUCTIVE)
