"""Tools that control Apple Music and Spotify, from ``macos.music``."""

from typing import Annotated, Literal, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._permissions import AUTOMATION
from .._registry import READ_ONLY, REPLACING, add_tool

Player = Annotated[
    Optional[Literal["Music", "Spotify"]],
    Field(description="'Music' or 'Spotify'. By default, the one playing, or else the one running."),
]


class Track(BaseModel):
    """The song a player is on."""

    title: str = Field(description="The song's title.")
    artist: str = Field(description="Its artist.")
    album: str = Field(description="Its album.")
    duration_seconds: Optional[float] = Field(description="How long it is, in seconds. Null for live radio.")
    position_seconds: Optional[float] = Field(description="How far into the song the player is, in seconds.")
    playing: bool = Field(description="False when paused.")
    app: str = Field(description="The player: 'Music' or 'Spotify'.")
    volume: Optional[int] = Field(
        description="The player's own volume, from 0 to 100, apart from the system's. Null when it can't be read."
    )


class NowPlaying(BaseModel):
    """What a player is on."""

    track: Optional[Track] = Field(description="The song, playing or paused. Null when no player is running.")


def get_now_playing(app: Player = None) -> NowPlaying:
    """
    Get the song Music or Spotify is on, playing or paused, with how far into it the player is and its
    volume. It never opens a player: the track is null when none is running.
    """
    track = macos.music.now_playing(app)
    if track is None:
        return NowPlaying(track=None)
    try:
        volume: Optional[int] = macos.music.volume(track.app)
    except macos.MacOSError:
        volume = None  # the player quit in between, or won't say
    return NowPlaying(
        track=Track(
            title=track.title,
            artist=track.artist,
            album=track.album,
            duration_seconds=track.duration,
            position_seconds=track.position,
            playing=track.playing,
            app=track.app,
            volume=volume,
        )
    )


def control_music(
    action: Annotated[
        Literal["play", "pause", "play_pause", "next", "previous"],
        Field(
            description="'play' (or resume), 'pause', 'play_pause' (like the play/pause key), 'next' song, or "
            "'previous' (or the start of this one)."
        ),
    ],
    app: Player = None,
) -> str:
    """
    Play, pause or skip songs in Music or Spotify, like the media keys. Only 'play' opens a player when
    none is running (Music, then); the others fail.
    """
    {
        "play": macos.music.play,
        "pause": macos.music.pause,
        "play_pause": macos.music.play_pause,
        "next": macos.music.next,
        "previous": macos.music.previous,
    }[action](app)
    return "Done: {}.".format(action.replace("_", "/"))


def set_music_volume(
    level: Annotated[int, Field(description="The player's volume, from 0 to 100.", ge=0, le=100)],
    app: Player = None,
) -> str:
    """Set the player's own volume, apart from the system's (set_volume). The player must be running."""
    macos.music.set_volume(level, app)
    return "Player volume set to {}.".format(level)


def seek_music(
    seconds: Annotated[float, Field(description="Where to jump to in the song, in seconds from its start.", ge=0)],
    app: Player = None,
) -> str:
    """Jump to a point of the current song, like dragging the progress bar. Past the end, the next song plays."""
    macos.music.seek(seconds, app)
    return "Jumped to {:g} seconds.".format(seconds)


def register(server: MCPServer) -> None:
    # The players are asked through AppleScript, which macOS asks the user to allow, the first time.
    add_tool(server, get_now_playing, title="Get what's playing", annotations=READ_ONLY, permission=AUTOMATION)
    add_tool(server, control_music, title="Play, pause or skip music", annotations=REPLACING, permission=AUTOMATION)
    add_tool(server, set_music_volume, title="Set the music player's volume", annotations=REPLACING, permission=AUTOMATION)
    add_tool(server, seek_music, title="Jump to a point of the song", annotations=REPLACING, permission=AUTOMATION)
