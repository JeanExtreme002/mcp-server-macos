"""Tools that ask the user something in a native dialog, from ``macos.dialog``."""

from typing import Annotated, List, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._registry import ADDITIVE, LONGEST_WAIT, add_tool

Message = Annotated[str, Field(description="What the dialog says.", min_length=1)]
Title = Annotated[Optional[str], Field(description="The dialog's title.")]
Timeout = Annotated[
    float,
    Field(
        description="How long to wait for the user, in seconds, before closing the dialog as if it was cancelled.",
        gt=0,
        le=LONGEST_WAIT,
    ),
]
Types = Annotated[
    Optional[List[str]],
    Field(description="Limit the choice, by extension (['pdf', 'png']) or type identifier (['public.image'])."),
]
StartFolder = Annotated[Optional[str], Field(description="The folder the picker opens in.")]


class Confirmation(BaseModel):
    """The answer to a yes or no question."""

    confirmed: bool = Field(
        description="True when the user clicked the OK button. False when they cancelled, or didn't answer in time."
    )


class TextAnswer(BaseModel):
    """What the user typed."""

    text: Optional[str] = Field(description="The text. Null when the user cancelled, or didn't answer in time.")


class Choice(BaseModel):
    """What the user picked from a list."""

    choice: Optional[str] = Field(description="The option picked. Null when the user cancelled, or didn't answer in time.")


class ChosenPaths(BaseModel):
    """The files or the folder the user picked."""

    paths: List[str] = Field(description="The paths picked. Empty when the user cancelled, or didn't answer in time.")


def show_alert(
    message: Message,
    detail: Annotated[Optional[str], Field(description="Smaller text under the message.")] = None,
    timeout_seconds: Timeout = 120.0,
) -> str:
    """
    Show the user an alert with an OK button, and wait until it's dismissed. To tell them something
    without waiting, send a notification instead.
    """
    macos.dialog.alert(message, detail=detail, timeout=timeout_seconds)
    return "Alert shown."


def ask_confirmation(
    message: Message,
    title: Title = None,
    ok: Annotated[str, Field(description="The label of the button that confirms.", min_length=1)] = "OK",
    cancel: Annotated[str, Field(description="The label of the button that cancels.", min_length=1)] = "Cancel",
    timeout_seconds: Timeout = 120.0,
) -> Confirmation:
    """Ask the user a yes or no question in a dialog, and wait for the answer."""
    return Confirmation(confirmed=macos.dialog.confirm(message, title=title, ok=ok, cancel=cancel, timeout=timeout_seconds))


def ask_text(
    message: Message,
    default: Annotated[
        str,
        Field(description="Text the field starts with. Not a secret: other processes of the user can see it."),
    ] = "",
    title: Title = None,
    hidden: Annotated[
        bool, Field(description="True to show dots instead of what's typed, for a password.")
    ] = False,
    timeout_seconds: Timeout = 120.0,
) -> TextAnswer:
    """
    Ask the user for a line of text in a dialog, and wait for it. What they type comes back as the
    result, a password included: ask for one only when the task needs it.
    """
    return TextAnswer(
        text=macos.dialog.prompt(message, default=default, title=title, hidden=hidden, timeout=timeout_seconds)
    )


def ask_choice(
    options: Annotated[List[str], Field(description="The options to pick from.", min_length=1)],
    prompt: Annotated[Optional[str], Field(description="What the dialog says above the list.")] = None,
    default: Annotated[Optional[str], Field(description="The option selected when the dialog opens.")] = None,
    title: Title = None,
    timeout_seconds: Timeout = 120.0,
) -> Choice:
    """Let the user pick one option from a list, in a dialog. It waits until they answer, or the time runs out."""
    return Choice(choice=macos.dialog.choose(options, prompt=prompt, default=default, title=title, timeout=timeout_seconds))


def ask_for_files(
    prompt: Annotated[Optional[str], Field(description="What the picker says.")] = None,
    types: Types = None,
    folder: StartFolder = None,
    multiple: Annotated[bool, Field(description="True to let the user pick several files.")] = False,
    timeout_seconds: Timeout = 120.0,
) -> ChosenPaths:
    """
    Let the user pick a file, or several, in the system's file picker. It waits until they answer, or the
    time runs out.
    """
    if multiple:
        chosen_files = macos.dialog.choose_files(prompt, types=types, folder=folder, timeout=timeout_seconds)
        return ChosenPaths(paths=[str(path) for path in chosen_files])
    chosen = macos.dialog.choose_file(prompt, types=types, folder=folder, timeout=timeout_seconds)
    return ChosenPaths(paths=[] if chosen is None else [str(chosen)])


def ask_for_folder(
    prompt: Annotated[Optional[str], Field(description="What the picker says.")] = None,
    folder: StartFolder = None,
    timeout_seconds: Timeout = 120.0,
) -> ChosenPaths:
    """Let the user pick a folder in the system's folder picker. It waits until they answer, or the time runs out."""
    chosen = macos.dialog.choose_folder(prompt, folder=folder, timeout=timeout_seconds)
    return ChosenPaths(paths=[] if chosen is None else [str(chosen)])


def register(server: MCPServer) -> None:
    # Each shows a dialog, which the user sees and has to answer, and changes nothing else.
    add_tool(server, show_alert, title="Show an alert", annotations=ADDITIVE)
    add_tool(server, ask_confirmation, title="Ask a yes or no question", annotations=ADDITIVE)
    add_tool(server, ask_text, title="Ask for a line of text", annotations=ADDITIVE)
    add_tool(server, ask_choice, title="Ask to pick from a list", annotations=ADDITIVE)
    add_tool(server, ask_for_files, title="Ask to pick files", annotations=ADDITIVE)
    add_tool(server, ask_for_folder, title="Ask to pick a folder", annotations=ADDITIVE)
