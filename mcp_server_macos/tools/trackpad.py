"""Tools for the trackpad: clicking, scrolling, the pointer speed and the gestures, from ``macos.trackpad``."""

from typing import Annotated, Dict, Literal, Optional, Union

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._registry import READ_ONLY, REPLACING, add_tool

# The gestures made with three or four fingers: the others are on or off.
_FINGERS = ("swipe_between_full_screen_apps", "mission_control")


class TrackpadSettings(BaseModel):
    """The settings of System Settings › Trackpad."""

    tap_to_click: bool = Field(description="Whether a tap clicks, without pressing.")
    natural_scrolling: bool = Field(description="Whether content follows the fingers, for the trackpad and mice alike.")
    tracking_speed: float = Field(description="The pointer speed, from 0 (slowest) to 1 (fastest).")
    three_finger_drag: bool = Field(description="Whether dragging with three fingers moves windows and selects text.")
    secondary_click: Optional[str] = Field(
        description="How it right-clicks: 'two_fingers', 'bottom_right' or 'bottom_left' (a corner). Null when it doesn't."
    )
    click_pressure: str = Field(description="How firmly it must be pressed to click: 'light', 'medium' or 'firm'.")
    gestures: Dict[str, Union[bool, int]] = Field(
        description="Which gestures are on, by name: those made with three or four fingers give the number, or false."
    )


def get_trackpad_settings() -> TrackpadSettings:
    """
    Get the trackpad's settings: tap to click, the scroll direction, the pointer speed, the right click,
    the pressure and the gestures.
    """
    return TrackpadSettings(
        tap_to_click=macos.trackpad.tap_to_click(),
        natural_scrolling=macos.trackpad.natural_scrolling(),
        tracking_speed=macos.trackpad.tracking_speed(),
        three_finger_drag=macos.trackpad.three_finger_drag(),
        secondary_click=macos.trackpad.secondary_click(),
        click_pressure=macos.trackpad.click_pressure(),
        gestures=macos.trackpad.gestures(),
    )


def set_trackpad_settings(
    tap_to_click: Annotated[Optional[bool], Field(description="True for a tap to click, false to press only.")] = None,
    natural_scrolling: Annotated[
        Optional[bool],
        Field(description="True for content to follow the fingers, false for the classic way. Mice too."),
    ] = None,
    tracking_speed: Annotated[
        Optional[float],
        Field(description="The pointer speed, from 0 to 1. Takes effect at the next login.", ge=0, le=1),
    ] = None,
    three_finger_drag: Annotated[
        Optional[bool],
        Field(
            description="True to drag with three fingers. Three-finger swipes then clash with it: move them to four."
        ),
    ] = None,
    secondary_click: Annotated[
        Optional[Literal["two_fingers", "bottom_right", "bottom_left", "off"]],
        Field(description="Right-click with 'two_fingers', in the 'bottom_right' or 'bottom_left' corner, or 'off'."),
    ] = None,
    click_pressure: Annotated[
        Optional[Literal["light", "medium", "firm"]], Field(description="How firmly to press to click.")
    ] = None,
    gestures: Annotated[
        Optional[Dict[str, Union[bool, Literal[3, 4]]]],
        Field(
            description="Gestures to turn on (true) or off (false), by name: swipe_between_pages, pinch_to_zoom, rotate, "
            "smart_zoom, notification_center, swipe_between_full_screen_apps, mission_control, app_expose, launchpad, "
            "show_desktop. The full-screen swipe and Mission Control also take 3 or 4, the fingers."
        ),
    ] = None,
) -> str:
    """
    Change the trackpad's settings, like System Settings › Trackpad. Give only the settings to change: the
    others stay as they are. Most apply at once; the pointer speed at the next login.
    """
    settings = (
        tap_to_click,
        natural_scrolling,
        tracking_speed,
        three_finger_drag,
        secondary_click,
        click_pressure,
        gestures,
    )
    if all(setting is None for setting in settings):
        raise ValueError("no setting was given: say which one to change")
    # Checked before anything is changed, so a wrong gesture doesn't leave the settings half applied.
    for name, on in (gestures or {}).items():
        if name not in macos.trackpad.GESTURES:
            raise ValueError("gestures must be among {}, not {!r}".format(", ".join(macos.trackpad.GESTURES), name))
        if not isinstance(on, bool) and name not in _FINGERS:
            raise ValueError("{} is on or off: give true or false, not {!r}".format(name, on))

    changed = []
    with macos.settings.batch():
        if tap_to_click is not None:
            macos.trackpad.set_tap_to_click(tap_to_click)
            changed.append("tap to click")
        if natural_scrolling is not None:
            macos.trackpad.set_natural_scrolling(natural_scrolling)
            changed.append("natural scrolling")
        if tracking_speed is not None:
            macos.trackpad.set_tracking_speed(tracking_speed)
            changed.append("tracking speed")
        if three_finger_drag is not None:
            macos.trackpad.set_three_finger_drag(three_finger_drag)
            changed.append("three-finger drag")
        if secondary_click is not None:
            macos.trackpad.set_secondary_click(None if secondary_click == "off" else secondary_click)
            changed.append("secondary click")
        if click_pressure is not None:
            macos.trackpad.set_click_pressure(click_pressure)
            changed.append("click pressure")
        for name, on in (gestures or {}).items():
            macos.trackpad.set_gesture(name, on)
            changed.append(name.replace("_", " "))
    return "Changed: {}.".format(", ".join(changed))


def register(server: MCPServer) -> None:
    add_tool(server, get_trackpad_settings, title="Get the trackpad's settings", annotations=READ_ONLY)
    add_tool(server, set_trackpad_settings, title="Change the trackpad's settings", annotations=REPLACING)
