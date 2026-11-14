"""How tools are registered: the modules listed, and the errors a tool reports."""

import importlib
import threading
import pkgutil

import macos
import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from mcp_server_macos import _registry, tools
from mcp_server_macos._permissions import APP, Permission
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


def test_every_tool_module_is_a_toolset_named_after_it() -> None:
    assert list(tools.TOOLSETS.values()) == list(tools.MODULES)
    for name, module in tools.TOOLSETS.items():
        assert module.__name__ == "mcp_server_macos.tools.{}".format(name)


@pytest.mark.parametrize(
    "error, expected",
    [
        (macos.NotSupportedError("needs macOS"), "NotSupportedError: needs macOS"),
        (macos.MacOSError("it failed"), "MacOSError: it failed"),
        (ValueError("no such sound"), "ValueError: no such sound"),
        (FileNotFoundError("/nope.txt"), "FileNotFoundError: /nope.txt"),
        (LookupError("no folder is named 'Work'"), "LookupError: no folder is named 'Work'"),
        (macos.AppNotFoundError("unable to find application 'Nope'"), "AppNotFoundError: unable to find application 'Nope'"),
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


@pytest.mark.parametrize("error", [RuntimeError("a bug"), KeyError("missing"), IndexError("out of range"), TypeError("x")])
def test_unexpected_errors_are_left_alone(error: Exception) -> None:
    # A missing key or index is a bug in the code: it's reported as a crash, without its text.
    @translate_errors
    def tool() -> None:
        raise error

    with pytest.raises(type(error)) as raised:
        tool()

    assert raised.value is error


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
    assert "Only the user can grant a permission" in text(result)


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


def test_annotations_say_what_a_tool_does() -> None:
    every = (_registry.READ_ONLY, _registry.ADDITIVE, _registry.REPLACING, _registry.DESTRUCTIVE)

    # Nothing leaves this Mac, but what asks a server on the internet, which only reads.
    assert all(annotations.open_world_hint is False for annotations in every)
    assert _registry.READ_ONLY_ONLINE.open_world_hint is True
    assert _registry.READ_ONLY_ONLINE.read_only_hint is True

    # What opens or runs something that may do anything is marked as the worst on every count.
    assert _registry.OPEN_ENDED.read_only_hint is False
    assert _registry.OPEN_ENDED.destructive_hint is True
    assert _registry.OPEN_ENDED.idempotent_hint is False
    assert _registry.OPEN_ENDED.open_world_hint is True

    assert _registry.READ_ONLY.read_only_hint is True
    assert [annotations.read_only_hint for annotations in every[1:]] == [False, False, False]

    # What a client asks the user about: only ADDITIVE changes something without being destructive.
    assert _registry.ADDITIVE.destructive_hint is False
    assert _registry.REPLACING.destructive_hint is True
    assert _registry.DESTRUCTIVE.destructive_hint is True

    # Setting a value twice is setting it once. Adding or deleting twice isn't.
    assert _registry.REPLACING.idempotent_hint is True
    assert _registry.ADDITIVE.idempotent_hint is False
    assert _registry.DESTRUCTIVE.idempotent_hint is False


# A missing permission: macOS is asked to show its prompt, and the tool runs again if that granted it.


class Screen:
    """A tool that needs a permission, which is granted or not, and the prompt of macOS for it."""

    def __init__(self, granted: bool = False, prompt_grants: bool = False) -> None:
        self.granted = granted
        self.prompt_grants = prompt_grants
        self.calls = 0
        self.prompts = 0
        self.permission = Permission(
            name="Screen Recording", where="System Settings › Privacy", request=self.request, restart=True
        )

    def request(self) -> bool:
        self.prompts += 1
        self.granted = self.granted or self.prompt_grants
        return self.granted

    def tool(self) -> str:
        self.calls += 1
        if not self.granted:
            raise macos.PermissionDeniedError("Screen Recording permission is missing")
        return "captured"


def test_tool_with_its_permission_runs_once_and_asks_nothing() -> None:
    screen = Screen(granted=True)

    assert translate_errors(screen.tool, screen.permission)() == "captured"
    assert (screen.calls, screen.prompts) == (1, 0)


def test_missing_permission_is_asked_for_and_the_tool_runs_again() -> None:
    screen = Screen(prompt_grants=True)

    assert translate_errors(screen.tool, screen.permission)() == "captured"
    assert (screen.calls, screen.prompts) == (2, 1)


def test_permission_still_missing_tells_what_to_ask_the_user() -> None:
    screen = Screen()

    with pytest.raises(ToolError) as raised:
        translate_errors(screen.tool, screen.permission)()

    assert str(raised.value) == (
        "PermissionDeniedError: Screen Recording permission is missing "
        "This needs the Screen Recording permission, which only the user can grant. "
        "Ask them to allow {} in System Settings › Privacy, to restart that app, and then try again.".format(APP)
    )
    assert isinstance(raised.value.__cause__, macos.PermissionDeniedError)
    # Asked once, and the tool not run again: macOS said the permission is still missing.
    assert (screen.calls, screen.prompts) == (1, 1)


def test_permission_granted_by_the_prompt_but_refused_again_is_reported() -> None:
    # macOS says it's granted, and the tool is refused all the same (another permission, or one that
    # only applies after a restart): reported, not asked for in a loop.
    screen = Screen()
    screen.permission = Permission(name="Screen Recording", where="System Settings", request=lambda: True)

    with pytest.raises(ToolError, match="This needs the Screen Recording permission"):
        translate_errors(screen.tool, screen.permission)()

    assert screen.calls == 2


def test_permission_without_a_prompt_is_only_reported() -> None:
    screen = Screen()
    permission = Permission(name="Automation", where="System Settings › Automation", note="macOS asks by itself.")

    with pytest.raises(ToolError) as raised:
        translate_errors(screen.tool, permission)()

    assert str(raised.value).endswith(
        "Ask them to allow {} in System Settings › Automation, and then try again. macOS asks by itself.".format(APP)
    )
    assert screen.calls == 1


def test_prompt_that_fails_is_a_permission_still_missing() -> None:
    def request() -> bool:
        raise macos.MacOSError("macOS lacks its prompt option")

    screen = Screen()
    permission = Permission(name="Accessibility", where="System Settings", request=request)

    with pytest.raises(ToolError, match="This needs the Accessibility permission"):
        translate_errors(screen.tool, permission)()

    assert screen.calls == 1


def test_missing_permission_of_a_tool_that_declares_none_is_reported() -> None:
    screen = Screen()

    with pytest.raises(ToolError) as raised:
        translate_errors(screen.tool)()

    assert str(raised.value) == (
        "PermissionDeniedError: Screen Recording permission is missing "
        "Only the user can grant a permission: ask them to allow {}, and then try again.".format(APP)
    )
    assert screen.calls == 1


def test_other_errors_do_not_ask_for_a_permission() -> None:
    screen = Screen()

    def tool() -> None:
        raise macos.MacOSError("it failed")

    with pytest.raises(ToolError, match="MacOSError: it failed"):
        translate_errors(tool, screen.permission)()

    assert screen.prompts == 0


async def test_tool_registered_with_a_permission_asks_for_it() -> None:
    screen = Screen(prompt_grants=True)

    def capture() -> str:
        """Capture the screen."""
        return screen.tool()

    server = MCPServer(name="test")
    add_tool(server, capture, title="Capture", annotations=READ_ONLY, permission=screen.permission)

    async with Client(server) as client:
        result = await client.call_tool("capture", {})

    assert not result.is_error
    assert text(result) == "captured"
    assert screen.prompts == 1


# Where a tool runs: a plain one on a worker thread, one that needs the main thread on the server's own.


async def test_tool_runs_on_a_worker_thread_unless_it_needs_the_main_one() -> None:
    def where_am_i() -> str:
        """Say which thread this runs on."""
        return threading.current_thread().name

    def where_am_i_on_main() -> str:
        """Say which thread this runs on, asked to be the main one."""
        return threading.current_thread().name

    server = MCPServer(name="test")
    add_tool(server, where_am_i, title="Where", annotations=READ_ONLY)
    add_tool(server, where_am_i_on_main, title="Where, on main", annotations=READ_ONLY, main_thread=True)

    async with Client(server) as client:
        worker = await client.call_tool("where_am_i", {})
        main = await client.call_tool("where_am_i_on_main", {})
        (tool,) = [tool for tool in (await client.list_tools()).tools if tool.name == "where_am_i_on_main"]

    assert text(main) == threading.current_thread().name  # the thread the server, and this test, run on
    assert text(worker) != text(main)
    # Still named and described by its function.
    assert tool.description == "Say which thread this runs on, asked to be the main one."


async def test_tool_on_the_main_thread_reports_errors_and_asks_for_permissions_like_any_other() -> None:
    screen = Screen(prompt_grants=True)

    def capture(region: str) -> str:
        """Capture a region of the screen."""
        if region == "nowhere":
            raise ValueError("no such region")
        return "{} {}".format(screen.tool(), region)

    server = MCPServer(name="test")
    add_tool(server, capture, title="Capture", annotations=READ_ONLY, permission=screen.permission, main_thread=True)

    async with Client(server) as client:
        granted = await client.call_tool("capture", {"region": "left"})
        refused = await client.call_tool("capture", {"region": "nowhere"})
        invalid = await client.call_tool("capture", {})

    assert text(granted) == "captured left"
    assert screen.prompts == 1
    assert refused.is_error and "ValueError: no such region" in text(refused)
    assert invalid.is_error
