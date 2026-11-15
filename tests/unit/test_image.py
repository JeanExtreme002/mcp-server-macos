"""The tools of mcp_server_macos.tools.image, with macos.image faked: no image is read or written."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio

OUT = Path("/Users/me/out.jpg")


async def test_get_image_info(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    info = macos.image.ImageInfo(width=4032, height=3024, format="heic", has_alpha=False, orientation=6, dpi=72.0)
    monkeypatch.setattr(macos.image, "info", lambda path: info)
    monkeypatch.setattr(macos.image, "location", lambda path: (37.8199, -122.4783))
    monkeypatch.setattr(macos.image, "taken_at", lambda path: datetime(2026, 9, 28, 14, 30, tzinfo=timezone(timedelta(hours=-7))))

    result = await client.call_tool("get_image_info", {"path": "IMG_0042.heic"})

    assert not result.is_error
    assert result.structured_content == {
        "width": 4032,
        "height": 3024,
        "format": "heic",
        "has_alpha": False,
        "orientation": 6,
        "dpi": 72.0,
        "taken_at": "2026-09-28T14:30:00-07:00",
        "latitude": 37.8199,
        "longitude": -122.4783,
    }


async def test_get_image_info_of_a_picture_that_is_not_a_photo(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    info = macos.image.ImageInfo(width=10, height=10, format="png", has_alpha=True, orientation=1, dpi=None)
    monkeypatch.setattr(macos.image, "info", lambda path: info)
    monkeypatch.setattr(macos.image, "location", lambda path: None)
    monkeypatch.setattr(macos.image, "taken_at", lambda path: None)

    result = await client.call_tool("get_image_info", {"path": "icon.png"})

    assert result.structured_content is not None
    assert (result.structured_content["taken_at"], result.structured_content["latitude"]) == (None, None)


async def test_get_image_metadata_as_json_has_it(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = {"PixelWidth": 4032, "{Exif}": {"DateTimeOriginal": "2026:09:28 14:30:00", "LensSpecification": (1.5, 6.0)}}
    monkeypatch.setattr(macos.image, "metadata", lambda path: metadata)

    result = await client.call_tool("get_image_metadata", {"path": "a.heic"})

    assert result.structured_content == {
        "result": {"PixelWidth": 4032, "{Exif}": {"DateTimeOriginal": "2026:09:28 14:30:00", "LensSpecification": [1.5, 6.0]}}
    }


async def test_get_image_colors(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.image, "dominant_colors", recorder.function("dominant_colors", ["#1d3557", "#f1faee"]))

    result = await client.call_tool("get_image_colors", {"path": "cover.jpg", "count": 2})

    assert result.structured_content == {"result": ["#1d3557", "#f1faee"]}
    assert recorder.calls == [("dominant_colors", ("cover.jpg", 2), {})]


# The tools that write an image: each calls its function of pymacos as told, and says where it wrote.
# The quality is from 0 to 100 here, and from 0.0 to 1.0 to pymacos.
WRITERS: Dict[str, Tuple[Dict[str, Any], str, Tuple[Any, ...], Dict[str, Any]]] = {
    "remove_image_metadata": ({"source": "a.heic", "output": "b.jpg"}, "strip_metadata", ("a.heic", "b.jpg"), {}),
    "set_image_date": (
        {"path": "a.jpg", "when": "2026-09-28T14:30:00-03:00"},
        "set_taken_at",
        ("a.jpg", datetime(2026, 9, 28, 14, 30, tzinfo=timezone(timedelta(hours=-3)))),
        {"output": None},
    ),
    "set_image_location": (
        {"path": "a.jpg", "latitude": -23.55, "longitude": -46.63, "output": "b.jpg"},
        "set_location",
        ("a.jpg", -23.55, -46.63),
        {"output": "b.jpg"},
    ),
    "convert_image": (
        {"source": "a.heic", "output": "b.jpg", "quality": 80},
        "convert",
        ("a.heic", "b.jpg"),
        {"quality": 0.8},
    ),
    "resize_image": (
        {"source": "a.jpg", "output": "b.jpg", "width": 800},
        "resize",
        ("a.jpg", "b.jpg"),
        {"width": 800, "height": None, "quality": None},
    ),
    "crop_image": (
        {"source": "a.png", "output": "b.png", "x": 40, "y": 120, "width": 200, "height": 60},
        "crop",
        ("a.png", "b.png", (40, 120, 200, 60)),
        {"quality": None},
    ),
    "rotate_image": (
        {"source": "a.jpg", "output": "b.jpg", "degrees": -90},
        "rotate",
        ("a.jpg", "b.jpg", -90),
        {"quality": None},
    ),
    "flip_image": (
        {"source": "a.jpg", "output": "b.jpg", "direction": "vertical", "quality": 100},
        "flip",
        ("a.jpg", "b.jpg"),
        {"direction": "vertical", "quality": 1.0},
    ),
    "straighten_image": ({"source": "a.jpg", "output": "b.jpg"}, "straighten", ("a.jpg", "b.jpg"), {"quality": None}),
    "enhance_image": ({"source": "a.jpg", "output": "b.jpg", "quality": 0}, "enhance", ("a.jpg", "b.jpg"), {"quality": 0.0}),
    "apply_image_effect": (
        {"source": "a.jpg", "output": "b.jpg", "effect": "noir"},
        "effect",
        ("a.jpg", "b.jpg", "noir"),
        {"quality": None},
    ),
    "blur_faces_in_image": ({"source": "a.jpg", "output": "b.jpg"}, "blur_faces", ("a.jpg", "b.jpg"), {"quality": None}),
    "blur_image_background": (
        {"source": "a.jpg", "output": "b.jpg", "strength": 2},
        "blur_background",
        ("a.jpg", "b.jpg"),
        {"strength": 2.0, "quality": None},
    ),
    "replace_image_background": (
        {"source": "me.jpg", "background": "beach.jpg", "output": "b.jpg"},
        "replace_background",
        ("me.jpg", "beach.jpg", "b.jpg"),
        {"quality": None},
    ),
    "watermark_image": (
        {"source": "a.jpg", "output": "b.jpg", "text": "© 2026 Alice"},
        "watermark",
        ("a.jpg", "b.jpg", "© 2026 Alice"),
        {"color": "#ffffff", "opacity": 0.35, "quality": None},
    ),
    "make_contact_sheet": (
        {"images": ["a.jpg", "b.jpg"], "output": "sheet.jpg", "columns": 5},
        "contact_sheet",
        (["a.jpg", "b.jpg"], "sheet.jpg", 5),
        {"size": 256, "gap": 8, "background": "#ffffff"},
    ),
}


@pytest.mark.parametrize("tool", sorted(WRITERS))
async def test_image_is_written_as_asked(client: Client, monkeypatch: pytest.MonkeyPatch, tool: str) -> None:
    arguments, function, args, options = WRITERS[tool]
    recorder = Recorder()
    monkeypatch.setattr(macos.image, function, recorder.function(function, OUT))

    result = await client.call_tool(tool, arguments)

    assert not result.is_error, text(result)
    assert result.structured_content == {"path": str(OUT)}
    assert recorder.calls == [(function, args, options)]


async def test_make_qr_code(client: Client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.image, "qr_code", recorder.function("qr_code", b"\x89PNG fake"))

    arguments = {"content": "https://python.org", "output": str(tmp_path / "qr.png"), "correction": "H"}
    result = await client.call_tool("make_qr_code", arguments)

    assert not result.is_error, text(result)
    assert result.structured_content == {"path": str(tmp_path / "qr.png")}
    assert (tmp_path / "qr.png").read_bytes() == b"\x89PNG fake"
    assert recorder.calls == [("qr_code", ("https://python.org",), {"size": 512, "correction": "H"})]


@pytest.mark.parametrize(
    "error, expected",
    [
        (ValueError("the photo shows no person"), "ValueError: the photo shows no person"),
        (FileNotFoundError("a.jpg"), "FileNotFoundError: a.jpg"),
    ],
)
async def test_image_that_pymacos_refuses(
    client: Client, monkeypatch: pytest.MonkeyPatch, error: Exception, expected: str
) -> None:
    monkeypatch.setattr(macos.image, "blur_background", Recorder().function("blur_background", error=error))

    result = await client.call_tool("blur_image_background", {"source": "a.jpg", "output": "b.jpg"})

    assert result.is_error
    assert expected in text(result)


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("convert_image", {"source": "a.heic"}),
        ("convert_image", {"source": "a.heic", "output": "b.jpg", "quality": 101}),
        ("resize_image", {"source": "a.jpg", "output": "b.jpg", "width": 0}),
        ("crop_image", {"source": "a.png", "output": "b.png", "x": -1, "y": 0, "width": 1, "height": 1}),
        ("rotate_image", {"source": "a.jpg", "output": "b.jpg", "degrees": 45}),
        ("flip_image", {"source": "a.jpg", "output": "b.jpg", "direction": "diagonal"}),
        ("apply_image_effect", {"source": "a.jpg", "output": "b.jpg", "effect": "sepia"}),
        ("watermark_image", {"source": "a.jpg", "output": "b.jpg", "text": "x", "color": "white"}),
        ("watermark_image", {"source": "a.jpg", "output": "b.jpg", "text": "x", "opacity": 2}),
        ("set_image_location", {"path": "a.jpg", "latitude": 91, "longitude": 0}),
        ("make_contact_sheet", {"images": [], "output": "s.jpg"}),
        ("make_qr_code", {"content": "", "output": "q.png"}),
        ("make_qr_code", {"content": "x", "output": "q.png", "correction": "X"}),
    ],
)
async def test_images_are_not_touched_without_what_they_need(
    client: Client, monkeypatch: pytest.MonkeyPatch, tool: str, arguments: Dict[str, Any]
) -> None:
    recorder = Recorder()
    for name in macos.image.__all__:
        if callable(getattr(macos.image, name)) and not isinstance(getattr(macos.image, name), type):
            monkeypatch.setattr(macos.image, name, recorder.function(name, OUT))

    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert recorder.calls == []
