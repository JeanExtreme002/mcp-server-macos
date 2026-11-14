"""The server as a client sees it: who it is, and which tools it lists."""

import re

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer

import mcp_server_macos
from mcp_server_macos import create_server
from mcp_server_macos._registry import ADDITIVE, DESTRUCTIVE, READ_ONLY, READ_ONLY_ONLINE, REPLACING
from tests.helpers import text

pytestmark = pytest.mark.anyio

# Every tool, by name, with what it does to the Mac. A new tool is added here, and only here (the other
# tests use this list): a client finds tools by name, so renaming or dropping one breaks whoever relies
# on it, and decides by these annotations whether to ask the user before a call, so a tool that changes
# or deletes something must never pass for one that only reads. Neither should change unnoticed.
ANNOTATIONS = {
    # appearance
    "get_appearance": READ_ONLY,
    "set_appearance": REPLACING,
    "wait_for_appearance_change": READ_ONLY,
    # clipboard
    "get_clipboard": READ_ONLY,
    "get_clipboard_image": READ_ONLY,
    "set_clipboard": REPLACING,
    "copy_files_to_clipboard": REPLACING,
    "copy_image_to_clipboard": REPLACING,
    "clear_clipboard": REPLACING,
    "wait_for_clipboard_change": READ_ONLY,
    # notifications
    "send_notification": ADDITIVE,
    "check_notification_permission": READ_ONLY,
    # power
    "get_power_status": READ_ONLY,
    "get_sleep_blockers": READ_ONLY,
    "keep_awake": REPLACING,
    "allow_sleep": REPLACING,
    "sleep_mac": DESTRUCTIVE,
    "sleep_display": REPLACING,
    # system: what the Mac is
    "get_system_info": READ_ONLY,
    "get_security_status": READ_ONLY,
    "list_fonts": READ_ONLY,
    "list_usb_devices": READ_ONLY,
    "list_available_updates": READ_ONLY_ONLINE,
    # system: how it's doing
    "get_system_status": READ_ONLY,
    "get_gpu_usage": READ_ONLY,
    "wait_for_idle": READ_ONLY,
    "wait_for_user_activity": READ_ONLY,
    # system: disks
    "list_volumes": READ_ONLY,
    "get_disk_health": READ_ONLY,
    "mount_disk_image": ADDITIVE,
    "eject_volume": DESTRUCTIVE,
    "unmount_disk_image": DESTRUCTIVE,
    # system: processes
    "list_processes": READ_ONLY,
    "get_process": READ_ONLY,
    "list_open_files": READ_ONLY,
    "find_processes_using": READ_ONLY,
    "list_ports": READ_ONLY,
    "find_port_owner": READ_ONLY,
    "list_connections": READ_ONLY,
    "get_network_usage": READ_ONLY,
    "get_energy_usage": READ_ONLY,
    "kill_process": DESTRUCTIVE,
    # system: settings
    "get_system_settings": READ_ONLY,
    "set_system_settings": REPLACING,
    "set_menu_bar_settings": REPLACING,
    # system: diagnostics
    "list_crash_reports": READ_ONLY,
    "read_system_log": READ_ONLY,
    "list_startup_items": READ_ONLY,
    # volume
    "get_volume": READ_ONLY,
    "set_volume": REPLACING,
    "set_muted": REPLACING,
}

TOOLS = set(ANNOTATIONS)


async def test_server_introduces_itself(client: Client) -> None:
    info = client.server_info

    assert info is not None
    assert info.name == "mcp-server-macos"
    assert info.title == "macOS"
    assert info.version == mcp_server_macos.__version__
    assert client.instructions


async def test_tools_are_the_expected_ones(client: Client) -> None:
    listed = await client.list_tools()

    assert {tool.name for tool in listed.tools} == TOOLS
    assert len(listed.tools) == len(TOOLS), "a tool is listed twice"


async def test_tools_do_what_they_are_listed_to_do(client: Client) -> None:
    for tool in (await client.list_tools()).tools:
        assert tool.annotations == ANNOTATIONS[tool.name], tool.name


async def test_every_tool_is_described(client: Client) -> None:
    for tool in (await client.list_tools()).tools:
        assert re.fullmatch(r"[a-z][a-z0-9]*(_[a-z0-9]+)*", tool.name), "{}: not snake_case".format(tool.name)
        assert tool.title, "{}: no title".format(tool.name)
        assert tool.description and len(tool.description) > 20, "{}: no description".format(tool.name)

        # The hints a client decides with: each tool says whether it only reads, and none is left
        # for the client to assume (it would assume the worst: destructive, open to the world).
        assert tool.annotations is not None, "{}: no annotations".format(tool.name)
        assert tool.annotations.read_only_hint is not None, "{}: readOnlyHint is unset".format(tool.name)
        assert tool.annotations.open_world_hint is not None, "{}: openWorldHint is unset".format(tool.name)
        if not tool.annotations.read_only_hint:
            assert tool.annotations.destructive_hint is not None, "{}: destructiveHint is unset".format(tool.name)
            assert tool.annotations.idempotent_hint is not None, "{}: idempotentHint is unset".format(tool.name)

        for name, argument in tool.input_schema.get("properties", {}).items():
            assert argument.get("description"), "{}: the argument {} isn't described".format(tool.name, name)


async def test_unknown_tool_is_an_error(client: Client) -> None:
    result = await client.call_tool("no_such_tool", {})

    assert result.is_error
    assert "no_such_tool" in text(result)


def test_servers_are_independent() -> None:
    # Nothing is registered on a shared, module-level server: each call builds its own.
    first, second = create_server(), create_server()

    assert first is not second
    assert isinstance(first, MCPServer)
