"""Starting the server with some of its toolsets: from Python, the command line and the environment."""

from typing import List, Optional, Set

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer

from mcp_server_macos import _on_demand, create_server, server, tools
from tests.unit.test_server import TOOLS

pytestmark = pytest.mark.anyio


# Added to a server started with some of the toolsets only, to find and enable the others.
ON_DEMAND = {"find_tools", "enable_toolsets"}


async def listed(running: MCPServer) -> Set[str]:
    async with Client(running) as client:
        return {tool.name for tool in (await client.list_tools()).tools}


async def own(running: MCPServer) -> Set[str]:
    """The tools of the toolsets a server was started with: without the two that enable the others."""
    names = await listed(running)
    assert ON_DEMAND <= names
    return names - ON_DEMAND


async def test_every_toolset_by_default() -> None:
    # Every toolset from the start: nothing to enable, so no tool to enable it either.
    assert await listed(create_server()) == TOOLS
    assert await listed(create_server(None)) == TOOLS
    assert await listed(create_server(list(tools.TOOLSETS))) == TOOLS


async def test_only_the_toolsets_asked_for() -> None:
    assert await own(create_server(["volume"])) == {"get_volume", "set_volume", "set_muted"}
    assert await own(create_server(["notifications"])) == {"send_notification", "check_notification_permission"}
    assert await own(create_server(["speech"])) == {"list_voices", "speak", "save_speech"}
    assert await own(create_server(["launch"])) == {"open_file_or_url"}
    assert await own(create_server(["volume", "notifications"])) == {
        "get_volume",
        "set_volume",
        "set_muted",
        "send_notification",
        "check_notification_permission",
    }


async def test_each_toolset_has_tools_and_together_they_have_them_all() -> None:
    together: Set[str] = set()
    for name in tools.TOOLSETS:
        mine = await own(create_server([name]))
        assert mine, "the toolset {} has no tools".format(name)
        assert not mine & together, "a tool of {} is in another toolset too".format(name)
        together |= mine

    assert together == TOOLS


async def test_toolsets_asked_for_twice_or_out_of_order() -> None:
    names = list(reversed(list(tools.TOOLSETS))) * 2

    async with Client(create_server(names)) as client:
        in_order = [tool.name for tool in (await client.list_tools()).tools]
    async with Client(create_server()) as client:
        by_default = [tool.name for tool in (await client.list_tools()).tools]

    assert in_order == by_default


@pytest.mark.parametrize(
    "names, message",
    [
        (["nope"], "unknown toolset: nope. The toolsets are: "),
        (["system", "nope", "neither"], "unknown toolsets: nope, neither. The toolsets are: "),
        ([], "no toolset was chosen. The toolsets are: "),
    ],
)
def test_toolsets_that_do_not_exist_are_refused(names: List[str], message: str) -> None:
    with pytest.raises(ValueError) as raised:
        create_server(names)

    assert str(raised.value) == message + ", ".join(tools.TOOLSETS)


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> List[Optional[List[str]]]:
    """The toolsets main() created its server with, instead of running one."""
    asked: List[Optional[List[str]]] = []

    def create(toolsets: Optional[List[str]] = None, *, follow_client: bool = False) -> MCPServer:
        asked.append(toolsets)
        following.append(follow_client)
        return create_server(toolsets)

    following: List[bool] = []
    monkeypatch.setattr(server, "_following", following, raising=False)

    monkeypatch.setattr(server, "create_server", create)
    monkeypatch.setattr(MCPServer, "run", lambda self, transport: None)
    monkeypatch.delenv(server.TOOLSETS_VARIABLE, raising=False)
    return asked


def test_command_starts_with_the_core_toolsets(started: List[Optional[List[str]]]) -> None:
    # The others are found and enabled as a task needs them: a client isn't sent every tool at first. Left
    # to the server, the toolsets follow the client (every one for a client that defers tools itself);
    # named, they don't.
    server.main([])
    server.main(["--toolsets", "pdf"])

    assert started == [list(_on_demand.CORE), ["pdf"]]
    assert server._following == [True, False]  # type: ignore[attr-defined]


def test_command_offers_every_toolset_from_the_start_when_asked(
    started: List[Optional[List[str]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    server.main(["--toolsets", "all"])
    monkeypatch.setenv(server.TOOLSETS_VARIABLE, "all")
    server.main([])

    assert started == [None, None]


def test_command_takes_the_toolsets(started: List[Optional[List[str]]]) -> None:
    server.main(["--toolsets", "system"])
    server.main(["--toolsets", " system , notifications,"])

    assert started == [["system"], ["system", "notifications"]]


def test_environment_chooses_the_toolsets(started: List[Optional[List[str]]], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(server.TOOLSETS_VARIABLE, "notifications")

    server.main([])

    assert started == [["notifications"]]


def test_command_line_wins_over_the_environment(
    started: List[Optional[List[str]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(server.TOOLSETS_VARIABLE, "notifications")

    server.main(["--toolsets", "system"])

    assert started == [["system"]]


@pytest.mark.parametrize("arguments", [["--toolsets", "nope"], ["--toolsets", ""], ["--toolsets", " , "]])
def test_command_refuses_toolsets_that_do_not_exist(
    started: List[Optional[List[str]]], capsys: pytest.CaptureFixture[str], arguments: List[str]
) -> None:
    with pytest.raises(SystemExit) as exit:
        server.main(arguments)

    assert exit.value.code == 2
    assert "The toolsets are: " + ", ".join(tools.TOOLSETS) in capsys.readouterr().err


def test_empty_environment_variable_is_refused(
    started: List[Optional[List[str]]], capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Set, but to nothing: a configuration mistake, not a wish for every toolset.
    monkeypatch.setenv(server.TOOLSETS_VARIABLE, "")

    with pytest.raises(SystemExit):
        server.main([])

    assert "no toolset was chosen" in capsys.readouterr().err
