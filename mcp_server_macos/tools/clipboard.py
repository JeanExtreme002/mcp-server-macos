"""Tools for the clipboard, from ``macos.clipboard``."""

from typing import Annotated, List, Optional

import macos
from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from .._registry import LONGEST_WAIT, READ_ONLY, REPLACING, add_tool


class Clipboard(BaseModel):
    """What the clipboard holds."""

    text: Optional[str] = Field(description="The text on the clipboard. Null when it holds no text (an image, say).")
    has_image: bool = Field(description="Whether it holds an image, which get_clipboard_image returns.")
    files: List[str] = Field(description="The paths of the files on it, as when copied in Finder. Empty when none.")
    change_count: int = Field(
        description="A counter that goes up each time any app changes the clipboard: compare two readings to "
        "know whether something was copied in between."
    )


class Copied(BaseModel):
    """Something new on the clipboard."""

    text: Optional[str] = Field(
        description="The text that was copied. Null when what was copied isn't text (an image, files...)."
    )


def get_clipboard() -> Clipboard:
    """
    Read the clipboard: its text, whether it holds an image, and the files on it. What the user copied
    last may be private (a password, a message): read it when the task calls for it.
    """
    return Clipboard(
        text=macos.clipboard.paste(),
        has_image=macos.clipboard.has_image(),
        files=[str(path) for path in macos.clipboard.paste_files()],
        change_count=macos.clipboard.change_count(),
    )


def get_clipboard_image() -> Image:
    """Get the image on the clipboard, as a PNG. Fails when the clipboard holds no image."""
    image = macos.clipboard.paste_image()
    if image is None:
        raise ToolError("The clipboard holds no image.")
    return Image(data=image, format="png")


def set_clipboard(
    text: Annotated[str, Field(description="The text to put on the clipboard.")],
    sensitive: Annotated[
        bool,
        Field(
            description="True for a password or a token: clipboard managers are asked not to show it or keep it "
            "in their history. Any app can still read it, so clear the clipboard after use."
        ),
    ] = False,
) -> str:
    """Put text on the clipboard, replacing what it held, for the user to paste."""
    macos.clipboard.copy(text, sensitive=sensitive)
    return "Text copied to the clipboard."


def copy_files_to_clipboard(
    paths: Annotated[
        List[str],
        Field(description="The paths of the files and folders to copy. They must exist.", min_length=1),
    ],
) -> str:
    """
    Put files on the clipboard, replacing what it held, as if they were copied in Finder: pasting in
    Finder copies them there, and apps like Mail attach them.
    """
    macos.clipboard.copy_files(paths)
    return "{} copied to the clipboard.".format("1 file" if len(paths) == 1 else "{} files".format(len(paths)))


def copy_image_to_clipboard(
    path: Annotated[
        str,
        Field(description="The path of the image file, in any format macOS opens (PNG, JPEG, HEIC, GIF, TIFF, PDF...)."),
    ],
) -> str:
    """
    Put an image on the clipboard, from a file, replacing what it held. Other apps get it as an image
    copied in Preview, not as a file.
    """
    macos.clipboard.copy_image(path)
    return "Image copied to the clipboard."


def clear_clipboard() -> str:
    """Empty the clipboard. What it held is gone."""
    macos.clipboard.clear()
    return "Clipboard cleared."


def wait_for_clipboard_change(
    timeout_seconds: Annotated[
        float,
        Field(description="How long to wait, in seconds, before giving up.", gt=0, le=LONGEST_WAIT),
    ] = 60.0,
    include_sensitive: Annotated[
        bool,
        Field(
            description="False to wait on past a copy marked as sensitive (a password, from a password manager), "
            "for the next one."
        ),
    ] = True,
) -> Copied:
    """
    Wait until the user, or an app, copies something new, and return it. Clearing the clipboard doesn't
    count. Fails when nothing is copied in time.
    """
    return Copied(text=macos.clipboard.wait_for_change(timeout=timeout_seconds, include_sensitive=include_sensitive))


def register(server: MCPServer) -> None:
    add_tool(server, get_clipboard, title="Read the clipboard", annotations=READ_ONLY)
    add_tool(server, get_clipboard_image, title="Get the image on the clipboard", annotations=READ_ONLY)
    add_tool(server, set_clipboard, title="Copy text to the clipboard", annotations=REPLACING)
    add_tool(server, copy_files_to_clipboard, title="Copy files to the clipboard", annotations=REPLACING)
    add_tool(server, copy_image_to_clipboard, title="Copy an image to the clipboard", annotations=REPLACING)
    add_tool(server, clear_clipboard, title="Clear the clipboard", annotations=REPLACING)
    add_tool(server, wait_for_clipboard_change, title="Wait for something to be copied", annotations=READ_ONLY)
