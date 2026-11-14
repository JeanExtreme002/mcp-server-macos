"""Tools for the sound volume, from ``macos.volume``."""

from typing import Annotated, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._registry import READ_ONLY, REPLACING, add_tool


class Volume(BaseModel):
    """The volume of the current sound output."""

    level: Optional[int] = Field(
        description="The output volume, from 0 (silent) to 100. Null when the output device has no volume control."
    )
    muted: Optional[bool] = Field(
        description="Whether the output is muted. Null when the output device has no volume control."
    )


def get_volume() -> Volume:
    """
    Get the Mac's output volume and whether it's muted, for the current output device (the speakers,
    headphones...).
    """
    return Volume(level=macos.volume.get(), muted=macos.volume.is_muted())


def set_volume(
    level: Annotated[int, Field(description="The volume, from 0 (silent) to 100.", ge=0, le=100)],
) -> str:
    """
    Set the Mac's output volume, like the volume keys. It doesn't change whether the output is muted:
    use set_muted for that.
    """
    macos.volume.set(level)
    return "Volume set to {}.".format(level)


def set_muted(
    muted: Annotated[bool, Field(description="True to mute the output, false to unmute it.")],
) -> str:
    """Mute or unmute the Mac's output. The volume level is kept for when it's unmuted."""
    if muted:
        macos.volume.mute()
    else:
        macos.volume.unmute()
    return "Output muted." if muted else "Output unmuted."


def register(server: MCPServer) -> None:
    add_tool(server, get_volume, title="Get the volume", annotations=READ_ONLY)
    add_tool(server, set_volume, title="Set the volume", annotations=REPLACING)
    add_tool(server, set_muted, title="Mute or unmute", annotations=REPLACING)
