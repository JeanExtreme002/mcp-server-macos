"""The tools of mcp_server_macos.tools.clipboard, with macos.clipboard faked."""

import base64
from pathlib import Path
from typing import Any, Dict, Optional

import macos
import pytest
from mcp import Client
from mcp.types import ImageContent

from tests.helpers import Recorder, png, text

pytestmark = pytest.mark.anyio

PNG = png()


@pytest.fixture
def clipboard(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    """An empty clipboard, and the calls made to the functions of macos.clipboard that change it."""
    recorder = Recorder()
    monkeypatch.setattr(macos.clipboard, "paste", lambda: None)
    monkeypatch.setattr(macos.clipboard, "has_image", lambda: False)
    monkeypatch.setattr(macos.clipboard, "paste_files", lambda: [])
    monkeypatch.setattr(macos.clipboard, "paste_image", lambda: None)
    monkeypatch.setattr(macos.clipboard, "change_count", lambda: 41)
    for name in ("copy", "copy_files", "copy_image", "clear"):
        monkeypatch.setattr(macos.clipboard, name, recorder.function(name))
    return recorder


async def test_get_clipboard_when_empty(client: Client, clipboard: Recorder) -> None:
    result = await client.call_tool("get_clipboard", {})

    assert not result.is_error
    assert result.structured_content == {"text": None, "has_image": False, "files": [], "change_count": 41}
    assert clipboard.calls == []


async def test_get_clipboard_with_text(client: Client, clipboard: Recorder, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(macos.clipboard, "paste", lambda: "héllo\n\"world\" 🍎")

    result = await client.call_tool("get_clipboard", {})

    assert result.structured_content == {
        "text": "héllo\n\"world\" 🍎",
        "has_image": False,
        "files": [],
        "change_count": 41,
    }


async def test_get_clipboard_with_files_and_an_image(
    client: Client, clipboard: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(macos.clipboard, "has_image", lambda: True)
    monkeypatch.setattr(macos.clipboard, "paste_files", lambda: [Path("/Users/me/a b.txt"), Path("/tmp/photo.png")])

    result = await client.call_tool("get_clipboard", {})

    # Paths as text: JSON has no path type.
    assert result.structured_content == {
        "text": None,
        "has_image": True,
        "files": ["/Users/me/a b.txt", "/tmp/photo.png"],
        "change_count": 41,
    }


async def test_get_clipboard_image(client: Client, clipboard: Recorder, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(macos.clipboard, "paste_image", lambda: PNG)

    result = await client.call_tool("get_clipboard_image", {})

    assert not result.is_error
    (image,) = result.content
    assert isinstance(image, ImageContent)
    assert image.mime_type == "image/png"
    assert base64.b64decode(image.data) == PNG


async def test_get_clipboard_image_when_there_is_none(client: Client, clipboard: Recorder) -> None:
    result = await client.call_tool("get_clipboard_image", {})

    assert result.is_error
    assert "The clipboard holds no image." in text(result)


async def test_get_clipboard_image_that_macos_cannot_read(
    client: Client, clipboard: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    def paste_image() -> bytes:
        raise macos.MacOSError("could not convert the image on the clipboard to PNG")

    monkeypatch.setattr(macos.clipboard, "paste_image", paste_image)

    result = await client.call_tool("get_clipboard_image", {})

    assert result.is_error
    assert "MacOSError: could not convert the image on the clipboard to PNG" in text(result)


async def test_set_clipboard(client: Client, clipboard: Recorder) -> None:
    result = await client.call_tool("set_clipboard", {"text": "It's \"copied\" — $(id) ✅"})

    assert not result.is_error
    assert text(result) == "Text copied to the clipboard."
    assert clipboard.calls == [("copy", ("It's \"copied\" — $(id) ✅",), {"sensitive": False})]


async def test_set_clipboard_with_a_password(client: Client, clipboard: Recorder) -> None:
    result = await client.call_tool("set_clipboard", {"text": "hunter2", "sensitive": True})

    assert not result.is_error
    assert clipboard.calls == [("copy", ("hunter2",), {"sensitive": True})]
    # What was copied isn't said back.
    assert "hunter2" not in text(result)


async def test_set_clipboard_takes_empty_text(client: Client, clipboard: Recorder) -> None:
    result = await client.call_tool("set_clipboard", {"text": ""})

    assert not result.is_error
    assert clipboard.calls == [("copy", ("",), {"sensitive": False})]


@pytest.mark.parametrize("arguments", [{}, {"text": None}, {"text": ["a"]}, {"text": "a", "sensitive": "maybe"}])
async def test_set_clipboard_refuses_what_is_not_text(
    client: Client, clipboard: Recorder, arguments: Dict[str, Any]
) -> None:
    result = await client.call_tool("set_clipboard", arguments)

    assert result.is_error
    assert clipboard.calls == []


@pytest.mark.parametrize(
    "paths, said",
    [
        (["/Users/me/report.pdf"], "1 file copied to the clipboard."),
        (["/Users/me/a b.txt", "/tmp/photo.png", "/tmp"], "3 files copied to the clipboard."),
    ],
)
async def test_copy_files_to_clipboard(client: Client, clipboard: Recorder, paths: Any, said: str) -> None:
    result = await client.call_tool("copy_files_to_clipboard", {"paths": paths})

    assert not result.is_error
    assert text(result) == said
    assert clipboard.calls == [("copy_files", (paths,), {})]


@pytest.mark.parametrize("arguments", [{}, {"paths": []}, {"paths": "/Users/me/report.pdf"}, {"paths": [1]}])
async def test_copy_files_to_clipboard_refuses_what_is_not_a_list_of_paths(
    client: Client, clipboard: Recorder, arguments: Dict[str, Any]
) -> None:
    result = await client.call_tool("copy_files_to_clipboard", arguments)

    assert result.is_error
    assert clipboard.calls == []


@pytest.mark.parametrize(
    "error, expected",
    [
        (FileNotFoundError(2, "No such file or directory", "/nope.txt"), "FileNotFoundError"),
        (PermissionError(13, "Permission denied", "/private/x"), "PermissionError"),
    ],
)
async def test_copy_files_to_clipboard_reports_a_file_it_cannot_take(
    client: Client, monkeypatch: pytest.MonkeyPatch, error: Exception, expected: str
) -> None:
    monkeypatch.setattr(macos.clipboard, "copy_files", Recorder().function("copy_files", error=error))

    result = await client.call_tool("copy_files_to_clipboard", {"paths": ["/nope.txt"]})

    assert result.is_error
    assert expected in text(result)
    # A file that can't be read is the caller's to fix, not a permission of macOS to ask the user for.
    assert "Only the user can grant a permission" not in text(result)


async def test_copy_image_to_clipboard(client: Client, clipboard: Recorder) -> None:
    result = await client.call_tool("copy_image_to_clipboard", {"path": "/Users/me/photo.heic"})

    assert not result.is_error
    assert text(result) == "Image copied to the clipboard."
    assert clipboard.calls == [("copy_image", ("/Users/me/photo.heic",), {})]


async def test_copy_image_to_clipboard_reports_a_missing_file(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    error = FileNotFoundError(2, "No such file or directory", "/nope.png")
    monkeypatch.setattr(macos.clipboard, "copy_image", Recorder().function("copy_image", error=error))

    result = await client.call_tool("copy_image_to_clipboard", {"path": "/nope.png"})

    assert result.is_error
    assert "FileNotFoundError" in text(result)
    assert "/nope.png" in text(result)


async def test_clear_clipboard(client: Client, clipboard: Recorder) -> None:
    result = await client.call_tool("clear_clipboard", {})

    assert not result.is_error
    assert text(result) == "Clipboard cleared."
    assert clipboard.calls == [("clear", (), {})]


@pytest.mark.parametrize("copied", ["something new", None])
async def test_wait_for_clipboard_change(
    client: Client, monkeypatch: pytest.MonkeyPatch, copied: Optional[str]
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.clipboard, "wait_for_change", recorder.function("wait_for_change", copied))

    result = await client.call_tool("wait_for_clipboard_change", {})

    assert not result.is_error
    assert result.structured_content == {"text": copied}
    assert recorder.calls == [("wait_for_change", (), {"timeout": 60.0, "include_sensitive": True})]


async def test_wait_for_clipboard_change_for_a_given_time(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.clipboard, "wait_for_change", recorder.function("wait_for_change", "x"))

    await client.call_tool("wait_for_clipboard_change", {"timeout_seconds": 2.5, "include_sensitive": False})

    assert recorder.calls == [("wait_for_change", (), {"timeout": 2.5, "include_sensitive": False})]


@pytest.mark.parametrize("timeout", [0, -1, 600.1, 86400, "soon"])
async def test_wait_for_clipboard_change_does_not_wait_forever(
    client: Client, monkeypatch: pytest.MonkeyPatch, timeout: Any
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.clipboard, "wait_for_change", recorder.function("wait_for_change", "x"))

    result = await client.call_tool("wait_for_clipboard_change", {"timeout_seconds": timeout})

    assert result.is_error
    assert recorder.calls == []


async def test_wait_for_clipboard_change_when_nothing_is_copied(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    error = macos.WaitTimeoutError("nothing was copied within 60 seconds")
    monkeypatch.setattr(macos.clipboard, "wait_for_change", Recorder().function("wait_for_change", error=error))

    result = await client.call_tool("wait_for_clipboard_change", {})

    assert result.is_error
    assert "WaitTimeoutError: nothing was copied within 60 seconds" in text(result)
