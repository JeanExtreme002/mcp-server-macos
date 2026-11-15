"""The tools of mcp_server_macos.tools.camera, with macos.camera faked: the camera doesn't turn on."""

import importlib
import threading
from pathlib import Path
from typing import Any, Dict, List, Tuple

import macos
import pytest
from mcp import Client
from mcp.server.mcpserver import Image
from mcp.types import ImageContent

from mcp_server_macos import _elsewhere
from mcp_server_macos.tools import camera
from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def here(monkeypatch: pytest.MonkeyPatch) -> List[Any]:
    """A video is recorded in a process of its own: here, in this one, where pymacos is faked."""
    called: List[Any] = []

    def call(function: str, args: List[Any], *, lasts: float) -> Any:
        called.append((function, args, lasts))
        module, _, name = function.partition(":")
        return getattr(importlib.import_module(module), name)(*args)

    monkeypatch.setattr(_elsewhere, "call", call)
    # A video asks for the camera first, in the server: granted here, unless a test says otherwise.
    monkeypatch.setattr(macos.camera, "has_permission", lambda: True)
    return called


async def test_list_cameras(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    found = [
        macos.camera.Camera(name="FaceTime HD Camera", id="A1", is_default=True),
        macos.camera.Camera(name="iPhone", id="B2", is_default=False),
    ]
    monkeypatch.setattr(macos.camera, "devices", lambda: found)
    monkeypatch.setattr(macos.camera, "has_permission", lambda: False)

    result = await client.call_tool("list_cameras", {})

    assert result.structured_content == {
        "cameras": [
            {"name": "FaceTime HD Camera", "id": "A1", "default": True},
            {"name": "iPhone", "id": "B2", "default": False},
        ],
        "camera_permission": False,
    }


async def test_take_photo(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.camera, "photo", recorder.function("photo"))

    def look(take: Any) -> Tuple[Image, int, int]:
        take(Path("/tmp/picture.png"))
        return Image(data=b"jpeg", format="jpeg"), 1280, 720

    monkeypatch.setattr(camera, "look", look)

    result = await client.call_tool("take_photo", {"camera": "iPhone"})

    (image,) = result.content
    assert isinstance(image, ImageContent) and image.mime_type == "image/jpeg"
    assert recorder.calls == [("photo", (Path("/tmp/picture.png"),), {"camera": "iPhone"})]


@pytest.mark.parametrize(
    "tool, arguments, call",
    [
        ("save_photo", {"path": "me.heic"}, ("photo", ("me.heic",), {"camera": None})),
        (
            "record_video",
            {"path": "clip.mov", "seconds": 5},
            ("record", ("clip.mov", 5.0), {"camera": None, "audio": False}),
        ),
        (
            "record_video",
            {"path": "clip.mov", "seconds": 2.5, "camera": "A1", "audio": True},
            ("record", ("clip.mov", 2.5), {"camera": "A1", "audio": True}),
        ),
    ],
)
async def test_camera_files(
    client: Client, monkeypatch: pytest.MonkeyPatch, tool: str, arguments: Dict[str, Any], call: Any
) -> None:
    recorder = Recorder()
    # A video with sound checks the microphone first: here, without macOS's.
    monkeypatch.setattr(macos.audio, "has_permission", lambda: True)
    monkeypatch.setattr(macos.camera, call[0], recorder.function(call[0], Path(call[1][0])))

    result = await client.call_tool(tool, arguments)

    assert result.structured_content == {"path": call[1][0]}
    assert recorder.calls == [call]


async def test_a_video_with_sound_asks_for_the_microphone(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    asked = Recorder()
    monkeypatch.setattr(macos.camera, "record", asked.function("record"))
    monkeypatch.setattr(macos.camera, "request_permission", asked.function("camera", True))
    monkeypatch.setattr(macos.audio, "has_permission", lambda: False)
    monkeypatch.setattr(macos.audio, "request_permission", asked.function("microphone", False))

    result = await client.call_tool("record_video", {"path": "clip.mov", "seconds": 3, "audio": True})

    assert result.is_error
    assert asked.names == ["microphone"]
    assert "System Settings › Privacy & Security › Microphone" in text(result)
    assert "› Camera" not in text(result)


async def test_photos_are_taken_on_the_main_thread_and_videos_in_a_process_of_their_own(
    client: Client, monkeypatch: pytest.MonkeyPatch, here: List[Any]
) -> None:
    # The camera works on the main thread only. A photo takes a second there; a video, which may last
    # minutes, is recorded on the main thread of a process of its own, so the server keeps answering.
    threads: List[Any] = []

    def photo(path: str, camera: Any) -> Path:
        threads.append(threading.current_thread())
        return Path(path)

    monkeypatch.setattr(macos.camera, "photo", photo)
    monkeypatch.setattr(macos.camera, "record", lambda path, seconds, camera, audio: Path(path))

    await client.call_tool("save_photo", {"path": "me.jpg"})
    await client.call_tool("record_video", {"path": "clip.mov", "seconds": 90})

    assert threads == [threading.main_thread()]
    # As long as pymacos may take: 15 seconds for the camera to start, the video and a second, then 15
    # seconds and a tenth of the video to finish the movie.
    assert here == [("mcp_server_macos.tools.camera:_record_here", ["clip.mov", 90.0, None, False], 130.0)]


async def test_a_video_asks_for_the_camera_before_it_starts(
    client: Client, monkeypatch: pytest.MonkeyPatch, here: List[Any]
) -> None:
    # The prompt waits for the user, for as long as they take: in the server, not within the time the
    # recording's process is given.
    asked = Recorder()
    monkeypatch.setattr(macos.camera, "has_permission", lambda: False)
    monkeypatch.setattr(macos.camera, "request_permission", asked.function("request_permission", False))

    result = await client.call_tool("record_video", {"path": "clip.mov", "seconds": 5})

    assert result.is_error
    assert asked.names == ["request_permission"]
    assert "System Settings › Privacy & Security › Camera" in text(result)
    assert here == []


async def test_without_the_permission_it_is_asked_for(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    asked = Recorder()
    monkeypatch.setattr(macos.camera, "photo", asked.function("photo", error=macos.PermissionDeniedError("no Camera")))
    monkeypatch.setattr(macos.camera, "request_permission", asked.function("request_permission", False))

    result = await client.call_tool("save_photo", {"path": "me.jpg"})

    assert asked.names == ["photo", "request_permission"]
    assert "System Settings › Privacy & Security › Camera" in text(result)


@pytest.mark.parametrize(
    "arguments", [{"path": "clip.mov", "seconds": 0}, {"path": "clip.mov", "seconds": 601}, {"path": "", "seconds": 1}]
)
async def test_nothing_is_recorded_without_what_it_needs(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any]
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.camera, "record", recorder.function("record"))

    assert (await client.call_tool("record_video", arguments)).is_error
    assert recorder.calls == []
