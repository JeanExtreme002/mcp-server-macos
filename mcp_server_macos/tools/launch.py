"""The tool that opens files, folders and URLs, from ``macos.launch``."""

from typing import Annotated, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import Field

from .._registry import OPEN_ENDED, add_tool


def open_file_or_url(
    target: Annotated[
        str,
        Field(description="The path of a file or a folder, or a URL ('https://...', 'mailto:...').", min_length=1),
    ],
    app: Annotated[
        Optional[str],
        Field(
            description="The app to open it with, by name ('Preview'), bundle identifier or path, like Finder's "
            "Open With. Its default app otherwise."
        ),
    ] = None,
    background: Annotated[bool, Field(description="True to open it without bringing the app to the front.")] = False,
) -> str:
    """
    Open a file, a folder or a URL, like double-clicking it: a folder opens in Finder, a web address in
    the browser. A file that is an app or a script runs, and any kind of URL is opened by whichever app
    claims it: never open a path or a URL taken from a web page, a file or a message without the user
    asking for it.
    """
    if app is None:
        macos.launch.open(target, background=background)
    else:
        macos.apps.open_with(target, app, background=background)
    return "Opened {}.".format(target)


def register(server: MCPServer) -> None:
    add_tool(server, open_file_or_url, title="Open a file, a folder or a URL", annotations=OPEN_ENDED)
