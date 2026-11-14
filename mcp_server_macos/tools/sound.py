"""Tools that play sounds and set the alert sound, from ``macos.sound``."""

from typing import Annotated, List, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._registry import ADDITIVE, READ_ONLY, REPLACING, add_tool


class SoundSettings(BaseModel):
    """The settings of System Settings › Sound that are about alerts and effects."""

    alert_sound: Optional[str] = Field(description="The name of the alert sound. Null for macOS's own.")
    alert_volume: int = Field(description="The volume of alert sounds, from 0 to 100, as a share of the output volume.")
    ui_sounds: bool = Field(
        description="Whether the interface plays sound effects, such as emptying the Trash or taking a screenshot."
    )
    available_alert_sounds: List[str] = Field(
        description="The names of the alert sounds there are, which play_sound and set_sound_settings take."
    )


def get_sound_settings() -> SoundSettings:
    """
    Get the alert sound and its volume, whether the interface plays sound effects, and the names of the
    alert sounds there are. The output volume itself is get_volume's.
    """
    return SoundSettings(
        alert_sound=macos.sound.alert_sound(),
        alert_volume=round(macos.sound.alert_volume() * 100),
        ui_sounds=macos.sound.ui_sounds(),
        available_alert_sounds=macos.sound.names(),
    )


def play_sound(
    sound: Annotated[
        str,
        Field(
            description="The name of an alert sound ('Glass', 'Ping', 'Basso'...: get_sound_settings lists them) or "
            "the path of an audio file.",
            min_length=1,
        ),
    ],
    volume: Annotated[
        int, Field(description="How loud, from 0 to 100, relative to the system volume.", ge=0, le=100)
    ] = 100,
    wait: Annotated[
        bool,
        Field(description="True to return when the sound ends, false to return right away while it plays."),
    ] = True,
) -> str:
    """Play an alert sound, by its name, or an audio file, through the Mac's speakers."""
    macos.sound.play(sound, volume=volume / 100, wait=wait)
    return "Played {}.".format(sound) if wait else "Playing {}.".format(sound)


def play_alert_beep() -> str:
    """Play the alert sound chosen in System Settings › Sound, like an app's error beep."""
    macos.sound.beep()
    return "Beeped."


def set_sound_settings(
    alert_sound: Annotated[
        Optional[str],
        Field(
            description="The alert sound, by its name ('Funk', 'Glass'...: get_sound_settings lists them), or "
            "'default' for macOS's own. Apps pick it up when reopened."
        ),
    ] = None,
    alert_volume: Annotated[
        Optional[int],
        Field(description="The volume of alert sounds, from 0 to 100, apart from music and videos.", ge=0, le=100),
    ] = None,
    ui_sounds: Annotated[
        Optional[bool],
        Field(description="True for the interface to play its sound effects, false to keep it quiet. Alerts still play."),
    ] = None,
) -> str:
    """
    Change the alert sound, its volume, or whether the interface plays sound effects. Give only the
    settings to change: the others stay as they are.
    """
    if alert_sound is None and alert_volume is None and ui_sounds is None:
        raise ValueError("no setting was given: say which one to change")
    if alert_sound is not None and alert_sound != "default":
        # Checked before anything is changed, so a wrong name doesn't leave the settings half applied.
        names = macos.sound.names()
        if alert_sound.casefold() not in (name.casefold() for name in names):
            raise ValueError("alert_sound must be 'default' or one of {}, not {!r}".format(", ".join(names), alert_sound))

    changed: List[str] = []
    if alert_sound is not None:
        macos.sound.set_alert_sound(None if alert_sound == "default" else alert_sound)
        changed.append("alert sound")
    if alert_volume is not None:
        macos.sound.set_alert_volume(alert_volume / 100)
        changed.append("alert volume")
    if ui_sounds is not None:
        macos.sound.set_ui_sounds(ui_sounds)
        changed.append("interface sounds")
    return "Changed: {}.".format(", ".join(changed))


def register(server: MCPServer) -> None:
    add_tool(server, get_sound_settings, title="Get the sound settings", annotations=READ_ONLY)
    add_tool(server, play_sound, title="Play a sound", annotations=ADDITIVE)
    add_tool(server, play_alert_beep, title="Play the alert beep", annotations=ADDITIVE)
    add_tool(server, set_sound_settings, title="Change the sound settings", annotations=REPLACING)
