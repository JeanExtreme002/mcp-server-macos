"""Tools that search files with Spotlight and read their metadata, from ``macos.spotlight``."""

from typing import Annotated, Any, Dict, List, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import Field

from .._registry import READ_ONLY, add_tool
from .._values import plain

# A search that's still going after this many seconds (Spotlight stuck, a slow network volume) is stopped.
SEARCH_TIMEOUT = 60.0

Folder = Annotated[
    Optional[str],
    Field(description="Search in this folder only, and the folders in it. Everywhere Spotlight indexes by default."),
]
Limit = Annotated[int, Field(description="How many files to return, at most.", ge=1, le=1000)]


def search_files(
    query: Annotated[
        str,
        Field(
            description="What the Spotlight bar takes: plain words, matched against names and contents; filters "
            "such as 'kind:pdf' or 'date:today'; or a raw metadata query like 'kMDItemPixelHeight > 1000'.",
            min_length=1,
        ),
    ],
    folder: Folder = None,
    limit: Limit = 50,
) -> List[str]:
    """
    Search the Mac's files with Spotlight, by name, content, kind or metadata, and return their paths.
    Only what Spotlight indexes is found. For a part of the name alone, search_files_by_name is exact.
    """
    found = macos.spotlight.search(query, folder=folder, limit=limit, timeout=SEARCH_TIMEOUT)
    return [str(path) for path in found]


def search_files_by_name(
    name: Annotated[
        str,
        Field(
            description="A part of the file's name, extension included: 'report', 'report.pdf', 'Calculator.app'. "
            "Case and accents don't matter.",
            min_length=1,
        ),
    ],
    folder: Folder = None,
    limit: Limit = 50,
) -> List[str]:
    """Find the files whose name contains a text, with Spotlight, and return their paths."""
    found = macos.spotlight.search_name(name, folder=folder, limit=limit, timeout=SEARCH_TIMEOUT)
    return [str(path) for path in found]


def get_file_metadata(
    path: Annotated[str, Field(description="The path of a file or a folder.", min_length=1)],
) -> Dict[str, Any]:
    """
    Get what Spotlight knows of a file: its kind, size, dates, and what its kind has, such as an image's
    dimensions, a PDF's pages or a song's artist. The names are Spotlight's own (kMDItemContentType,
    kMDItemPixelHeight...) and the dates are in UTC. A file Spotlight doesn't index only has the basic
    ones (kMDItemFS...).
    """
    metadata: Dict[str, Any] = plain(macos.spotlight.metadata(path))
    return metadata


def register(server: MCPServer) -> None:
    add_tool(server, search_files, title="Search files with Spotlight", annotations=READ_ONLY)
    add_tool(server, search_files_by_name, title="Find files by name", annotations=READ_ONLY)
    add_tool(server, get_file_metadata, title="Get a file's metadata", annotations=READ_ONLY)
