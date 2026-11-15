"""
The Finder tools against this Mac, on files of the tests' own in a temporary folder.

Nothing is moved to the Trash, no Finder window or Quick Look opens, and no setting is changed: that
would relaunch Finder in front of the user.
"""

import threading
import time
from pathlib import Path

import pytest
from mcp import Client
from mcp.types import ImageContent

from tests.helpers import png, text
from tests.live.helpers import call

pytestmark = pytest.mark.anyio


async def test_tags_alias_and_icon(client: Client, tmp_path: Path) -> None:
    file = tmp_path / "report.txt"
    file.write_text("a report")

    assert sorted((await call(client, "add_file_tags", {"path": str(file), "tags": ["Work", "Red"]}))["tags"]) == [
        "Red",
        "Work",
    ]
    tags = (await call(client, "get_finder_info", {"path": str(file)}))["tags"]
    assert sorted(tags) == ["Red", "Work"]
    assert (await call(client, "remove_file_tags", {"path": str(file), "tags": ["Red"]}))["tags"] == ["Work"]
    assert (await call(client, "set_file_tags", {"path": str(file), "tags": []}))["tags"] == []

    alias = (await call(client, "make_alias", {"target": str(file)}))["path"]
    info = await call(client, "get_finder_info", {"path": alias})
    assert info["is_alias"] is True
    assert Path(info["alias_target"]).resolve() == file.resolve()
    result = await client.call_tool("make_alias", {"target": str(file)})
    assert result.is_error and "FileExistsError" in text(result)

    icon = tmp_path / "icon.png"
    icon.write_bytes(png(64, 64))
    await call(client, "set_file_icon", {"path": str(file), "image": str(icon)})
    assert (await call(client, "get_finder_info", {"path": str(file)}))["has_custom_icon"] is True
    await call(client, "remove_file_icon", {"path": str(file)})
    assert (await call(client, "get_finder_info", {"path": str(file)}))["has_custom_icon"] is False


async def test_folder_is_zipped_and_unzipped(client: Client, tmp_path: Path) -> None:
    folder = tmp_path / "Project"
    folder.mkdir()
    (folder / "notes.txt").write_text("notes")

    archive = (await call(client, "compress_to_zip", {"path": str(folder)}))["path"]
    assert archive.endswith("Project.zip")

    out = tmp_path / "out"
    await call(client, "extract_zip", {"archive": archive, "destination": str(out)})
    assert (out / "Project" / "notes.txt").read_text() == "notes"

    # Unzipped again over itself: refused, unless asked to write over.
    result = await client.call_tool("extract_zip", {"archive": archive, "destination": str(out)})
    assert result.is_error and "FileExistsError" in text(result)
    await call(client, "extract_zip", {"archive": archive, "destination": str(out), "overwrite": True})


async def test_preview_and_largest_files(client: Client, tmp_path: Path) -> None:
    (tmp_path / "big.bin").write_bytes(b"x" * 2_000_000)
    (tmp_path / "small.bin").write_bytes(b"x" * 10)

    result = await client.call_tool("get_file_thumbnail", {"path": str(tmp_path / "small.bin"), "size": 64})
    (image,) = result.content
    assert isinstance(image, ImageContent)

    largest = await call(client, "find_largest_files", {"folder": str(tmp_path), "count": 5})
    assert [Path(found["path"]).name for found in largest] == ["big.bin"]


async def test_folder_change_is_waited_for(client: Client, tmp_path: Path) -> None:
    def later() -> None:
        time.sleep(0.5)
        (tmp_path / "export.pdf").write_text("x")

    threading.Thread(target=later).start()
    waited = await call(
        client, "wait_for_folder_change", {"folder": str(tmp_path), "pattern": ["*.pdf"], "timeout_seconds": 20}
    )

    assert waited["change"] is not None
    assert Path(waited["change"]["path"]).name == "export.pdf"

    assert await call(
        client, "wait_for_folder_change", {"folder": str(tmp_path), "pattern": ["*.mov"], "timeout_seconds": 0.5}
    ) == {"change": None}


async def test_finder_settings_are_read(client: Client) -> None:
    settings = await call(client, "get_finder_settings")

    assert settings["default_view"] in ("icons", "list", "columns", "gallery")
    assert settings["search_scope"] in ("this_mac", "current_folder", "previous")
    assert set(settings["drives_on_desktop"]) == {"internal", "external", "removable", "servers"}
    assert 16 <= settings["desktop_view"]["icon_size"] <= 128
