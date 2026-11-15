"""Tools for the keyboard: typing and pressing keys, its layout, backlight, settings and shortcuts, from ``macos.keyboard``."""

import threading
from typing import Annotated, Any, Callable, Dict, List, Literal, Optional, Tuple

import anyio.from_thread
import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._permissions import ACCESSIBILITY, INPUT_MONITORING
from .._registry import LONGEST_WAIT, OPEN_ENDED, READ_ONLY, REPLACING, add_tool

Keys = Annotated[
    str,
    Field(
        description="A key or a shortcut: 'enter', 'a', 'cmd+c', 'cmd+shift+4'. Modifiers are cmd, shift, option, ctrl "
        "and fn, joined with +. Keys are characters, or names: enter, tab, space, delete (backspace), forward_delete, "
        "escape, left, right, up, down, home, end, page_up, page_down, f1 to f20...",
        min_length=1,
    ),
]
SystemShortcut = Literal[
    "spotlight",
    "finder_search",
    "previous_input_source",
    "next_input_source",
    "screenshot",
    "screenshot_to_clipboard",
    "screenshot_area",
    "screenshot_area_to_clipboard",
    "screenshot_toolbar",
    "mission_control",
    "application_windows",
    "show_desktop",
    "move_left_a_space",
    "move_right_a_space",
    "dock_hiding",
]


# pymacos reads the whole list of remappings, of an app's shortcuts or of macOS's shortcuts and writes it
# back for each change, and the tools run on worker threads: two changes at once would each write the
# list without the other's. They take turns, across every server of the process, as the Mac is one.
_SAVED = threading.Lock()


def _read_layout_on_main_thread() -> None:
    """
    Have the main thread read the keyboard layout in use, so that this worker can find its keys.

    macOS only hands a layout over on the main thread, and pymacos keeps what it read there for other
    threads: without it, a layout unlike a US one (AZERTY...) can't be pressed off the main thread, and
    keys watched are named by what they type. Only the read goes to the main thread: the press or the
    wait stays on the worker, so that the server keeps answering meanwhile.
    """
    try:
        anyio.from_thread.run_sync(macos.keyboard.layout)
    except RuntimeError:
        # Not one of the server's workers (a thread of the caller's own, or the main thread itself):
        # pymacos reads the layout there if it can, and says what to do if it can't.
        pass


class KeyboardStatus(BaseModel):
    """The keyboard as it is now."""

    caps_lock: bool = Field(description="Whether Caps Lock is on.")
    layout: str = Field(description="The keyboard layout in use, such as 'ABC' or 'French'.")
    layouts: List[str] = Field(
        description="The layouts enabled in the menu bar's input menu, which set_keyboard_layout takes."
    )
    backlight: Optional[int] = Field(
        description="The backlight's brightness, from 0 to 100. Null on a keyboard without one."
    )
    backlight_auto: Optional[bool] = Field(
        description="Whether the backlight follows the room's light. Null without a backlight."
    )
    backlight_timeout_seconds: Optional[float] = Field(
        description="How long without use before the backlight turns off. Null when it stays on, or without a backlight."
    )
    accessibility_permission: bool = Field(
        description="Whether keys and clicks may be sent: the Accessibility permission of the app that runs this server."
    )
    input_monitoring_permission: bool = Field(
        description="Whether keys and clicks may be listened to: the Input Monitoring permission of that app."
    )


class KeyboardSettings(BaseModel):
    """The settings of System Settings › Keyboard."""

    key_repeat_interval_seconds: float = Field(description="The time between the repeats of a held key.")
    key_repeat_delay_seconds: float = Field(description="The time before a held key starts repeating.")
    press_and_hold: bool = Field(description="Whether holding a key shows the accents menu instead of repeating it.")
    standard_function_keys: bool = Field(description="Whether F1, F2... act as function keys without holding Fn.")
    autocorrect: bool = Field(description="Whether spelling is corrected as you type.")
    smart_quotes: bool = Field(description="Whether typed quotes become curly ones.")
    smart_dashes: bool = Field(description="Whether a typed -- becomes a dash.")
    auto_capitalization: bool = Field(description="Whether sentences start with a capital as you type.")
    double_space_period: bool = Field(description="Whether two spaces type a period.")
    full_keyboard_access: bool = Field(description="Whether Tab moves between every control, not only text fields.")
    inline_predictions: bool = Field(description="Whether the end of words is suggested in gray as you type.")
    fn_key_action: Optional[str] = Field(
        description="What pressing Fn alone does: 'emoji', 'input_source', 'dictation'. Null for nothing."
    )
    remappings: Dict[str, str] = Field(description="The keys remapped, such as {'caps_lock': 'escape'}.")
    system_shortcuts: Dict[str, bool] = Field(
        description="Which of macOS's shortcuts are on, such as {'spotlight': true}."
    )


class KeyPress(BaseModel):
    """A key pressed."""

    key: str = Field(description="The key, such as 'a', 'enter' or 'f5'.")
    modifiers: List[str] = Field(description="The modifiers held with it: cmd, shift, option, ctrl, fn.")
    shortcut: str = Field(description="The key and its modifiers, as press_keys takes them: 'cmd+shift+k'.")
    text: str = Field(description="The text it typed. Empty for a key that types nothing.")
    repeat: bool = Field(description="Whether it's a repeat of a key held down.")


class KeyWait(BaseModel):
    """What was pressed while the keyboard was listened to."""

    key: Optional[KeyPress] = Field(description="The key. Null when the time ran out first.")


def get_keyboard_status() -> KeyboardStatus:
    """
    Get the keyboard as it is now: Caps Lock, the layout in use and the enabled ones, the backlight, and
    whether the permissions to send and to listen to keys are granted.
    """
    try:
        backlight: Optional[int] = round(macos.keyboard.brightness() * 100)
        auto: Optional[bool] = macos.keyboard.auto_brightness()
        timeout: Optional[float] = macos.keyboard.backlight_timeout()
    except macos.NotSupportedError:
        backlight, auto, timeout = None, None, None  # a keyboard without a backlight
    return KeyboardStatus(
        caps_lock=macos.keyboard.caps_lock(),
        layout=macos.keyboard.layout(),
        layouts=macos.keyboard.layouts(),
        backlight=backlight,
        backlight_auto=auto,
        backlight_timeout_seconds=timeout,
        accessibility_permission=macos.keyboard.has_permission(),
        input_monitoring_permission=macos.keyboard.has_listen_permission(),
    )


def press_keys(
    keys: Keys,
    times: Annotated[int, Field(description="How many times to press it.", ge=1, le=100)] = 1,
) -> str:
    """
    Press a key or a shortcut in the app in front, as if on the keyboard: 'cmd+c', 'enter', 'cmd+shift+4'.
    It does whatever the shortcut does in that app, sending, deleting or closing included: know what's
    in front first.
    """
    _read_layout_on_main_thread()
    macos.keyboard.press(keys, times=times)
    return "Pressed {}{}.".format(keys, "" if times == 1 else " {} times".format(times))


def type_text(
    text: Annotated[
        str, Field(description="The text to type. Any character works, accents and emoji included.", min_length=1)
    ],
    interval_seconds: Annotated[
        float, Field(description="A pause between characters, for apps that can't keep up.", ge=0, le=1)
    ] = 0.0,
) -> str:
    """
    Type text into the app in front, as if typed on the keyboard. A new line presses Enter and a tab
    presses Tab: in a chat box or a form, a new line sends or submits, so leave them out of text taken
    from elsewhere (a web page, a message).
    """
    macos.keyboard.type(text, interval=interval_seconds)
    return "Typed {} character{}.".format(len(text), "" if len(text) == 1 else "s")


def wait_for_key_press(
    timeout_seconds: Annotated[float, Field(description="How long to wait, in seconds.", gt=0, le=LONGEST_WAIT)] = 60.0,
) -> KeyWait:
    """
    Wait for the user to press a key, in any app, and say which: for a key the user is asked to press.
    The key still reaches the app in front. macOS hides the keys typed in password fields.
    """
    _read_layout_on_main_thread()
    keys = macos.keyboard.watch(timeout=timeout_seconds)
    try:
        pressed = next(iter(keys), None)
    finally:
        close = getattr(keys, "close", None)
        if close is not None:
            close()
    if pressed is None:
        return KeyWait(key=None)
    return KeyWait(
        key=KeyPress(
            key=pressed.key,
            modifiers=list(pressed.modifiers),
            shortcut=pressed.shortcut,
            text=pressed.text,
            repeat=pressed.repeat,
        )
    )


def set_keyboard_layout(
    name: Annotated[
        str,
        Field(
            description="The layout, as get_keyboard_status lists it ('ABC', 'French'), or a part of its name.",
            min_length=1,
        ),
    ],
) -> str:
    """Switch to one of the enabled keyboard layouts, like picking it in the input menu."""
    return "Switched to {}.".format(macos.keyboard.set_layout(name))


def set_keyboard_backlight(
    brightness: Annotated[
        Optional[int], Field(description="The brightness, from 0 (off) to 100.", ge=0, le=100)
    ] = None,
    auto: Annotated[Optional[bool], Field(description="True to follow the room's light, false not to.")] = None,
    timeout_seconds: Annotated[
        Optional[float],
        Field(description="Turn it off after this long without use, in seconds; 0 to keep it on.", ge=0),
    ] = None,
) -> str:
    """Set the keyboard backlight: its brightness, whether it follows the room's light, and when it turns off."""
    if brightness is None and auto is None and timeout_seconds is None:
        raise ValueError("no setting was given: say which one to change")
    changed: List[str] = []
    if auto is not None:
        macos.keyboard.set_auto_brightness(auto)
        changed.append("automatic brightness")
    if brightness is not None:
        macos.keyboard.set_brightness(brightness / 100)
        changed.append("brightness")
    if timeout_seconds is not None:
        macos.keyboard.set_backlight_timeout(timeout_seconds or None)
        changed.append("timeout")
    return "Changed: {}.".format(", ".join(changed))


def get_keyboard_settings() -> KeyboardSettings:
    """Get the keyboard's settings: key repeat, text corrections, function keys, Fn, the keys remapped and macOS's shortcuts."""
    interval, delay = macos.keyboard.key_repeat()
    return KeyboardSettings(
        key_repeat_interval_seconds=interval,
        key_repeat_delay_seconds=delay,
        press_and_hold=macos.keyboard.press_and_hold(),
        standard_function_keys=macos.keyboard.standard_function_keys(),
        autocorrect=macos.keyboard.autocorrect(),
        smart_quotes=macos.keyboard.smart_quotes(),
        smart_dashes=macos.keyboard.smart_dashes(),
        auto_capitalization=macos.keyboard.auto_capitalization(),
        double_space_period=macos.keyboard.double_space_period(),
        full_keyboard_access=macos.keyboard.full_keyboard_access(),
        inline_predictions=macos.keyboard.inline_predictions(),
        fn_key_action=macos.keyboard.fn_key_action(),
        remappings=macos.keyboard.remappings(),
        system_shortcuts=macos.keyboard.system_shortcuts(),
    )


def set_keyboard_settings(
    key_repeat_interval_seconds: Annotated[
        Optional[float],
        Field(description="The time between repeats of a held key. Takes effect at the next login.", gt=0, le=2),
    ] = None,
    key_repeat_delay_seconds: Annotated[
        Optional[float],
        Field(description="The time before a held key repeats. Takes effect at the next login.", gt=0, le=5),
    ] = None,
    press_and_hold: Annotated[
        Optional[bool], Field(description="True to show the accents menu when a key is held.")
    ] = None,
    standard_function_keys: Annotated[
        Optional[bool], Field(description="True for F1, F2... to act as function keys without Fn.")
    ] = None,
    autocorrect: Annotated[Optional[bool], Field(description="True to correct spelling as you type.")] = None,
    smart_quotes: Annotated[Optional[bool], Field(description="False to keep typed quotes straight.")] = None,
    smart_dashes: Annotated[Optional[bool], Field(description="False to keep a typed -- as it is.")] = None,
    auto_capitalization: Annotated[
        Optional[bool], Field(description="True to capitalize sentences as you type.")
    ] = None,
    double_space_period: Annotated[Optional[bool], Field(description="True for two spaces to type a period.")] = None,
    full_keyboard_access: Annotated[
        Optional[bool], Field(description="True for Tab to move between every control.")
    ] = None,
    inline_predictions: Annotated[
        Optional[bool], Field(description="True to suggest the end of words as you type.")
    ] = None,
    fn_key_action: Annotated[
        Optional[Literal["emoji", "input_source", "dictation", "nothing"]],
        Field(description="What pressing Fn alone does: 'emoji', 'input_source', 'dictation' or 'nothing'."),
    ] = None,
) -> str:
    """
    Change the keyboard's settings. Give only the settings to change: the others stay as they are. Most
    apps pick the text settings up when they're reopened.
    """
    setters: Tuple[Tuple[Any, Callable[[Any], Any], str], ...] = (
        (press_and_hold, macos.keyboard.set_press_and_hold, "press and hold"),
        (standard_function_keys, macos.keyboard.set_standard_function_keys, "function keys"),
        (autocorrect, macos.keyboard.set_autocorrect, "autocorrect"),
        (smart_quotes, macos.keyboard.set_smart_quotes, "smart quotes"),
        (smart_dashes, macos.keyboard.set_smart_dashes, "smart dashes"),
        (auto_capitalization, macos.keyboard.set_auto_capitalization, "auto capitalization"),
        (double_space_period, macos.keyboard.set_double_space_period, "double-space period"),
        (full_keyboard_access, macos.keyboard.set_full_keyboard_access, "full keyboard access"),
        (inline_predictions, macos.keyboard.set_inline_predictions, "inline predictions"),
        (
            fn_key_action,
            lambda action: macos.keyboard.set_fn_key_action(None if action == "nothing" else action),
            "Fn key",
        ),
    )
    given = [(value, setter, name) for value, setter, name in setters if value is not None]
    repeat = key_repeat_interval_seconds is not None or key_repeat_delay_seconds is not None
    if not given and not repeat:
        raise ValueError("no setting was given: say which one to change")
    names: List[str] = []
    with macos.settings.batch():
        if repeat:
            macos.keyboard.set_key_repeat(key_repeat_interval_seconds, delay=key_repeat_delay_seconds)
            names.append("key repeat")
        for value, setter, name in given:
            setter(value)
            names.append(name)
    return "Changed: {}.".format(", ".join(names))


def remap_key(
    key: Annotated[
        str,
        Field(
            description="The key to remap: a letter, a digit, f1 to f20, a modifier (cmd, right_cmd, option, right_option, "
            "ctrl, shift, fn), caps_lock, escape, enter, tab..., not punctuation.",
            min_length=1,
        ),
    ],
    to: Annotated[
        Optional[str], Field(description="The key it acts as, named the same way. Null to undo the remapping.")
    ],
) -> str:
    """
    Make a key act as another on every keyboard, such as Caps Lock as Escape, or undo it. It lasts until
    the Mac restarts.
    """
    with _SAVED:
        macos.keyboard.remap(key, to)
    return "{} acts as {}.".format(key, to) if to else "{} acts as itself again.".format(key)


def clear_key_remappings() -> str:
    """Undo every key remapping: each key acts as itself again."""
    with _SAVED:
        macos.keyboard.clear_remappings()
    return "Every key acts as itself again."


def get_app_shortcuts(
    app: Annotated[
        Optional[str], Field(description="The app, by name, bundle identifier or path. Every app's by default.")
    ] = None,
) -> Dict[str, str]:
    """Get the keyboard shortcuts given to menu items, as {menu item: keys}, set in System Settings › Keyboard › App Shortcuts."""
    return macos.keyboard.app_shortcuts(app)


def set_app_shortcut(
    app: Annotated[
        Optional[str], Field(description="The app, by name, bundle identifier or path. Null for every app.")
    ],
    menu_item: Annotated[
        str,
        Field(
            description="The menu item's title exactly as the menu shows it, in the system's language, the ellipsis (…) "
            "included. 'Menu > Item' when several menus have it.",
            min_length=1,
        ),
    ],
    keys: Annotated[Optional[str], Field(description="The shortcut, written as for press_keys. Null to remove it.")],
) -> str:
    """Give a menu item a keyboard shortcut, or take it away. Apps pick it up when they're reopened."""
    with _SAVED:
        macos.keyboard.set_app_shortcut(app, menu_item, keys)
    return "{} has {}.".format(menu_item, keys) if keys else "{} has no shortcut.".format(menu_item)


def set_system_shortcut(
    name: Annotated[SystemShortcut, Field(description="The shortcut of macOS, such as 'spotlight' (⌘Space).")],
    on: Annotated[bool, Field(description="True to turn it on, false off. Its keys stay as they are.")],
) -> str:
    """Turn one of macOS's own shortcuts on or off: to free ⌘Space for another launcher, say. Applies at once."""
    with _SAVED:
        macos.keyboard.set_system_shortcut(name, on)
    return "{} is {}.".format(name, "on" if on else "off")


def register(server: MCPServer) -> None:
    # The layouts are read and switched through what macOS only allows on the main thread.
    add_tool(server, get_keyboard_status, title="Get the keyboard's status", annotations=READ_ONLY, main_thread=True)
    add_tool(server, set_keyboard_layout, title="Switch the keyboard layout", annotations=REPLACING, main_thread=True)
    add_tool(server, get_keyboard_settings, title="Get the keyboard's settings", annotations=READ_ONLY)
    add_tool(server, get_app_shortcuts, title="Get the app shortcuts", annotations=READ_ONLY)
    # Keys pressed or typed do whatever they do in the app in front: anything, sending or deleting too.
    add_tool(server, press_keys, title="Press keys", annotations=OPEN_ENDED, permission=ACCESSIBILITY)
    add_tool(server, type_text, title="Type text", annotations=OPEN_ENDED, permission=ACCESSIBILITY)
    add_tool(
        server, wait_for_key_press, title="Wait for a key press", annotations=READ_ONLY, permission=INPUT_MONITORING
    )
    for setter, title in (
        (set_keyboard_backlight, "Set the keyboard backlight"),
        (set_keyboard_settings, "Change the keyboard's settings"),
        (remap_key, "Remap a key"),
        (clear_key_remappings, "Undo the key remappings"),
        (set_app_shortcut, "Set an app shortcut"),
        (set_system_shortcut, "Turn a macOS shortcut on or off"),
    ):
        add_tool(server, setter, title=title, annotations=REPLACING)
