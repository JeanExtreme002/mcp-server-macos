"""Tools that save this Mac's settings and apply them, as dotfiles for macOS, from ``macos.settings``."""

import warnings
from typing import Annotated, Any, Dict, List

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._registry import READ_ONLY, REPLACING, add_tool
from .._values import plain


class Exported(BaseModel):
    """This Mac's settings."""

    settings: Dict[str, Dict[str, Any]] = Field(
        description="The settings, by section, as apply_settings takes them back: {\"dock\": {\"autohide\": true, ...}}."
    )
    left_out: List[str] = Field(
        description="The settings that couldn't be saved, and why: one this Mac doesn't have, a permission macOS "
        "refused, a value apply_settings would refuse. The rest is saved and applies as it is."
    )


class Applied(BaseModel):
    """The settings that were applied."""

    changed: List[str] = Field(description="The settings that changed, as 'section.name'. Those already as wanted aren't.")


def list_setting_names() -> List[str]:
    """
    List every setting export_settings saves and apply_settings takes, as 'section.name': the keyboard,
    trackpad, mouse, Dock, Finder, windows, appearance, screenshots, sounds and system settings.
    """
    return macos.settings.names()


def export_settings() -> Exported:
    """
    Get this Mac's settings, by section, as values apply_settings takes back, and the ones that couldn't
    be saved. Save them to move them to another Mac, or to put them back later.
    """
    # pymacos says which settings it leaves out with a warning, which would otherwise not reach the model.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", RuntimeWarning)
        exported = macos.settings.export()
    return Exported(
        settings=plain(exported),
        left_out=[str(warning.message) for warning in caught if issubclass(warning.category, RuntimeWarning)],
    )


def apply_settings(
    settings: Annotated[
        Dict[str, Dict[str, Any]],
        Field(
            description="The settings to apply, by section, as export_settings gives them: {\"dock\": {\"autohide\": "
            "true, \"size\": 48}}. Any part of an export works: the settings left out stay as they are."
        ),
    ],
) -> Applied:
    """
    Change this Mac's settings to the ones given, and return those that changed. Unknown names and
    invalid values are refused before anything changes, and when a change fails midway, the ones
    already made are put back. The Dock and Finder restart once, at the end.
    """
    return Applied(changed=macos.settings.apply(settings))


def register(server: MCPServer) -> None:
    add_tool(server, list_setting_names, title="List the settings that can be saved", annotations=READ_ONLY)
    add_tool(server, export_settings, title="Save this Mac's settings", annotations=READ_ONLY)
    add_tool(server, apply_settings, title="Apply settings to this Mac", annotations=REPLACING)
