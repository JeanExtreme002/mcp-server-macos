"""Tools that ask the user to confirm it's them, with Touch ID or their password, from ``macos.auth``."""

from typing import Annotated

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._registry import ADDITIVE, LONGEST_WAIT, READ_ONLY, add_tool


class Availability(BaseModel):
    """How the user can confirm it's them."""

    available: bool = Field(description="Whether the user can be asked at all: with their login password, on any Mac.")
    touch_id: bool = Field(description="Whether Touch ID is set up, and not locked out after failed tries.")


class Confirmation(BaseModel):
    """Whether the user confirmed it's them."""

    confirmed: bool = Field(
        description="True when they confirmed, with their fingerprint, password or Apple Watch. False when they "
        "cancelled, failed, or didn't answer in time."
    )


def check_user_authentication() -> Availability:
    """Check how the user can be asked to confirm it's them, without asking: whether Touch ID is set up."""
    return Availability(available=macos.auth.is_available(), touch_id=macos.auth.is_available(only_touch_id=True))


def authenticate_user(
    reason: Annotated[
        str,
        Field(
            description="Why, completing the sentence the prompt shows: '... wants to <reason>'. Such as 'unlock "
            "the production credentials'.",
            min_length=1,
        ),
    ],
    only_touch_id: Annotated[
        bool, Field(description="True to accept the fingerprint only, not the login password.")
    ] = False,
    timeout_seconds: Annotated[
        float, Field(description="How long to wait for the user, in seconds.", gt=0, le=LONGEST_WAIT)
    ] = 120.0,
) -> Confirmation:
    """
    Ask the user to confirm it's them, with Touch ID, their login password or their Apple Watch, in
    macOS's own prompt: for a moment where it matters that the Mac's owner is there and agrees. macOS
    checks the fingerprint or the password itself: only the answer comes back.
    """
    return Confirmation(confirmed=macos.auth.confirm(reason, only_touch_id=only_touch_id, timeout=timeout_seconds))


def register(server: MCPServer) -> None:
    add_tool(server, check_user_authentication, title="Check how the user can authenticate", annotations=READ_ONLY)
    # It shows a prompt, which the user sees and has to answer.
    add_tool(server, authenticate_user, title="Ask the user to authenticate", annotations=ADDITIVE)
