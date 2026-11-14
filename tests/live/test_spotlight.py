"""The Spotlight tools against this Mac: files are looked for, and a file's metadata read."""

from pathlib import Path

import pytest
from mcp import Client

from tests.helpers import text
from tests.live.helpers import call

pytestmark = pytest.mark.anyio


async def test_get_file_metadata(client: Client, tmp_path: Path) -> None:
    file = tmp_path / "notes.txt"
    file.write_text("seven b")

    metadata = await call(client, "get_file_metadata", {"path": str(file)})

    # A temporary folder isn't indexed: the file has the basic attributes, which every file has.
    assert metadata["kMDItemFSName"] == "notes.txt"
    assert metadata["kMDItemFSSize"] == 7
    assert isinstance(metadata["kMDItemFSContentChangeDate"], str)  # a date, as text


async def test_get_file_metadata_of_a_missing_file(client: Client, tmp_path: Path) -> None:
    result = await client.call_tool("get_file_metadata", {"path": str(tmp_path / "nope.txt")})

    assert result.is_error
    assert "FileNotFoundError" in text(result)


async def test_searches_answer(client: Client) -> None:
    # What Spotlight has indexed on this machine isn't known (little, on a fresh one): only that the
    # searches answer with paths, and no more than asked for.
    for tool, arguments in (
        ("search_files", {"query": "kind:application", "limit": 3}),
        ("search_files_by_name", {"name": ".app", "folder": "/System/Applications", "limit": 3}),
    ):
        found = await call(client, tool, arguments)
        assert len(found) <= 3
        assert all(path.startswith("/") for path in found)
