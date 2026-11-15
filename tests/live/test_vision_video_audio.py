"""
The vision, video and audio tools against this Mac's frameworks, on files made for the tests.

Nothing is recorded from the microphone, and no audio device is switched: the devices are only read.
"""

from pathlib import Path

import macos
import pytest
from mcp import Client
from mcp.types import ImageContent

from tests.helpers import png, text
from tests.live.helpers import call

pytestmark = pytest.mark.anyio


@pytest.fixture
def pictures(tmp_path: Path) -> Path:
    """A red picture, a QR code, and a page of text drawn as a picture."""
    (tmp_path / "red.png").write_bytes(png(64, 48))
    (tmp_path / "qr.png").write_bytes(macos.image.qr_code("https://python.org", size=300))
    return tmp_path


async def test_codes_and_text_are_read_from_pictures(client: Client, pictures: Path) -> None:
    (code,) = await call(client, "find_barcodes", {"image": str(pictures / "qr.png")})
    assert (code["payload"], code["kind"]) == ("https://python.org", "QR")

    # A page of text, drawn by the document and PDF tools, read back as a picture.
    source = pictures / "page.txt"
    source.write_text("Invoice number 4217\nTotal due: 98.50\n")
    pdf = (await call(client, "convert_document", {"source": str(source), "output": str(pictures / "page.pdf")}))[
        "path"
    ]
    result = await client.call_tool("render_pdf_page", {"path": pdf, "size": 1600})
    (image,) = result.content
    assert isinstance(image, ImageContent)
    page = pictures / "page.png"
    page.write_bytes(macos.pdf.render(pdf, 1, size=1600))

    read = (await call(client, "read_text_in_image", {"image": str(page)}))["text"]
    assert "Invoice number 4217" in read
    lines = await call(client, "find_text_lines_in_image", {"image": str(page), "fast": True})
    assert any("Total due" in line["text"] for line in lines)
    assert "en-US" in await call(client, "list_text_languages")


async def test_pictures_are_compared(client: Client, pictures: Path) -> None:
    red, qr = str(pictures / "red.png"), str(pictures / "qr.png")

    assert (await call(client, "compare_images", {"first": red, "second": red}))["distance"] == 0
    assert await call(client, "find_duplicate_images", {"images": [red, qr, red]}) == [[red, red]]
    assert await call(client, "find_faces", {"image": red}) == []
    assert await call(client, "pick_best_shot", {"images": [red, qr]}) == {"path": None}

    cropped = await call(
        client, "smart_crop_image", {"image": qr, "output": str(pictures / "c.png"), "width": 50, "height": 50}
    )
    assert Path(cropped["path"]).read_bytes().startswith(b"\x89PNG")

    result = await client.call_tool("scan_document_photo", {"image": red, "output": str(pictures / "scan.png")})
    assert result.is_error
    assert not (pictures / "scan.png").exists()


async def test_video_is_made_read_and_edited(client: Client, pictures: Path) -> None:
    images = [str(pictures / "red.png"), str(pictures / "qr.png")] * 4
    clip = (
        await call(
            client, "images_to_video", {"images": images, "output": str(pictures / "clip.mp4"), "fps": 4, "width": 128}
        )
    )["path"]

    info = await call(client, "get_video_info", {"path": clip})
    assert (info["width"], info["duration_seconds"], info["has_audio"]) == (128, 2.0, False)

    result = await client.call_tool("get_video_frame", {"path": clip, "at_seconds": 0.5, "size": 64})
    assert not result.is_error, text(result)
    frames = await call(
        client, "save_video_frames", {"path": clip, "folder": str(pictures / "frames"), "every_seconds": 1}
    )
    assert len(frames["paths"]) >= 2

    for tool, arguments, extension in (
        ("trim_video", {"start": 0.5, "duration": 1}, ".mov"),
        ("rotate_video", {"degrees": 90}, ".mov"),
        ("mute_video", {}, ".mov"),
        ("video_to_gif", {"width": 64}, ".gif"),
        ("convert_video", {"quality": "low"}, ".mp4"),
    ):
        saved = await call(client, tool, {"source": clip, "output": str(pictures / (tool + extension)), **arguments})
        assert Path(saved["path"]).stat().st_size > 0, tool

    turned = await call(client, "get_video_info", {"path": str(pictures / "rotate_video.mov")})
    assert (turned["width"], turned["height"]) == (96, 128)


async def test_audio_file_is_made_read_and_edited(client: Client, tmp_path: Path) -> None:
    spoken = (
        await call(client, "save_speech", {"text": "Hello from the tests.", "path": str(tmp_path / "hello.aiff")})
    )["path"]

    info = await call(client, "get_audio_info", {"path": spoken})
    assert info["duration_seconds"] > 0.5
    labels = [label["label"] for label in await call(client, "classify_audio", {"path": spoken, "limit": 3})]
    assert "speech" in labels

    for tool, arguments in (
        ("convert_audio", {"quality": "low"}),
        ("change_audio_volume", {"decibels": -6}),
        ("trim_audio", {"start": 0.1, "duration": 0.5}),
        ("fade_audio", {"fade_in_seconds": 0.2}),
        ("reverse_audio", {}),
        ("change_audio_speed", {"factor": 1.5}),
    ):
        saved = await call(client, tool, {"source": spoken, "output": str(tmp_path / (tool + ".m4a")), **arguments})
        assert Path(saved["path"]).stat().st_size > 0, tool

    trimmed = await call(client, "get_audio_info", {"path": str(tmp_path / "trim_audio.m4a")})
    assert 0.3 < trimmed["duration_seconds"] < 0.8


async def test_audio_devices_are_read(client: Client) -> None:
    status = await call(client, "get_audio_status")

    uids = {device["uid"] for device in status["outputs"] + status["inputs"]}
    assert status["default_output"] is None or status["default_output"] in uids
    assert isinstance(status["microphone_permission"], bool)
