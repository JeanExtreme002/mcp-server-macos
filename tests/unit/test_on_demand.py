"""
Toolsets enabled on demand: a server started with some toolsets reaches every tool all the same, with
find_tools and enable_toolsets, and each tool it adds is the one a server with every toolset has.
"""

from typing import Any, Dict, Set

import anyio
import macos
import pytest
from mcp import Client

from mcp_server_macos import _on_demand, create_server, tools
from mcp_server_macos._registry import READ_ONLY
from tests.helpers import text
from tests.unit.test_server import TOOLS

pytestmark = pytest.mark.anyio

ON_DEMAND = {"find_tools", "enable_toolsets"}


async def definitions(client: Client) -> Dict[str, Dict[str, Any]]:
    """Every tool the client is sent, as it's sent: schemas, description, title and annotations."""
    return {
        tool.name: tool.model_dump(mode="json", exclude_none=True, by_alias=True)
        for tool in (await client.list_tools()).tools
    }


async def _names(toolset: str) -> Set[str]:
    """The tools of one toolset."""
    async with Client(create_server([toolset])) as client:
        return {tool.name for tool in (await client.list_tools()).tools} - ON_DEMAND


async def test_the_core_toolsets_start_with_the_tools_that_enable_the_others() -> None:
    core: Set[str] = set()
    for name in _on_demand.CORE:
        core |= await _names(name)

    async with Client(create_server(list(_on_demand.CORE))) as client:
        assert set(await definitions(client)) == core | ON_DEMAND


async def test_every_tool_is_reached_as_it_is_with_every_toolset() -> None:
    # Started with the core, every toolset enabled one after the other: the tools listed in the end are
    # every tool, each defined exactly as a server with every toolset defines it.
    async with Client(create_server()) as everything:
        expected = await definitions(everything)

    async with Client(create_server(list(_on_demand.CORE))) as client:
        for name in tools.TOOLSETS:
            result = await client.call_tool("enable_toolsets", {"names": [name]})
            assert not result.is_error, text(result)
        reached = await definitions(client)

    assert set(reached) - ON_DEMAND == TOOLS
    for name, definition in expected.items():
        assert reached[name] == definition, name


async def test_enabling_a_toolset_lists_its_tools_and_says_which() -> None:
    async with Client(create_server(list(_on_demand.CORE))) as client:
        result = await client.call_tool("enable_toolsets", {"names": ["volume", "notifications"]})
        listed = set(await definitions(client))

    # In the toolsets' own order; notifications was enabled already, so only volume's tools are added.
    assert result.structured_content == {
        "toolsets": [name for name in tools.TOOLSETS if name in {"clipboard", "dialog", "notifications", "volume"}],
        "added": ["get_volume", "set_volume", "set_muted"],
    }
    assert {"get_volume", "set_volume", "set_muted"} <= listed


async def test_enabling_a_toolset_twice_adds_nothing_the_second_time() -> None:
    async with Client(create_server(list(_on_demand.CORE))) as client:
        await client.call_tool("enable_toolsets", {"names": ["volume"]})
        again = await client.call_tool("enable_toolsets", {"names": ["volume", "volume"]})
        names = [tool.name for tool in (await client.list_tools()).tools]

    assert again.structured_content is not None and again.structured_content["added"] == []
    assert len(names) == len(set(names))


async def test_a_tool_enabled_is_called_as_any_other(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(macos.volume, "get", lambda: 30)
    monkeypatch.setattr(macos.volume, "is_muted", lambda: False)

    async with Client(create_server(list(_on_demand.CORE))) as client:
        before = await client.call_tool("get_volume", {})
        await client.call_tool("enable_toolsets", {"names": ["volume"]})
        after = await client.call_tool("get_volume", {})

    assert before.is_error  # not there yet
    assert not after.is_error and after.structured_content == {"level": 30, "muted": False}


async def test_the_client_is_told_the_list_changed() -> None:
    # From protocol 2026-07-28 on, on a subscriptions/listen stream, as Claude Code hears it.
    events = []
    async with Client(create_server(list(_on_demand.CORE))) as client:
        async with client.listen(tools_list_changed=True) as subscription:

            async def receive() -> None:
                async for event in subscription:
                    events.append(type(event).__name__)
                    return

            async with anyio.create_task_group() as group:
                group.start_soon(receive)
                await client.call_tool("enable_toolsets", {"names": ["volume"]})
                with anyio.fail_after(5):
                    while not events:
                        await anyio.sleep(0.01)
                group.cancel_scope.cancel()

    assert events == ["ToolsListChanged"]


async def test_a_server_with_some_toolsets_says_its_tools_may_change() -> None:
    # Before protocol 2026-07-28, a client is told of a change only if the server said it may make one.
    server = create_server(list(_on_demand.CORE))
    options = server._lowlevel_server.create_initialization_options()

    assert options.capabilities.tools is not None and options.capabilities.tools.list_changed is True


async def test_find_tools_searches_every_tool_enabled_or_not() -> None:
    async with Client(create_server(list(_on_demand.CORE))) as client:
        found = await client.call_tool("find_tools", {"query": "encrypt a PDF"})
        await client.call_tool("enable_toolsets", {"names": ["pdf"]})
        again = await client.call_tool("find_tools", {"query": "encrypt a PDF", "limit": 1})

    assert found.structured_content is not None
    first = found.structured_content["result"][0]
    assert (first["name"], first["toolset"], first["enabled"]) == ("encrypt_pdf", "pdf", False)
    assert again.structured_content is not None
    assert again.structured_content["result"] == [{**first, "enabled": True}]


async def test_find_tools_lists_a_toolset() -> None:
    async with Client(create_server(list(_on_demand.CORE))) as client:
        found = await client.call_tool("find_tools", {"query": "anything", "toolset": "volume", "limit": 50})

    assert found.structured_content is not None
    assert {tool["name"] for tool in found.structured_content["result"]} == {"get_volume", "set_volume", "set_muted"}


async def test_the_two_tools_only_read_and_name_every_toolset() -> None:
    async with Client(create_server(list(_on_demand.CORE))) as client:
        listed = {tool.name: tool for tool in (await client.list_tools()).tools}

    for name in ON_DEMAND:
        assert listed[name].annotations == READ_ONLY, name
    description = listed["enable_toolsets"].description or ""
    for name in tools.TOOLSETS:
        assert "- {}: {}".format(name, _on_demand.summary(name)) in description
    assert set(listed["enable_toolsets"].input_schema["properties"]["names"]["items"]["enum"]) == set(tools.TOOLSETS)


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("enable_toolsets", {"names": []}),
        ("enable_toolsets", {"names": ["nope"]}),
        ("find_tools", {"query": ""}),
        ("find_tools", {"query": "pdf", "toolset": "nope"}),
        ("find_tools", {"query": "pdf", "limit": 0}),
    ],
)
async def test_the_two_tools_refuse_what_isnt_one(tool: str, arguments: Dict[str, Any]) -> None:
    async with Client(create_server(list(_on_demand.CORE))) as client:
        result = await client.call_tool(tool, arguments)
        listed = {t.name for t in (await client.list_tools()).tools}

    assert result.is_error
    assert "get_volume" not in listed


def test_a_toolset_summary_is_its_docstring_without_pymacos() -> None:
    assert _on_demand.summary("system").startswith("Tools about the Mac itself: what it is")
    assert "macos." not in "".join(_on_demand.summary(name) for name in tools.TOOLSETS)


async def test_the_instructions_say_how_to_reach_the_other_tools() -> None:
    async with Client(create_server(list(_on_demand.CORE))) as client:
        some = client.instructions or ""
    async with Client(create_server()) as client:
        every = client.instructions or ""

    assert "enable_toolsets" in some and "find_tools" in some
    assert "enable_toolsets" not in every  # nothing to enable
