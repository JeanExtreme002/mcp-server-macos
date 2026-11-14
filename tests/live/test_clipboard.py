"""The clipboard tools against this Mac: the text on the clipboard is put back afterwards."""

import base64
from pathlib import Path
from typing import AsyncIterator

import macos
import pytest
from mcp import Client
from mcp.types import ImageContent

from tests.helpers import png, text

pytestmark = pytest.mark.anyio


@pytest.fixture
async def restored() -> AsyncIterator[None]:
    """
    Put back the text the clipboard held (an image or files on it are lost, as in pymacos's own tests).

    It's put back as sensitive: it may be a password that was copied as one, and whether it was can't
    be read back. Marked so without need, a text only stays out of clipboard managers' histories;
    left unmarked, a password would get into them.
    """
    before = macos.clipboard.paste()
    yield
    if before is None:
        macos.clipboard.clear()
    else:
        macos.clipboard.copy(before, sensitive=True)


@pytest.mark.usefixtures("restored")
async def test_text_goes_to_the_clipboard_and_back(client: Client) -> None:
    before = (await client.call_tool("get_clipboard", {})).structured_content
    assert before is not None

    result = await client.call_tool("set_clipboard", {"text": "mcp-server-macos — \"live\" ✅"})
    assert not result.is_error, text(result)

    after = (await client.call_tool("get_clipboard", {})).structured_content
    assert after is not None
    assert after["text"] == "mcp-server-macos — \"live\" ✅"
    assert after["files"] == []
    assert after["change_count"] > before["change_count"]


@pytest.mark.usefixtures("restored")
async def test_clipboard_is_cleared(client: Client) -> None:
    await client.call_tool("set_clipboard", {"text": "to be cleared"})

    result = await client.call_tool("clear_clipboard", {})
    assert not result.is_error, text(result)

    after = (await client.call_tool("get_clipboard", {})).structured_content
    assert after is not None
    assert (after["text"], after["has_image"], after["files"]) == (None, False, [])

    result = await client.call_tool("get_clipboard_image", {})
    assert result.is_error
    assert "The clipboard holds no image." in text(result)


@pytest.mark.usefixtures("restored")
async def test_files_go_to_the_clipboard_and_back(client: Client, tmp_path: Path) -> None:
    first, second = tmp_path / "a b.txt", tmp_path / "c.txt"
    first.write_text("a")
    second.write_text("c")

    result = await client.call_tool("copy_files_to_clipboard", {"paths": [str(first), str(second)]})
    assert not result.is_error, text(result)

    after = (await client.call_tool("get_clipboard", {})).structured_content
    assert after is not None
    assert [Path(path).resolve() for path in after["files"]] == [first.resolve(), second.resolve()]


@pytest.mark.usefixtures("restored")
async def test_missing_file_is_refused_and_the_clipboard_kept(client: Client, tmp_path: Path) -> None:
    await client.call_tool("set_clipboard", {"text": "kept"})

    result = await client.call_tool("copy_files_to_clipboard", {"paths": [str(tmp_path / "nope.txt")]})

    assert result.is_error
    assert "FileNotFoundError" in text(result)
    after = (await client.call_tool("get_clipboard", {})).structured_content
    assert after is not None and after["text"] == "kept"


@pytest.mark.usefixtures("restored")
async def test_image_goes_to_the_clipboard_and_back(client: Client, tmp_path: Path) -> None:
    picture = tmp_path / "red.png"
    picture.write_bytes(png())

    result = await client.call_tool("copy_image_to_clipboard", {"path": str(picture)})
    assert not result.is_error, text(result)

    after = (await client.call_tool("get_clipboard", {})).structured_content
    assert after is not None and after["has_image"] is True

    result = await client.call_tool("get_clipboard_image", {})
    assert not result.is_error, text(result)
    (image,) = result.content
    assert isinstance(image, ImageContent)
    assert image.mime_type == "image/png"
    assert base64.b64decode(image.data).startswith(b"\x89PNG")


@pytest.mark.usefixtures("restored")
async def test_waiting_for_a_copy_that_does_not_come(client: Client) -> None:
    result = await client.call_tool("wait_for_clipboard_change", {"timeout_seconds": 0.5})

    assert result.is_error
    assert "WaitTimeoutError" in text(result)
