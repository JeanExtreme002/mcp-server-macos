"""The Keychain tools against this Mac: an item of the tests' own is stored, read and deleted."""

from typing import AsyncIterator

import macos
import pytest
from mcp import Client

from tests.live.helpers import call

pytestmark = pytest.mark.anyio

SERVICE = "mcp-server-macos tests"


@pytest.fixture
async def service() -> AsyncIterator[str]:
    """A service no app uses, with no item before and after."""

    def empty() -> None:
        for account in macos.keychain.accounts(SERVICE):
            macos.keychain.delete(SERVICE, account)

    empty()
    yield SERVICE
    empty()


async def test_password_is_stored_read_and_deleted(client: Client, service: str) -> None:
    item = {"service": service, "account": "alice"}
    assert await call(client, "list_keychain_accounts", {"service": service}) == []
    assert await call(client, "get_keychain_password", item) == {"password": None}

    result = await client.call_tool("set_keychain_password", {**item, "password": "pä$$ \"w\" $(id) 🔑"})
    assert not result.is_error

    assert await call(client, "list_keychain_accounts", {"service": service}) == ["alice"]
    assert await call(client, "get_keychain_password", item) == {"password": "pä$$ \"w\" $(id) 🔑"}

    await client.call_tool("set_keychain_password", {**item, "password": "replaced"})
    assert await call(client, "get_keychain_password", item) == {"password": "replaced"}
    assert await call(client, "list_keychain_accounts", {"service": service}) == ["alice"]

    assert await call(client, "delete_keychain_password", item) == {"existed": True}
    assert await call(client, "delete_keychain_password", item) == {"existed": False}
    assert await call(client, "get_keychain_password", item) == {"password": None}
