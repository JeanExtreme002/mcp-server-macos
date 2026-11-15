"""Tools that read and convert documents (Word, RTF, HTML, OpenDocument, text, PDF), from ``macos.document``."""

from typing import Annotated, Literal, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._registry import OPEN_ENDED, READ_ONLY_ONLINE, add_tool

Resources = Annotated[
    bool,
    Field(
        description="For HTML: true to fetch the page's pictures, style sheets and frames, from the web and from this "
        "Mac's files, as a browser would. Only for a page the user trusts: one could make this Mac fetch addresses "
        "of its choosing, or read local files. False reads the page alone."
    ),
]


class DocumentText(BaseModel):
    """The text of a document."""

    text: str = Field(description="The document's text.")


class Converted(BaseModel):
    """A document that was converted."""

    path: str = Field(description="The path of the converted document.")


def read_document_text(
    path: Annotated[
        str,
        Field(
            description="The document: Word (.docx, .doc), RTF, HTML, OpenDocument (.odt), a web archive or text.",
            min_length=1,
        ),
    ],
    resources: Resources = False,
) -> DocumentText:
    """Get the text of a document, without Word or LibreOffice: macOS reads it as TextEdit does. For a PDF, see the pdf tools."""
    return DocumentText(text=macos.document.text(path, resources=resources))


def convert_document(
    source: Annotated[str, Field(description="The document to convert, in any format read_document_text reads.", min_length=1)],
    output: Annotated[
        str,
        Field(
            description="Where to write the result. Its extension picks the format: .docx, .doc, .rtf, .html, .odt, "
            ".webarchive, .txt or .pdf. A file already there is replaced.",
            min_length=1,
        ),
    ],
    paper: Annotated[
        Optional[Literal["a4", "letter", "legal"]],
        Field(description="For a PDF: the paper it's laid out on. The region's, as in TextEdit, by default."),
    ] = None,
    margin_points: Annotated[
        float, Field(description="For a PDF: the margin from each edge, in points (72 is an inch).", ge=0, le=288)
    ] = 72.0,
    resources: Resources = False,
) -> Converted:
    """
    Convert a document to another format, as TextEdit would: fonts, bold, colors, lists, tables and
    pictures survive, while a Word document's headers, footers and page layout don't.
    """
    return Converted(
        path=str(macos.document.convert(source, output, paper=paper, margin=margin_points, resources=resources))
    )


def register(server: MCPServer) -> None:
    # HTML is read by WebKit, which macOS only allows on the main thread. With resources, a page is
    # fetched from the web as a browser would: they reach beyond this Mac. Converting also writes a file,
    # over the one that may be there, so it's marked as cautiously as can be.
    add_tool(server, read_document_text, title="Read a document's text", annotations=READ_ONLY_ONLINE, main_thread=True)
    add_tool(server, convert_document, title="Convert a document", annotations=OPEN_ENDED, main_thread=True)
