"""The tools of mcp_server_macos.tools.vision, with macos.vision faked: no image is read."""

from pathlib import Path
from typing import Any, Dict, Tuple

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio

BOX = (0.1, 0.2, 0.3, 0.4)


# The tools that only read: each calls its function of pymacos as told, and gives its answer as JSON.
READERS: Dict[str, Tuple[Dict[str, Any], str, Any, Tuple[Any, ...], Dict[str, Any], Any]] = {
    "read_text_in_image": (
        {"image": "receipt.png", "languages": ["pt-BR"]},
        "text",
        "Total: R$ 42,00",
        ("receipt.png",),
        {"languages": ["pt-BR"], "fast": False},
        {"text": "Total: R$ 42,00"},
    ),
    "find_text_lines_in_image": (
        {"image": "slide.png", "fast": True},
        "lines",
        [macos.vision.TextLine(text="Title", confidence=0.98, box=BOX)],
        ("slide.png",),
        {"languages": None, "fast": True},
        {"result": [{"text": "Title", "confidence": 0.98, "box": list(BOX)}]},
    ),
    "list_text_languages": ({}, "languages", ["en-US", "pt-BR"], (), {"fast": False}, {"result": ["en-US", "pt-BR"]}),
    "find_barcodes": (
        {"image": "poster.jpg"},
        "barcodes",
        [
            macos.vision.Barcode(payload="https://python.org", kind="QR", box=BOX),
            macos.vision.Barcode(payload=None, kind="PDF417", box=BOX),
        ],
        ("poster.jpg",),
        {},
        {
            "result": [
                {"payload": "https://python.org", "kind": "QR", "box": list(BOX)},
                {"payload": None, "kind": "PDF417", "box": list(BOX)},
            ]
        },
    ),
    "classify_image": (
        {"image": "beach.jpg", "limit": 2, "min_confidence": 0.5},
        "classify",
        [("beach", 0.91), ("sky", 0.87)],
        ("beach.jpg",),
        {"limit": 2, "min_confidence": 0.5},
        {"result": [{"label": "beach", "confidence": 0.91}, {"label": "sky", "confidence": 0.87}]},
    ),
    "find_faces": ({"image": "group.jpg"}, "faces", [BOX], ("group.jpg",), {}, {"result": [list(BOX)]}),
    "find_animals": (
        {"image": "pets.jpg"},
        "animals",
        [macos.vision.Animal(kind="dog", confidence=0.9, box=BOX)],
        ("pets.jpg",),
        {},
        {"result": [{"kind": "dog", "confidence": 0.9, "box": list(BOX)}]},
    ),
    "compare_images": (
        {"first": "a.jpg", "second": "b.jpg"},
        "image_distance",
        0.12,
        ("a.jpg", "b.jpg"),
        {},
        {"distance": 0.12},
    ),
    "find_duplicate_images": (
        {"images": ["a.jpg", "b.jpg", "c.jpg"], "threshold": 0.5},
        "duplicates",
        [["a.jpg", "c.jpg"]],
        (["a.jpg", "b.jpg", "c.jpg"],),
        {"threshold": 0.5},
        {"result": [["a.jpg", "c.jpg"]]},
    ),
    "pick_best_shot": (
        {"images": ["a.jpg", "b.jpg"]},
        "best_shot",
        "b.jpg",
        (["a.jpg", "b.jpg"],),
        {},
        {"path": "b.jpg"},
    ),
    "get_horizon_tilt": ({"image": "beach.jpg"}, "horizon", -3.5, ("beach.jpg",), {}, {"degrees": -3.5}),
    "score_image_aesthetics": (
        {"image": "a.jpg"},
        "aesthetics",
        macos.vision.Aesthetics(score=0.42, utility=False),
        ("a.jpg",),
        {},
        {"score": 0.42, "utility": False},
    ),
    "detect_body_poses": (
        {"image": "dance.jpg"},
        "body_pose",
        [macos.vision.Pose(joints={"nose": (0.5, 0.1, 0.9)}, confidence=0.8)],
        ("dance.jpg",),
        {},
        {"result": [{"joints": {"nose": [0.5, 0.1, 0.9]}, "confidence": 0.8}]},
    ),
    "detect_hand_poses": (
        {"image": "hand.jpg", "max_hands": 1},
        "hand_pose",
        [macos.vision.Hand(side="left", joints={"thumb_tip": (0.4, 0.3, 0.7)}, confidence=0.6)],
        ("hand.jpg",),
        {"max_hands": 1},
        {"result": [{"side": "left", "joints": {"thumb_tip": [0.4, 0.3, 0.7]}, "confidence": 0.6}]},
    ),
}


@pytest.mark.parametrize("tool", sorted(READERS))
async def test_image_is_read_as_asked(client: Client, monkeypatch: pytest.MonkeyPatch, tool: str) -> None:
    arguments, function, answer, args, options, expected = READERS[tool]
    recorder = Recorder()
    monkeypatch.setattr(macos.vision, function, recorder.function(function, answer))

    result = await client.call_tool(tool, arguments)

    assert not result.is_error, text(result)
    assert result.structured_content == expected
    assert recorder.calls == [(function, args, options)]


@pytest.mark.parametrize(
    "tool, function, answer, expected",
    [
        ("pick_best_shot", "best_shot", None, {"path": None}),
        ("get_horizon_tilt", "horizon", None, {"degrees": None}),
    ],
)
async def test_nothing_found_is_an_answer(
    client: Client, monkeypatch: pytest.MonkeyPatch, tool: str, function: str, answer: Any, expected: Any
) -> None:
    monkeypatch.setattr(macos.vision, function, lambda *a, **k: answer)
    arguments = {"images": ["a.jpg"]} if tool == "pick_best_shot" else {"image": "a.jpg"}

    result = await client.call_tool(tool, arguments)

    assert not result.is_error
    assert result.structured_content == expected


@pytest.mark.parametrize(
    "tool, arguments, function, args, options",
    [
        ("remove_image_subject", {"crop": True}, "remove_background", ("dog.jpg",), {"crop": True}),
        ("scan_document_photo", {}, "scan_document", ("dog.jpg",), {}),
        ("smart_crop_image", {"width": 300, "height": 200}, "smart_crop", ("dog.jpg", 300, 200), {}),
    ],
)
async def test_picture_made_from_an_image_is_saved(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    tool: str,
    arguments: Dict[str, Any],
    function: str,
    args: Any,
    options: Any,
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.vision, function, recorder.function(function, b"\x89PNG fake"))
    output = tmp_path / "out.png"

    result = await client.call_tool(tool, {"image": "dog.jpg", "output": str(output), **arguments})

    assert not result.is_error, text(result)
    assert result.structured_content == {"path": str(output)}
    assert output.read_bytes() == b"\x89PNG fake"
    assert recorder.calls == [(function, args, options)]


@pytest.mark.parametrize(
    "tool, function, why",
    [
        ("remove_image_subject", "remove_background", "No subject stands out of the background."),
        ("scan_document_photo", "scan_document", "No document was found in the photo."),
    ],
)
async def test_nothing_to_cut_out_is_an_error_and_writes_nothing(
    client: Client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tool: str, function: str, why: str
) -> None:
    monkeypatch.setattr(macos.vision, function, lambda *a, **k: None)
    output = tmp_path / "out.png"

    result = await client.call_tool(tool, {"image": "wall.jpg", "output": str(output)})

    assert result.is_error
    assert why in text(result)
    assert not output.exists()


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("read_text_in_image", {}),
        ("read_text_in_image", {"image": ""}),
        ("classify_image", {"image": "a.jpg", "limit": 0}),
        ("classify_image", {"image": "a.jpg", "min_confidence": 2}),
        ("find_duplicate_images", {"images": []}),
        ("find_duplicate_images", {"images": ["a.jpg"], "threshold": 0}),
        ("smart_crop_image", {"image": "a.jpg", "output": "b.png", "width": 0, "height": 10}),
        ("detect_hand_poses", {"image": "a.jpg", "max_hands": 0}),
    ],
)
async def test_images_are_not_read_without_what_they_need(
    client: Client, monkeypatch: pytest.MonkeyPatch, tool: str, arguments: Dict[str, Any]
) -> None:
    recorder = Recorder()
    for name in macos.vision.__all__:
        if callable(getattr(macos.vision, name)) and not isinstance(getattr(macos.vision, name), type):
            monkeypatch.setattr(macos.vision, name, recorder.function(name))

    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert recorder.calls == []


async def test_picture_saved_over_its_source_is_written_whole(
    client: Client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "photo.png"
    source.write_bytes(b"the photo")
    monkeypatch.setattr(macos.vision, "smart_crop", lambda image, width, height: b"the crop")

    result = await client.call_tool(
        "smart_crop_image", {"image": str(source), "output": str(source), "width": 10, "height": 10}
    )

    assert not result.is_error, text(result)
    assert source.read_bytes() == b"the crop"
    assert [path.name for path in tmp_path.iterdir()] == ["photo.png"]
