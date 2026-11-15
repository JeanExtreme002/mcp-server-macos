"""The PDF tools against this Mac's frameworks: PDFs made for the tests, in a temporary folder."""

from pathlib import Path

import pytest
from mcp import Client
from mcp.types import ImageContent

from tests.helpers import png, text
from tests.live.helpers import call

pytestmark = pytest.mark.anyio


@pytest.fixture
async def contract(client: Client, tmp_path: Path) -> str:
    """A one-page PDF with some text, made from a text file."""
    source = tmp_path / "contract.txt"
    source.write_text("Contract between Jane Doe and Acme.\nJane Doe signs here: ID 123-45-6789.\nSignature:\n")
    converted = await call(client, "convert_document", {"source": str(source), "output": str(tmp_path / "contract.pdf")})
    return str(converted["path"])


async def test_pdf_is_read(client: Client, contract: str) -> None:
    assert (await call(client, "get_pdf_info", {"path": contract}))["pages"] == 1
    assert "Jane Doe signs here" in (await call(client, "read_pdf_text", {"path": contract}))["text"]

    hits = await call(client, "find_in_pdf", {"path": contract, "text": "jane doe"})
    assert [hit["text"] for hit in hits] == ["Jane Doe", "Jane Doe"]
    assert len(await call(client, "find_in_pdf", {"path": contract, "text": r"\d{3}-\d{2}-\d{4}", "regex": True})) == 1

    result = await client.call_tool("render_pdf_page", {"path": contract, "size": 256})
    assert not result.is_error, text(result)
    (image,) = result.content
    assert isinstance(image, ImageContent)


async def test_text_is_redacted_for_good(client: Client, contract: str, tmp_path: Path) -> None:
    done = await call(client, "redact_pdf", {"path": contract, "output": str(tmp_path / "public.pdf"), "targets": ["Jane Doe"]})

    assert done["matches"] == {"Jane Doe": 2}
    assert "Jane Doe" not in (await call(client, "read_pdf_text", {"path": done["path"]}))["text"]

    result = await client.call_tool("redact_pdf", {"path": contract, "output": str(tmp_path / "x.pdf"), "targets": ["Nobody"]})
    assert result.is_error
    assert not (tmp_path / "x.pdf").exists()


async def test_text_is_replaced_in_one_place_only(client: Client, contract: str, tmp_path: Path) -> None:
    done = await call(
        client,
        "replace_in_pdf",
        {"path": contract, "output": str(tmp_path / "r.pdf"), "replacements": {"Jane Doe": "Maria Lima"}, "occurrences": [2]},
    )

    assert done["matches"] == {"Jane Doe": 1}
    hits = await call(client, "find_in_pdf", {"path": done["path"], "text": "Maria Lima"})
    assert len(hits) == 1


async def test_some_places_of_a_pattern_are_replaced_with_its_groups(client: Client, contract: str, tmp_path: Path) -> None:
    done = await call(
        client,
        "replace_in_pdf",
        {
            "path": contract,
            "output": str(tmp_path / "g.pdf"),
            "replacements": {r"Jane (\w+)": r"Maria \1"},
            "regex": True,
            "occurrences": [1],
        },
    )

    assert done["matches"] == {"Jane Doe": 1} or sum(done["matches"].values()) == 1
    assert len(await call(client, "find_in_pdf", {"path": done["path"], "text": "Maria Doe"})) == 1


async def test_pages_are_merged_extracted_and_turned(client: Client, contract: str, tmp_path: Path) -> None:
    merged = (await call(client, "merge_pdfs", {"inputs": [contract, contract], "output": str(tmp_path / "m.pdf")}))["path"]
    assert (await call(client, "get_pdf_info", {"path": merged}))["pages"] == 2

    second = (await call(client, "extract_pdf_pages", {"path": merged, "output": str(tmp_path / "e.pdf"), "pages": [2]}))["path"]
    assert (await call(client, "get_pdf_info", {"path": second}))["pages"] == 1

    rotated = {"path": merged, "output": str(tmp_path / "t.pdf"), "degrees": 90, "pages": [1]}
    turned = await call(client, "rotate_pdf_pages", rotated)
    assert Path(turned["path"]).is_file()


async def test_pdf_is_encrypted_and_opened_with_its_password(client: Client, contract: str, tmp_path: Path) -> None:
    encrypted = {"path": contract, "output": str(tmp_path / "l.pdf"), "password": "1234"}
    locked = (await call(client, "encrypt_pdf", encrypted))["path"]

    result = await client.call_tool("get_pdf_info", {"path": locked})
    assert result.is_error
    assert "encrypted" in text(result)
    assert "System Settings" not in text(result)  # a password to give, not an app to allow

    assert (await call(client, "get_pdf_info", {"path": locked, "password": "1234"}))["pages"] == 1

    decrypted = {"path": locked, "output": str(tmp_path / "o.pdf"), "password": "1234"}
    opened = (await call(client, "decrypt_pdf", decrypted))["path"]
    assert "Jane Doe" in (await call(client, "read_pdf_text", {"path": opened}))["text"]


async def test_pdf_is_marked_signed_and_given_contents(client: Client, contract: str, tmp_path: Path) -> None:
    signature = tmp_path / "signature.png"
    signature.write_bytes(png(40, 20))

    for tool, arguments in (
        ("watermark_pdf", {"text": "DRAFT"}),
        ("compress_pdf", {}),
        ("grayscale_pdf", {}),
        ("add_text_to_pdf", {"text": "Received", "position": "top_right"}),
        ("add_text_to_pdf", {"text": "Jane", "position": [100, 100]}),
        ("sign_pdf", {"image": str(signature), "near": "Signature:"}),
    ):
        output = tmp_path / "{}-{}.pdf".format(tool, len(arguments))
        saved = await call(client, tool, {"path": contract, "output": str(output), **arguments})
        assert Path(saved["path"]).is_file(), tool

    marks = [{"title": "Contract", "page": 1}, {"title": "Parties", "page": 1, "level": 1}, {"title": "Annex", "page": 0}]
    given = {"path": contract, "output": str(tmp_path / "b.pdf"), "bookmarks": marks}
    marked = (await call(client, "set_pdf_bookmarks", given))["path"]
    listed = await call(client, "list_pdf_bookmarks", {"path": marked})
    assert listed == [{**marks[0], "level": 0}, marks[1], {**marks[2], "level": 0}]
    # What was listed is written back as it is, the heading of page 0 included.
    again = {"path": contract, "output": str(tmp_path / "b2.pdf"), "bookmarks": listed}
    assert await call(client, "list_pdf_bookmarks", {"path": (await call(client, "set_pdf_bookmarks", again))["path"]}) == listed
    assert await call(client, "list_pdf_form_fields", {"path": contract}) == []


async def test_pdf_is_made_from_images_and_gives_them_back(client: Client, tmp_path: Path) -> None:
    pictures = []
    for index, size in enumerate(((40, 30), (20, 50))):
        picture = tmp_path / "{}.png".format(index)
        picture.write_bytes(png(*size))
        pictures.append(str(picture))

    made = (await call(client, "images_to_pdf", {"images": pictures, "output": str(tmp_path / "scan.pdf")}))["path"]
    assert (await call(client, "get_pdf_info", {"path": made}))["pages"] == 2

    saved = await call(client, "extract_pdf_images", {"path": made, "folder": str(tmp_path / "out")})
    assert len(saved["paths"]) == 2
    assert all(Path(path).is_file() for path in saved["paths"])
