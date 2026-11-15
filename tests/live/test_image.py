"""The image tools against this Mac's frameworks: pictures made for the tests, in a temporary folder."""

from pathlib import Path

import pytest
from mcp import Client

from tests.helpers import png, text
from tests.live.helpers import call

pytestmark = pytest.mark.anyio


@pytest.fixture
def picture(tmp_path: Path) -> Path:
    made = tmp_path / "red.png"
    made.write_bytes(png(64, 48))
    return made


async def test_image_is_read(client: Client, picture: Path) -> None:
    info = await call(client, "get_image_info", {"path": str(picture)})

    assert (info["width"], info["height"], info["format"]) == (64, 48, "png")
    assert (info["taken_at"], info["latitude"], info["longitude"]) == (None, None, None)
    assert await call(client, "get_image_colors", {"path": str(picture), "count": 3}) == ["#ff0000"]
    assert (await call(client, "get_image_metadata", {"path": str(picture)}))["PixelWidth"] == 64


async def test_image_is_converted_resized_cropped_and_turned(client: Client, picture: Path, tmp_path: Path) -> None:
    converted = {"source": str(picture), "output": str(tmp_path / "a.jpg"), "quality": 80}
    jpeg = (await call(client, "convert_image", converted))["path"]
    assert (await call(client, "get_image_info", {"path": jpeg}))["format"] == "jpeg"

    small = (await call(client, "resize_image", {"source": str(picture), "output": str(tmp_path / "b.png"), "width": 32}))["path"]
    assert (await call(client, "get_image_info", {"path": small}))["width"] == 32

    crop = {"source": str(picture), "output": str(tmp_path / "c.png"), "x": 4, "y": 4, "width": 10, "height": 20}
    cropped = (await call(client, "crop_image", crop))["path"]
    assert [(await call(client, "get_image_info", {"path": cropped}))[side] for side in ("width", "height")] == [10, 20]

    rotated = {"source": str(picture), "output": str(tmp_path / "d.png"), "degrees": 90}
    turned = (await call(client, "rotate_image", rotated))["path"]
    assert [(await call(client, "get_image_info", {"path": turned}))[side] for side in ("width", "height")] == [48, 64]


async def test_photo_gets_a_date_and_a_place_and_loses_them(client: Client, picture: Path, tmp_path: Path) -> None:
    photo = (await call(client, "convert_image", {"source": str(picture), "output": str(tmp_path / "photo.jpg")}))["path"]

    await call(client, "set_image_date", {"path": photo, "when": "2026-09-28T14:30:00"})
    await call(client, "set_image_location", {"path": photo, "latitude": -23.55, "longitude": -46.63})
    info = await call(client, "get_image_info", {"path": photo})
    assert info["taken_at"].startswith("2026-09-28T14:30:00")
    assert (round(info["latitude"], 2), round(info["longitude"], 2)) == (-23.55, -46.63)

    clean = (await call(client, "remove_image_metadata", {"source": photo, "output": str(tmp_path / "clean.jpg")}))["path"]
    info = await call(client, "get_image_info", {"path": clean})
    assert (info["taken_at"], info["latitude"]) == (None, None)


async def test_filters_and_marks(client: Client, picture: Path, tmp_path: Path) -> None:
    for tool, arguments in (
        ("flip_image", {"direction": "vertical"}),
        ("enhance_image", {}),
        ("apply_image_effect", {"effect": "noir"}),
        ("watermark_image", {"text": "SAMPLE"}),
        ("straighten_image", {}),
        ("blur_faces_in_image", {}),
    ):
        output = tmp_path / "{}.png".format(tool)
        saved = await call(client, tool, {"source": str(picture), "output": str(output), **arguments})
        assert Path(saved["path"]).is_file(), tool

    noir = await call(client, "get_image_colors", {"path": str(tmp_path / "apply_image_effect.png"), "count": 1})
    red, green, blue = (int(noir[0][index : index + 2], 16) for index in (1, 3, 5))
    assert red == green == blue  # black and white


async def test_photo_without_a_person_has_no_background_to_blur(client: Client, picture: Path, tmp_path: Path) -> None:
    result = await client.call_tool("blur_image_background", {"source": str(picture), "output": str(tmp_path / "x.png")})

    assert result.is_error
    assert "Error" in text(result)


async def test_qr_code_and_contact_sheet(client: Client, picture: Path, tmp_path: Path) -> None:
    code = {"content": "https://python.org", "output": str(tmp_path / "qr.png"), "size": 256}
    qr = (await call(client, "make_qr_code", code))["path"]
    assert Path(qr).read_bytes().startswith(b"\x89PNG")

    sheet = {"images": [str(picture), qr], "output": str(tmp_path / "sheet.png"), "columns": 2, "size": 64, "gap": 0}
    made = (await call(client, "make_contact_sheet", sheet))["path"]
    assert (await call(client, "get_image_info", {"path": made}))["width"] == 128
