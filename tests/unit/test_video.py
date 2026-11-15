"""The tools of mcp_server_macos.tools.video, with macos.video faked: no video is read or written."""

from pathlib import Path
from typing import Any, Dict, Tuple

import macos
import pytest
from mcp import Client
from mcp.types import ImageContent

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio

OUT = Path("/Users/me/out.mp4")


async def test_get_video_info(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    info = macos.video.VideoInfo(duration=12.5, width=1080, height=1920, fps=29.97, codec="hevc", has_audio=True)
    monkeypatch.setattr(macos.video, "info", lambda path: info)

    result = await client.call_tool("get_video_info", {"path": "clip.mov"})

    assert result.structured_content == {
        "duration_seconds": 12.5,
        "width": 1080,
        "height": 1920,
        "fps": 29.97,
        "codec": "hevc",
        "has_audio": True,
    }


async def test_get_video_frame(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.video, "frame", recorder.function("frame", b"\x89PNG fake"))

    result = await client.call_tool("get_video_frame", {"path": "clip.mov", "at_seconds": 3})

    assert not result.is_error
    (image,) = result.content
    assert isinstance(image, ImageContent) and image.mime_type == "image/png"
    # A picture the model reads is kept to a sensible size by default.
    assert recorder.calls == [("frame", ("clip.mov", 3.0), {"size": 1024})]


async def test_save_video_frames(client: Client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    recorder = Recorder()
    info = macos.video.VideoInfo(duration=9.0, width=1920, height=1080, fps=30.0, codec="h264", has_audio=True)
    monkeypatch.setattr(macos.video, "info", lambda path: info)
    monkeypatch.setattr(macos.video, "frames", recorder.function("frames", [b"one", b"two"]))
    folder = tmp_path / "new" / "frames"

    result = await client.call_tool(
        "save_video_frames", {"path": "clip.mov", "folder": str(folder), "every_seconds": 5, "size": 320}
    )

    assert not result.is_error, text(result)
    assert result.structured_content == {"paths": [str(folder / "frame-000.png"), str(folder / "frame-001.png")]}
    assert (folder / "frame-001.png").read_bytes() == b"two"
    assert recorder.calls == [("frames", ("clip.mov", 5.0), {"size": 320})]


@pytest.mark.parametrize(
    "arguments, why",
    [
        # A two-hour video at a frame a second: 7200 frames.
        ({"every_seconds": 1}, "7200 frames of 1024 pixels are more than can be made at once"),
        # At the video's own size, fewer fit.
        ({"every_seconds": 60, "size": None}, "120 frames of 3840 pixels"),
    ],
)
async def test_save_video_frames_does_not_make_more_than_memory_holds(
    client: Client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, arguments: Dict[str, Any], why: str
) -> None:
    recorder = Recorder()
    info = macos.video.VideoInfo(duration=7200.0, width=3840, height=2160, fps=30.0, codec="hevc", has_audio=True)
    monkeypatch.setattr(macos.video, "info", lambda path: info)
    monkeypatch.setattr(macos.video, "frames", recorder.function("frames", []))

    result = await client.call_tool("save_video_frames", {"path": "film.mov", "folder": str(tmp_path), **arguments})

    assert result.is_error
    assert why in text(result)
    assert "save one every" in text(result)
    assert recorder.calls == []


WRITERS: Dict[str, Tuple[Dict[str, Any], str, Tuple[Any, ...], Dict[str, Any]]] = {
    "convert_video": (
        {"source": "screen.mov", "output": "share.mp4", "quality": "medium", "height": 720, "start": 2, "duration": 10},
        "convert",
        ("screen.mov", "share.mp4"),
        {"quality": "medium", "hevc": False, "height": 720, "start": 2.0, "duration": 10.0},
    ),
    "video_to_gif": (
        {"source": "demo.mov", "output": "demo.gif", "width": 640},
        "to_gif",
        ("demo.mov", "demo.gif"),
        {"fps": 10.0, "width": 640, "start": None, "duration": None, "loop": True},
    ),
    "trim_video": (
        {"source": "a.mov", "output": "b.mov", "start": 1800, "duration": 90},
        "trim",
        ("a.mov", "b.mov", 1800.0, 90.0),
        {},
    ),
    "join_videos": ({"videos": ["a.mov", "b.mov"], "output": "c.mp4"}, "concat", (["a.mov", "b.mov"], "c.mp4"), {}),
    "change_video_speed": ({"source": "a.mov", "output": "b.mp4", "factor": 8}, "speed", ("a.mov", "b.mp4", 8.0), {}),
    "rotate_video": ({"source": "a.mov", "output": "b.mov", "degrees": 90}, "rotate", ("a.mov", "b.mov", 90), {}),
    "crop_video": (
        {"source": "a.mov", "output": "b.mov", "x": 100, "y": 80, "width": 1280, "height": 720},
        "crop",
        ("a.mov", "b.mov", (100, 80, 1280, 720)),
        {},
    ),
    "mute_video": ({"source": "a.mov", "output": "b.mov"}, "mute", ("a.mov", "b.mov"), {}),
    "add_audio_to_video": (
        {"video": "a.mov", "audio": "music.m4a", "output": "b.mp4", "volume": 0.5},
        "add_audio",
        ("a.mov", "music.m4a", "b.mp4"),
        {"at": 0.0, "replace": False, "volume": 0.5},
    ),
    "add_video_language_track": (
        {"video": "film.mov", "audio": "en.m4a", "output": "dual.mov", "language": "en", "original_language": "es"},
        "add_language_track",
        ("film.mov", "en.m4a", "dual.mov", "en"),
        {"original_language": "es"},
    ),
    "images_to_video": (
        {"images": ["1.jpg", "2.jpg"], "output": "show.mp4", "fps": 1, "width": 1280},
        "from_images",
        (["1.jpg", "2.jpg"], "show.mp4", 1.0),
        {"width": 1280},
    ),
    "reverse_video": ({"source": "a.mov", "output": "b.mov"}, "reverse", ("a.mov", "b.mov"), {}),
}


@pytest.mark.parametrize("tool", sorted(WRITERS))
async def test_video_is_written_as_asked(client: Client, monkeypatch: pytest.MonkeyPatch, tool: str) -> None:
    arguments, function, args, options = WRITERS[tool]
    recorder = Recorder()
    monkeypatch.setattr(macos.video, function, recorder.function(function, OUT))

    result = await client.call_tool(tool, arguments)

    assert not result.is_error, text(result)
    assert result.structured_content == {"path": str(OUT)}
    assert recorder.calls == [(function, args, options)]


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("get_video_frame", {"path": "a.mov", "at_seconds": -1}),
        ("save_video_frames", {"path": "a.mov", "folder": "f", "every_seconds": 0}),
        ("convert_video", {"source": "a.mov", "output": "b.mp4", "quality": "best"}),
        ("convert_video", {"source": "a.mov", "output": "b.mp4", "height": 1000}),
        ("trim_video", {"source": "a.mov", "output": "b.mov", "duration": 0}),
        ("rotate_video", {"source": "a.mov", "output": "b.mov", "degrees": 45}),
        ("change_video_speed", {"source": "a.mov", "output": "b.mov", "factor": 0}),
        ("add_audio_to_video", {"video": "a.mov", "audio": "m.m4a", "output": "b.mp4", "volume": 2}),
        ("join_videos", {"videos": [], "output": "c.mp4"}),
        ("video_to_gif", {"source": "a.mov", "output": "a.gif", "fps": 60}),
        ("crop_video", {"source": "a.mov", "output": "b.mov", "x": 0, "y": 0, "width": 1, "height": 10}),
    ],
)
async def test_videos_are_not_touched_without_what_they_need(
    client: Client, monkeypatch: pytest.MonkeyPatch, tool: str, arguments: Dict[str, Any]
) -> None:
    recorder = Recorder()
    for name in macos.video.__all__:
        if callable(getattr(macos.video, name)) and not isinstance(getattr(macos.video, name), type):
            monkeypatch.setattr(macos.video, name, recorder.function(name, OUT))

    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert recorder.calls == []
