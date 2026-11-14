"""Tools for the system appearance (Light and Dark mode, the accent color...), from ``macos.appearance``."""

from typing import Annotated, List, Literal, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._permissions import AUTOMATION
from .._registry import LONGEST_WAIT, READ_ONLY, REPLACING, add_tool

Mode = Literal["dark", "light"]
ScrollBars = Literal["automatic", "when_scrolling", "always"]


class Appearance(BaseModel):
    """The settings of System Settings › Appearance."""

    mode: str = Field(description="The mode in effect now: 'dark' or 'light'.")
    auto: bool = Field(description="Whether the mode is Auto: it switches between light and dark by the time of day.")
    accent_color: str = Field(
        description="The accent color, of buttons and selections, as hex ('#007aff'). The default blue when "
        "Multicolor is chosen."
    )
    menu_bar_hidden: bool = Field(
        description="Whether the menu bar hides until the pointer reaches the top of the screen."
    )
    scroll_bars: str = Field(
        description="When scroll bars show: 'automatic' (by the mouse or trackpad), 'when_scrolling' or 'always'."
    )
    font_smoothing: bool = Field(description="Whether text is drawn a little bolder (font smoothing).")


class ModeChange(BaseModel):
    """A switch between Light and Dark mode."""

    mode: str = Field(description="The mode the system switched to: 'dark' or 'light'.")


def get_appearance() -> Appearance:
    """
    Get the Mac's appearance settings: Light or Dark mode, whether it's on Auto, the accent color, and
    how the menu bar, scroll bars and fonts show.
    """
    return Appearance(
        mode=macos.appearance.mode(),
        auto=macos.appearance.is_auto(),
        accent_color=macos.appearance.accent_color(),
        menu_bar_hidden=macos.appearance.menu_bar_hidden(),
        scroll_bars=macos.appearance.scroll_bars(),
        font_smoothing=macos.appearance.font_smoothing(),
    )


def set_appearance(
    mode: Annotated[Optional[Mode], Field(description="Switch the whole system to 'dark' or 'light' mode.")] = None,
    auto: Annotated[
        Optional[bool],
        Field(
            description="True to switch between light and dark by the time of day (Auto), false to keep the "
            "current mode. macOS may apply it only at the next login."
        ),
    ] = None,
    accent_color: Annotated[
        Optional[str],
        Field(
            description="The color of buttons and selections, by name: multicolor (each app's own), graphite, "
            "red, orange, yellow, green, blue, purple or pink."
        ),
    ] = None,
    hide_menu_bar: Annotated[
        Optional[bool],
        Field(description="True to hide the menu bar until the pointer reaches the top of the screen, false to show it."),
    ] = None,
    scroll_bars: Annotated[
        Optional[ScrollBars], Field(description="When scroll bars show: 'automatic', 'when_scrolling' or 'always'.")
    ] = None,
    font_smoothing: Annotated[
        Optional[bool],
        Field(description="True to draw text a little bolder, false for thinner. Apps pick it up when reopened."),
    ] = None,
) -> str:
    """
    Change the Mac's appearance settings, like System Settings › Appearance. Give only the settings to
    change: the others stay as they are.
    """
    if all(setting is None for setting in (mode, auto, accent_color, hide_menu_bar, scroll_bars, font_smoothing)):
        raise ValueError("no setting was given: say which one to change")
    if accent_color is not None and accent_color not in macos.appearance.ACCENT_COLORS:
        # Checked before anything is changed, so a wrong name doesn't leave the settings half applied.
        raise ValueError(
            "accent_color must be one of {}, not {!r}".format(", ".join(macos.appearance.ACCENT_COLORS), accent_color)
        )

    changed: List[str] = []
    # The mode first: it's the one that may be refused, for a permission, before anything is changed.
    if mode is not None:
        macos.appearance.set_mode(mode)
        changed.append("mode")
    if auto is not None:
        macos.appearance.set_auto_mode(auto)
        changed.append("auto")
    if accent_color is not None:
        macos.appearance.set_accent_color(accent_color)
        changed.append("accent color")
    if hide_menu_bar is not None:
        macos.appearance.set_hide_menu_bar(hide_menu_bar)
        changed.append("menu bar")
    if scroll_bars is not None:
        macos.appearance.set_scroll_bars(scroll_bars)
        changed.append("scroll bars")
    if font_smoothing is not None:
        macos.appearance.set_font_smoothing(font_smoothing)
        changed.append("font smoothing")

    return "Changed: {}.".format(", ".join(changed))


def wait_for_appearance_change(
    timeout_seconds: Annotated[
        float,
        Field(description="How long to wait, in seconds, before giving up.", gt=0, le=LONGEST_WAIT),
    ] = 60.0,
) -> ModeChange:
    """
    Wait until the system switches between Light and Dark mode, by the user or by Auto, and return the
    new mode. Fails when it doesn't switch in time.
    """
    return ModeChange(mode=macos.appearance.wait_for_change(timeout=timeout_seconds))


def register(server: MCPServer) -> None:
    add_tool(server, get_appearance, title="Get the appearance settings", annotations=READ_ONLY)
    # Switching the mode goes through System Events, which macOS asks the user to allow, the first time.
    add_tool(server, set_appearance, title="Change the appearance settings", annotations=REPLACING, permission=AUTOMATION)
    add_tool(server, wait_for_appearance_change, title="Wait for Light or Dark mode to switch", annotations=READ_ONLY)
