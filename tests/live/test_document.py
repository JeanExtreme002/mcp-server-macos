"""The document tools against this Mac: a text file is converted, in a temporary folder, and read back."""

from pathlib import Path

import pytest
from mcp import Client

from tests.helpers import text
from tests.live.helpers import call

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("extension", [".rtf", ".docx", ".html", ".odt"])
async def test_document_is_converted_and_read_back(client: Client, tmp_path: Path, extension: str) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("Meeting minutes\nAção: revisar o contrato ✅\n", encoding="utf-8")

    output = str(tmp_path / ("notes" + extension))
    converted = await call(client, "convert_document", {"source": str(source), "output": output})

    assert Path(converted["path"]).is_file()
    read = (await call(client, "read_document_text", {"path": converted["path"]}))["text"]
    assert "Meeting minutes" in read
    assert "Ação: revisar o contrato ✅" in read


async def test_document_is_converted_to_pdf(client: Client, tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("A page of text.")

    converted = await call(
        client, "convert_document", {"source": str(source), "output": str(tmp_path / "notes.pdf"), "paper": "a4"}
    )

    assert Path(converted["path"]).read_bytes().startswith(b"%PDF")


async def test_document_that_does_not_exist(client: Client, tmp_path: Path) -> None:
    result = await client.call_tool("read_document_text", {"path": str(tmp_path / "nope.docx")})

    assert result.is_error
    assert "FileNotFoundError" in text(result)
