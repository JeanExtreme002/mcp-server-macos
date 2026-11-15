"""The tools of mcp_server_macos.tools.camera, with macos.camera faked: the camera doesn't turn on."""

from pathlib import Path
from typing import Any, Dict, Tuple

import macos
import pytest
from mcp import Client
from mcp.server.mcpserver import Image
from mcp.types import ImageContent

from mcp_server_macos.tools import camera
from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


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
