"""How tools are registered: the modules listed, and the errors a tool reports."""

import importlib
import pkgutil

import macos
import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from mcp_server_macos import _registry, tools
from mcp_server_macos._registry import READ_ONLY, add_tool, translate_errors
from tests.helpers import text

pytestmark = pytest.mark.anyio


def test_every_tool_module_is_listed() -> None:
    found = {
        importlib.import_module("{}.{}".format(tools.__name__, module.name))
        for module in pkgutil.iter_modules(tools.__path__)
        if not module.name.startswith("_")
    }

    assert found == set(tools.MODULES), "a module of mcp_server_macos.tools is missing from MODULES, or is listed twice"
    assert len(tools.MODULES) == len(set(tools.MODULES))


def test_every_tool_module_registers_itself() -> None:
    for module in tools.MODULES:
        assert callable(getattr(module, "register", None)), "{} has no register(server)".format(module.__name__)


@pytest.mark.parametrize(
    "error, expected",
    [
        (macos.NotSupportedError("needs macOS"), "NotSupportedError: needs macOS"),
        (macos.PermissionDeniedError("notifications are off"), "PermissionDeniedError: notifications are off"),
        (macos.MacOSError("it failed"), "MacOSError: it failed"),
        (ValueError("no such sound"), "ValueError: no such sound"),
    ],
)
def test_expected_errors_become_tool_errors(error: Exception, expected: str) -> None:
    @translate_errors
    def tool() -> None:
        raise error

    with pytest.raises(ToolError) as raised:
        tool()

    assert str(raised.value) == expected
    assert raised.value.__cause__ is error


def test_unexpected_errors_are_left_alone() -> None:
    @translate_errors
    def tool() -> None:
        raise RuntimeError("a bug")

    with pytest.raises(RuntimeError):
        tool()


def test_translate_errors_keeps_the_function() -> None:
    @translate_errors
    def tool(number: int, *, word: str = "a") -> str:
        """Repeat a word."""
        return word * number

    assert tool(3, word="ab") == "ababab"
    assert tool.__name__ == "tool"
    assert tool.__doc__ == "Repeat a word."


def test_tool_without_docstring_is_refused(server: MCPServer) -> None:
    def undocumented() -> None:
        pass

    with pytest.raises(ValueError, match="undocumented"):
        add_tool(server, undocumented, title="Undocumented", annotations=READ_ONLY)


async def test_tool_is_named_and_described_by_its_function() -> None:
    def count_letters(word: str) -> int:
        """
        Count the letters of a word.

        Spaces count too.
        """
        return len(word)

    server = MCPServer(name="test")
    add_tool(server, count_letters, title="Count letters", annotations=READ_ONLY)

    async with Client(server) as client:
        (tool,) = (await client.list_tools()).tools
        result = await client.call_tool("count_letters", {"word": "hello"})

    assert tool.name == "count_letters"
    assert tool.title == "Count letters"
    assert tool.description == "Count the letters of a word.\n\nSpaces count too."
    assert tool.annotations == READ_ONLY
    assert tool.input_schema["required"] == ["word"]
    assert result.structured_content == {"result": 5}


async def test_expected_error_reaches_the_client_with_its_message() -> None:
    def fail() -> None:
        """Always fail, as macOS would."""
        raise macos.PermissionDeniedError("Screen Recording is off")

    server = MCPServer(name="test")
    add_tool(server, fail, title="Fail", annotations=READ_ONLY)

    async with Client(server) as client:
        result = await client.call_tool("fail", {})

    assert result.is_error
    assert "PermissionDeniedError: Screen Recording is off" in text(result)


async def test_unexpected_error_reaches_the_client_without_its_message() -> None:
    def crash() -> None:
        """Always crash, with a message that shouldn't leave the server."""
        raise RuntimeError("the password is hunter2")

    server = MCPServer(name="test")
    add_tool(server, crash, title="Crash", annotations=READ_ONLY)

    async with Client(server) as client:
        result = await client.call_tool("crash", {})

    assert result.is_error
    assert "hunter2" not in text(result)
    assert "crash" in text(result)


def test_annotations_say_nothing_leaves_this_mac() -> None:
    for annotations in (_registry.READ_ONLY, _registry.ADDITIVE):
        assert annotations.open_world_hint is False

    assert _registry.READ_ONLY.read_only_hint is True
    assert _registry.ADDITIVE.read_only_hint is False
    assert _registry.ADDITIVE.destructive_hint is False
