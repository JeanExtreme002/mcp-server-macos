"""Tools for the webcam: the cameras, photos and videos, from ``macos.camera``."""

from typing import Annotated, List, Optional

import macos
from mcp.server.mcpserver import Image, MCPServer
from pydantic import BaseModel, Field

from .. import _elsewhere, _permissions
from .._permissions import CAMERA, MICROPHONE
from .._registry import LONGEST_WAIT, READ_ONLY, REPLACING, add_tool
from .screen import Saved, look

Camera = Annotated[
    Optional[str], Field(description="The camera, by its name (or part of it) or its ID. The default one by default.")
]


class CameraInfo(BaseModel):
    """A connected camera."""

    name: str = Field(description="Its name, such as 'FaceTime HD Camera'.")
    id: str = Field(description="Its unique ID.")
    default: bool = Field(description="Whether it's the one used by default.")


class Cameras(BaseModel):
    """The connected cameras."""

    cameras: List[CameraInfo] = Field(description="The cameras, the default one first.")
    camera_permission: bool = Field(description="Whether the app running the server may use the camera.")


def list_cameras() -> Cameras:
    """List the connected cameras, and whether the camera may be used."""
    return Cameras(
        cameras=[
            CameraInfo(name=camera.name, id=camera.id, default=camera.is_default) for camera in macos.camera.devices()
        ],
        camera_permission=macos.camera.has_permission(),
    )


def take_photo(camera: Camera = None) -> Image:
    """
    Look through the webcam: take a photo and see it. The camera's green light turns on for a second or
    two: take one only when the user asked for it. To keep it as a file, use save_photo.
    """
    image, _, _ = look(lambda path: macos.camera.photo(path, camera=camera))
    return image


def save_photo(
    path: Annotated[
        str,
        Field(
            description="Where to save it: .jpg, .png, .heic or .tiff, after the extension. A file already there is "
            "replaced.",
            min_length=1,
        ),
    ],
    camera: Camera = None,
) -> Saved:
    """Take a photo with the webcam and save it. Take one only when the user asked for it."""
    return Saved(path=str(macos.camera.photo(path, camera=camera)))


def record_video(
    path: Annotated[
        str, Field(description="Where to save the video, a .mov. A file already there is replaced.", min_length=1)
    ],
    seconds: Annotated[float, Field(description="How long to record.", gt=0, le=LONGEST_WAIT)],
    camera: Camera = None,
    audio: Annotated[
        bool, Field(description="True to record the microphone too, which needs its own permission.")
    ] = False,
) -> Saved:
    """Record a video with the webcam. It returns when the recording ends. Record only when the user asked for it."""
    if audio:
        # The tool needs the camera, and the microphone only with sound: asked for here, with its own
        # instructions, rather than as the camera when it's the one missing.
        _permissions.require(MICROPHONE, macos.audio.has_permission)
    # Asked for here, in the server, before the recording: the prompt waits for the user, for as long as
    # they take, which isn't the recording's time.
    _permissions.require(CAMERA, macos.camera.has_permission)
    # The camera records on the main thread, which is the server's: it would answer nothing else for
    # as long as the video lasts. A process of its own records on its own main thread instead.
    saved = _elsewhere.call(
        "mcp_server_macos.tools.camera:_record_here", [path, seconds, camera, audio], lasts=_recording_time(seconds)
    )
    return Saved(path=saved)


def _recording_time(seconds: float) -> float:
    """
    The longest a recording of ``seconds`` takes, as pymacos waits for it: the camera starting (15
    seconds at most), the video and a second, then the movie finished (15 seconds, and a tenth of it).
    """
    return 15.0 + seconds + 1.0 + 15.0 + seconds / 10


def _record_here(path: str, seconds: float, camera: Optional[str], audio: bool) -> str:
    """Record on this process's main thread, as the camera needs: run by the process record_video starts."""
    return str(macos.camera.record(path, seconds, camera=camera, audio=audio))


def register(server: MCPServer) -> None:
    add_tool(server, list_cameras, title="List the cameras", annotations=READ_ONLY)
    # The camera takes photos on the main thread, as macOS needs: a second or two. A photo looked at is
    # only read: nothing is kept.
    add_tool(server, take_photo, title="Take a photo", annotations=READ_ONLY, permission=CAMERA, main_thread=True)
    # These write a file made from scratch: done again, they write a new one in its place.
    add_tool(server, save_photo, title="Save a photo", annotations=REPLACING, permission=CAMERA, main_thread=True)
    add_tool(server, record_video, title="Record a video", annotations=REPLACING, permission=CAMERA)
