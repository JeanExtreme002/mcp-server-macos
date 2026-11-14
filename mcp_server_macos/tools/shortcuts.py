"""Tools that list and run the shortcuts of the Shortcuts app, from ``macos.shortcuts``."""

from pathlib import Path
from typing import Annotated, List, Optional, Sequence, Union

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._registry import LONGEST_WAIT, OPEN_ENDED, READ_ONLY, add_tool


class ShortcutResult(BaseModel):
    """What a shortcut produced."""

    output: Optional[str] = Field(
        description="The shortcut's text output. Null when it produced none, or when its output was saved to a file."
    )


def list_shortcuts(
    folder: Annotated[
        Optional[str],
        Field(description="Keep the shortcuts of a folder, by its name, or 'none' for those in no folder. All by default."),
    ] = None,
) -> List[str]:
    """List the names of the shortcuts in the Shortcuts app."""
    return macos.shortcuts.list(folder=folder)


def run_shortcut(
    name: Annotated[str, Field(description="The shortcut's name, as list_shortcuts gives it.", min_length=1)],
    input_text: Annotated[
        Optional[str], Field(description="Text to give the shortcut as its input. Not with input_files.")
    ] = None,
    input_files: Annotated[
        Optional[List[str]],
        Field(description="The paths of files to give the shortcut as its input. Not with input_text.", min_length=1),
    ] = None,
    output_path: Annotated[
        Optional[str],
        Field(description="Where to save the shortcut's output, when it's a file (an image, a PDF...) rather than text."),
    ] = None,
    timeout_seconds: Annotated[
        float,
        Field(description="How long to let it run, in seconds, before stopping it.", gt=0, le=LONGEST_WAIT),
    ] = 120.0,
) -> ShortcutResult:
    """
    Run a shortcut of the Shortcuts app, and return its text output. A shortcut is a program the user
    made or installed: it can do anything Shortcuts can, such as sending messages, changing settings
    or deleting files. Run the one the user asked for, and know what it does first.
    """
    if input_text is not None and input_files is not None:
        raise ValueError("give input_text or input_files, not both: a shortcut has one input")
    given: Union[str, Sequence[Path], None] = input_text
    if input_files is not None:
        given = [Path(path) for path in input_files]
    return ShortcutResult(output=macos.shortcuts.run(name, input=given, output=output_path, timeout=timeout_seconds))


def register(server: MCPServer) -> None:
    add_tool(server, list_shortcuts, title="List the shortcuts", annotations=READ_ONLY)
    add_tool(server, run_shortcut, title="Run a shortcut", annotations=OPEN_ENDED)
