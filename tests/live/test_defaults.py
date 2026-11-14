"""The preferences tools against this Mac: a domain of the tests' own is written, read and removed."""

from typing import AsyncIterator

import macos
import pytest
from mcp import Client

from tests.helpers import text
from tests.live.helpers import call

pytestmark = pytest.mark.anyio

DOMAIN = "com.github.jeanextreme002.mcp-server-macos.tests"


@pytest.fixture
async def domain() -> AsyncIterator[str]:
    """A domain no app reads, emptied before and after."""

    def empty() -> None:
        for key in macos.defaults.keys(DOMAIN):
            macos.defaults.delete(DOMAIN, key)

    empty()
    yield DOMAIN
    empty()


async def test_preferences_are_written_read_and_removed(client: Client, domain: str) -> None:
    values = {"flag": True, "count": 3, "ratio": 0.5, "name": "héllo \"quoted\"", "list": ["a", 1, False], "nested": {"n": 1}}

    for key, value in values.items():
        result = await client.call_tool("write_preference", {"domain": domain, "key": key, "value": value})
        assert not result.is_error, text(result)

    assert await call(client, "list_preference_keys", {"domain": domain}) == sorted(values)
    for key, value in values.items():
        read = (await call(client, "read_preference", {"domain": domain, "key": key}))["value"]
        assert read == value
        assert type(read) is type(value), key  # true comes back true, not 1
    assert (await call(client, "read_preference", {"domain": domain}))["value"] == values

    assert await call(client, "delete_preference", {"domain": domain, "key": "flag"}) == {"was_set": True}
    assert await call(client, "delete_preference", {"domain": domain, "key": "flag"}) == {"was_set": False}
    assert (await call(client, "read_preference", {"domain": domain, "key": "flag"}))["value"] is None
    assert "flag" not in await call(client, "list_preference_keys", {"domain": domain})


async def test_preference_is_not_written_without_a_value_or_to_a_path(client: Client, domain: str) -> None:
    result = await client.call_tool("write_preference", {"domain": domain, "key": "nothing", "value": None})
    assert result.is_error
    assert "ValueError" in text(result)

    result = await client.call_tool("write_preference", {"domain": "/tmp/a file", "key": "k", "value": 1})
    assert result.is_error
    assert "ValueError" in text(result)

    assert await call(client, "list_preference_keys", {"domain": domain}) == []


async def test_system_preferences_are_read(client: Client) -> None:
    assert await call(client, "list_preference_keys", {"domain": "NSGlobalDomain"})
