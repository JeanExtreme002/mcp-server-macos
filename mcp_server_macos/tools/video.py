"""Tools that read, convert and edit videos, with AVFoundation, from ``macos.video``."""

import math
from pathlib import Path
from typing import Annotated, List, Literal, Optional

import macos
from mcp.server.mcpserver import Image, MCPServer
from pydantic import BaseModel, Field

from .._registry import DESTRUCTIVE, READ_ONLY, REPLACING, add_tool

VideoPath = Annotated[
    str, Field(description="The path of the video: any format QuickTime opens (MOV, MP4, M4V...).", min_length=1)
]
Output = Annotated[
    str,
    Field(
        description="Where to save the result. Its extension picks the container: .mp4, .mov or .m4v. A file already "
        "there is replaced.",
        min_length=1,
    ),
]
Start = Annotated[Optional[float], Field(description="Where to start, in seconds from the beginning.", ge=0)]
Duration = Annotated[Optional[float], Field(description="How long to keep, in seconds. To the end by default.", gt=0)]
# The frames save_video_frames may make at once, counted in pixels: 500 frames of 1024 x 1024. pymacos
# makes them all before they're saved, so this is what bounds the memory a call takes.
FRAME_BUDGET = 500 * 1024 * 1024


class VideoInfo(BaseModel):
    """What a video file contains."""

    duration_seconds: float = Field(description="How long it is, in seconds.")
    width: int = Field(description="Its width, in pixels, as it plays (turned upright, like a portrait phone video).")
    height: int = Field(description="Its height, in pixels, as it plays.")
    fps: Optional[float] = Field(description="Its frames per second, as the file declares it.")
    codec: Optional[str] = Field(
        description="Its codec: 'h264', 'hevc', 'prores'... or a four-character code for others."
    )
    has_audio: bool = Field(description="Whether it has sound.")


class Saved(BaseModel):
    """A file that was written."""

    path: str = Field(description="The path of the file.")


class SavedFiles(BaseModel):
    """Files that were written."""

    paths: List[str] = Field(description="The paths of the files, in order.")


def _saved(path: Path) -> Saved:
    return Saved(path=str(path))


def get_video_info(path: VideoPath) -> VideoInfo:
    """Get a video's duration, size, frame rate and codec, and whether it has sound."""
    info = macos.video.info(path)
    return VideoInfo(
        duration_seconds=info.duration,
        width=info.width,
        height=info.height,
        fps=info.fps,
        codec=info.codec,
        has_audio=info.has_audio,
    )


def get_video_frame(
    path: VideoPath,
    at_seconds: Annotated[
        float, Field(description="When, in seconds from the start: the duration gives the last frame.", ge=0)
    ] = 0.0,
    size: Annotated[int, Field(description="The longest side of the picture, in pixels.", ge=16, le=4096)] = 1024,
) -> Image:
    """Get the frame a video shows at a moment, as a picture, turned upright: to look at what the video shows."""
    return Image(data=macos.video.frame(path, at_seconds, size=size), format="png")


def save_video_frames(
    path: VideoPath,
    folder: Annotated[
        str, Field(description="The folder to save the frames into, as frame-000.png, frame-001.png...", min_length=1)
    ],
    every_seconds: Annotated[
        float, Field(description="Save a frame every so many seconds, from the start.", gt=0)
    ] = 1.0,
    size: Annotated[
        Optional[int],
        Field(description="The longest side of each frame, in pixels. Null for the video's own size.", ge=16, le=8192),
    ] = 1024,
) -> SavedFiles:
    """
    Save frames of a video, one every so many seconds, as PNGs in a folder. The frames are all made
    before they're saved, so their number is bounded: some 500 at 1024 pixels, fewer when larger. For a
    long video, save one every few seconds, or smaller ones.
    """
    info = macos.video.info(path)
    count = max(1, math.ceil(info.duration / every_seconds))
    side = size or max(info.width, info.height, 1)
    if count * side * side > FRAME_BUDGET:
        raise ValueError(
            "{} frames of {} pixels are more than can be made at once: save one every {:g} seconds or more, or "
            "smaller ones".format(count, side, math.ceil(count * side * side / FRAME_BUDGET * every_seconds))
        )
    saved = Path(folder).expanduser()
    saved.mkdir(parents=True, exist_ok=True)
    paths: List[str] = []
    for index, frame in enumerate(macos.video.frames(path, every_seconds, size=size)):
        written = saved / "frame-{:03}.png".format(index)
        written.write_bytes(frame)
        paths.append(str(written.absolute()))
    return SavedFiles(paths=paths)


def convert_video(
    source: VideoPath,
    output: Annotated[
        str,
        Field(
            description="Where to save the result. Its extension picks the container: .mp4, .mov or .m4v, or .m4a for "
            "the sound alone. A file already there is replaced.",
            min_length=1,
        ),
    ],
    quality: Annotated[
        Literal["high", "medium", "low"],
        Field(description="'high', 'medium' or 'low' (a small preview, about 224 pixels wide)."),
    ] = "high",
    hevc: Annotated[
        bool, Field(description="True to encode in HEVC (H.265), smaller than H.264 at the same quality.")
    ] = False,
    height: Annotated[
        Optional[Literal[480, 540, 720, 1080, 2160]],
        Field(
            description="Resize it to fit 640×480, 960×540, 1280×720, 1920×1080 or 3840×2160, keeping its proportions "
            "(only 1080 and 2160 with HEVC). The quality is then ignored."
        ),
    ] = None,
    start: Start = None,
    duration: Duration = None,
) -> Saved:
    """Convert, compress, resize or cut a video, re-encoding it, exact to the frame."""
    return _saved(
        macos.video.convert(source, output, quality=quality, hevc=hevc, height=height, start=start, duration=duration)
    )


def video_to_gif(
    source: VideoPath,
    output: Annotated[str, Field(description="Where to save the GIF. A file already there is replaced.", min_length=1)],
    fps: Annotated[float, Field(description="The GIF's frames per second, up to 50.", gt=0, le=50)] = 10.0,
    width: Annotated[
        int, Field(description="The GIF's width, in pixels, never wider than the video.", ge=16, le=4096)
    ] = 480,
    start: Start = None,
    duration: Duration = None,
    loop: Annotated[bool, Field(description="True to loop forever, false to play once.")] = True,
) -> Saved:
    """Turn a video, or part of it, into an animated GIF: for a screen recording in a README or a chat. GIFs get big fast."""
    return _saved(macos.video.to_gif(source, output, fps=fps, width=width, start=start, duration=duration, loop=loop))


def trim_video(
    source: VideoPath,
    output: Output,
    start: Annotated[float, Field(description="Where to start, in seconds from the beginning.", ge=0)] = 0.0,
    duration: Duration = None,
) -> Saved:
    """
    Keep part of a video without re-encoding it: fast and lossless. The cut lands on the nearest
    keyframe, so it may start a little early; convert_video with start and duration cuts exactly.
    """
    return _saved(macos.video.trim(source, output, start, duration))


def join_videos(
    videos: Annotated[
        List[str], Field(description="The videos, in order: clips of the same size and orientation.", min_length=1)
    ],
    output: Output,
) -> Saved:
    """Join videos one after another, sound included, re-encoding them at the highest quality."""
    return _saved(macos.video.concat(videos, output))


def change_video_speed(
    source: VideoPath,
    output: Output,
    factor: Annotated[
        float, Field(description="How many times faster: 2 for twice as fast, 0.5 for half.", gt=0, le=1000)
    ],
) -> Saved:
    """Play a video faster or slower. The sound follows, at the same pitch."""
    return _saved(macos.video.speed(source, output, factor))


def rotate_video(
    source: VideoPath,
    output: Output,
    degrees: Annotated[
        Literal[90, 180, 270, -90, -180, -270],
        Field(description="How far to turn it clockwise: 90, 180 or 270. Negative turns counter-clockwise."),
    ],
) -> Saved:
    """Turn a video, fast and losslessly: it's marked to play turned, as phones do."""
    return _saved(macos.video.rotate(source, output, degrees))


def crop_video(
    source: VideoPath,
    output: Output,
    x: Annotated[int, Field(description="The left edge of the part to keep, in pixels from the left.", ge=0)],
    y: Annotated[int, Field(description="The top edge of the part to keep, in pixels from the top.", ge=0)],
    width: Annotated[int, Field(description="The width of the part to keep, in pixels: 2 at least.", ge=2)],
    height: Annotated[int, Field(description="The height of the part to keep, in pixels: 2 at least.", ge=2)],
) -> Saved:
    """Keep the part of a video inside a box, measured on the picture as it plays. An odd width or height loses its last pixel."""
    return _saved(macos.video.crop(source, output, (x, y, width, height)))


def mute_video(source: VideoPath, output: Output) -> Saved:
    """Save a video without its sound, fast and losslessly."""
    return _saved(macos.video.mute(source, output))


def add_audio_to_video(
    video: VideoPath,
    audio: Annotated[str, Field(description="The sound to add: music, a voice-over...", min_length=1)],
    output: Output,
    at_seconds: Annotated[float, Field(description="When it starts, in seconds into the video.", ge=0)] = 0.0,
    replace: Annotated[
        bool, Field(description="True to drop the video's own sound. It plays over it by default.")
    ] = False,
    volume: Annotated[float, Field(description="The added sound's loudness, from 0 to 1.", ge=0, le=1)] = 1.0,
) -> Saved:
    """Add a sound to a video, over its own sound or in its place. A sound longer than the video is cut at its end."""
    return _saved(macos.video.add_audio(video, audio, output, at=at_seconds, replace=replace, volume=volume))


def add_video_language_track(
    video: VideoPath,
    audio: Annotated[str, Field(description="The sound in the other language.", min_length=1)],
    output: Output,
    language: Annotated[
        str, Field(description="Its language, as a tag such as 'en', 'fr-CA' or 'es-419'.", min_length=1)
    ],
    original_language: Annotated[
        Optional[str], Field(description="The language of the sound already there, to label it.")
    ] = None,
) -> Saved:
    """
    Add a sound in another language as an alternative track, which players offer in their audio menu.
    The video's own sound stays the default.
    """
    return _saved(macos.video.add_language_track(video, audio, output, language, original_language=original_language))


def images_to_video(
    images: Annotated[List[str], Field(description="The images, in order.", min_length=1)],
    output: Output,
    fps: Annotated[
        float, Field(description="How many images per second: 1 shows each for a second, 0.1 for ten.", gt=0, le=1000)
    ] = 24.0,
    width: Annotated[
        Optional[int], Field(description="The video's width, keeping proportions. The first image's by default.", ge=2)
    ] = None,
) -> Saved:
    """
    Make a video from images, one after another: for timelapses and slideshows. Images of other shapes
    are fitted in, on black.
    """
    return _saved(macos.video.from_images(images, output, fps, width=width))


def reverse_video(source: VideoPath, output: Output) -> Saved:
    """Save a video played backwards, sound included. Slow on long videos: a few seconds of clip is best."""
    return _saved(macos.video.reverse(source, output))


def register(server: MCPServer) -> None:
    add_tool(server, get_video_info, title="Get a video's information", annotations=READ_ONLY)
    add_tool(server, get_video_frame, title="Get a frame of a video", annotations=READ_ONLY)
    # They make a file from scratch, from the video: doing it again gives the same files.
    for setter, title in (
        (save_video_frames, "Save frames of a video"),
        (video_to_gif, "Turn a video into a GIF"),
        (mute_video, "Remove a video's sound"),
        (images_to_video, "Make a video from images"),
    ):
        add_tool(server, setter, title=title, annotations=REPLACING)
    # These change the video, and the output may be the source: done again, they cut, speed up, turn,
    # add or reverse it again. Not idempotent, then, and they write over a file.
    for transform, title in (
        (convert_video, "Convert a video"),
        (trim_video, "Trim a video"),
        (join_videos, "Join videos"),
        (change_video_speed, "Change a video's speed"),
        (rotate_video, "Rotate a video"),
        (crop_video, "Crop a video"),
        (add_audio_to_video, "Add a sound to a video"),
        (add_video_language_track, "Add a language track to a video"),
        (reverse_video, "Reverse a video"),
    ):
        add_tool(server, transform, title=title, annotations=DESTRUCTIVE)
