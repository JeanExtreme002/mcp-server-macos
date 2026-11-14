"""Tools that read and change the preferences of apps and of the system, from ``macos.defaults``."""

from typing import Annotated, Any, List, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._registry import DESTRUCTIVE, READ_ONLY, REPLACING, add_tool
from .._values import plain

Domain = Annotated[
    str,
    Field(
        description="The preferences' domain: an app's bundle ID, such as 'com.apple.dock', or 'NSGlobalDomain' for "
        "the settings every app shares.",
        min_length=1,
    ),
]
Key = Annotated[str, Field(description="The preference's name, such as 'autohide'.", min_length=1)]
CurrentHost = Annotated[
    bool, Field(description="True for the settings kept for this Mac only, like the defaults command's -currentHost.")
]


class Preference(BaseModel):
    """The value of a preference, or of all those of a domain."""

    value: Any = Field(
        description="The value: a boolean, a number, text, a list or an object. A date is ISO 8601 text, in UTC, and "
        "binary data is Base64 text. Null when the preference isn't set. For a whole domain, an object with "
        "every preference it sets."
    )


class Deleted(BaseModel):
    """A preference that was removed."""

    was_set: bool = Field(description="Whether the preference was set: false when there was nothing to remove.")


def list_preference_keys(domain: Domain, current_host: CurrentHost = False) -> List[str]:
    """List the names of the preferences a domain sets, sorted, like the defaults command."""
    return macos.defaults.keys(domain, current_host=current_host)


def read_preference(
    domain: Domain,
    key: Annotated[
        Optional[str],
        Field(description="The preference's name, such as 'autohide'. Every preference of the domain when left out."),
    ] = None,
    current_host: CurrentHost = False,
) -> Preference:
    """
    Read a preference of an app or of the system, or all those of a domain, like the defaults command.
    As apps see it, a preference an app's domain doesn't set falls back to the global domain's.
    """
    return Preference(value=plain(macos.defaults.read(domain, key, current_host=current_host)))


def write_preference(
    domain: Domain,
    key: Key,
    value: Annotated[
        Any,
        Field(
            description="The value, with its own type: true or false for a boolean, a number, text, a list or an "
            "object. Not null: a preference has no null, and delete_preference removes one."
        ),
    ],
    current_host: CurrentHost = False,
) -> str:
    """
    Set a preference of an app or of the system, like the defaults command. Preferences aren't
    documented or checked: a wrong name does nothing, and a wrong value can make an app misbehave, so
    read the preference first to know what it holds. Most apps read their preferences when they open.
    """
    macos.defaults.write(domain, key, value, current_host=current_host)
    return "Set {} in {}.".format(key, domain)


def delete_preference(domain: Domain, key: Key, current_host: CurrentHost = False) -> Deleted:
    """
    Remove a preference from a domain, which puts the app back to its own default for it. What it held
    is gone: read it first if it may be wanted back.
    """
    return Deleted(was_set=macos.defaults.delete(domain, key, current_host=current_host))


def register(server: MCPServer) -> None:
    add_tool(server, list_preference_keys, title="List a domain's preferences", annotations=READ_ONLY)
    add_tool(server, read_preference, title="Read a preference", annotations=READ_ONLY)
    add_tool(server, write_preference, title="Set a preference", annotations=REPLACING)
    add_tool(server, delete_preference, title="Remove a preference", annotations=DESTRUCTIVE)
