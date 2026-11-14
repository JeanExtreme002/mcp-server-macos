"""Tools that store and read passwords in the Keychain, from ``macos.keychain``."""

from typing import Annotated, List, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._registry import DESTRUCTIVE, READ_ONLY, REPLACING, add_tool

Service = Annotated[
    str,
    Field(description="The service the password is for: the name of an app, a site or a tool, such as 'my-app'.", min_length=1),
]
Account = Annotated[str, Field(description="The account the password belongs to, such as 'alice'.")]


class Password(BaseModel):
    """A password read from the Keychain."""

    password: Optional[str] = Field(description="The password. Null when none is stored for that service and account.")


class Deleted(BaseModel):
    """A password removed from the Keychain."""

    existed: bool = Field(description="Whether there was one: false when there was nothing to delete.")


def list_keychain_accounts(service: Service) -> List[str]:
    """
    List the accounts that have a password stored in the Keychain for a service. Only the names are
    read, never the passwords, so macOS doesn't ask the user for anything.
    """
    return macos.keychain.accounts(service)


def get_keychain_password(service: Service, account: Account) -> Password:
    """
    Read a password from the Keychain, by its service and account. The password comes back as the
    result, which is seen by whoever provides the model: read one only when the task needs the
    password itself, and don't repeat it. macOS may ask the user to allow it, for an item another app
    created.
    """
    return Password(password=macos.keychain.get(service, account))


def set_keychain_password(
    service: Service,
    account: Account,
    password: Annotated[str, Field(description="The password to store.")],
) -> str:
    """Store a password in the Keychain for a service and an account, replacing the one that may be there."""
    macos.keychain.set(service, account, password)
    return "Password stored for {} ({}).".format(service, account)


def delete_keychain_password(service: Service, account: Account) -> Deleted:
    """Delete a password from the Keychain. It can't be read again afterwards."""
    return Deleted(existed=macos.keychain.delete(service, account))


def register(server: MCPServer) -> None:
    add_tool(server, list_keychain_accounts, title="List the accounts of a Keychain service", annotations=READ_ONLY)
    add_tool(server, get_keychain_password, title="Read a password from the Keychain", annotations=READ_ONLY)
    add_tool(server, set_keychain_password, title="Store a password in the Keychain", annotations=REPLACING)
    add_tool(server, delete_keychain_password, title="Delete a password from the Keychain", annotations=DESTRUCTIVE)
