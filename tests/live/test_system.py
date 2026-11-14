"""The system tools against this Mac: read, mostly, and what they change is made for the test and undone."""

import os
import re
import socket
import subprocess
from pathlib import Path

import macos
import pytest
from mcp import Client

from tests.helpers import text
from tests.live.helpers import call

pytestmark = pytest.mark.anyio


async def test_get_system_info(client: Client) -> None:
    result = await client.call_tool("get_system_info", {})

    assert not result.is_error, text(result)
    info = result.structured_content
    assert info is not None
    assert re.fullmatch(r"\d+\.\d+(\.\d+)?", info["macos_version"]), info
    assert info["macos_build"]
    assert info["model"]
    assert info["model_identifier"]
    assert info["processor"]
    assert info["memory_bytes"] >= 1024**3
    assert info["computer_name"]
    assert info["uptime_seconds"] > 0


async def test_get_system_status(client: Client) -> None:
    status = await call(client, "get_system_status")

    assert 0 <= status["cpu_percent"] <= 100
    assert status["memory"]["total_bytes"] >= 1024**3
    assert 0 < status["memory"]["used_bytes"] <= status["memory"]["total_bytes"]
    assert 0 < status["memory"]["used_percent"] <= 100
    assert status["thermal_state"] in ("nominal", "fair", "serious", "critical", "unknown")
    assert status["idle_seconds"] >= 0
    assert status["lid_closed"] in (True, False, None)
    assert isinstance(status["camera_in_use"], bool)
    assert isinstance(status["microphone_in_use"], bool)


async def test_what_the_mac_is(client: Client) -> None:
    security = await call(client, "get_security_status")
    assert set(security) == {"filevault", "firewall", "gatekeeper", "system_integrity_protection"}

    fonts = await call(client, "list_fonts", {"search": "helvetica"})
    assert "Helvetica" in fonts
    assert len(await call(client, "list_fonts")) > len(fonts)

    for device in await call(client, "list_usb_devices"):
        assert isinstance(device["is_hub"], bool)

    for gpu in await call(client, "get_gpu_usage"):
        assert 0 <= gpu["percent"] <= 100


async def test_disks(client: Client) -> None:
    volumes = await call(client, "list_volumes")
    assert volumes[0]["path"] == "/"  # the startup disk first
    assert 0 < volumes[0]["free_bytes"] < volumes[0]["total_bytes"]

    disks = await call(client, "get_disk_health")
    assert disks, "a Mac has a disk"
    assert all(disk["smart"] in ("verified", "failing", None) for disk in disks)


async def test_disk_image_is_mounted_and_unmounted(client: Client, tmp_path: Path) -> None:
    image = tmp_path / "mcp-server-macos test.dmg"
    subprocess.run(
        ["hdiutil", "create", "-size", "2m", "-fs", "HFS+", "-volname", "MCP Server Test", str(image)],
        check=True,
        capture_output=True,
        timeout=120,
    )

    mounted = (await call(client, "mount_disk_image", {"path": str(image)}))["mount_point"]
    try:
        # Mounted without showing in Finder, so list_volumes, which lists what Finder shows, leaves it out.
        assert Path(mounted).is_dir()
        assert Path(mounted).name == "MCP Server Test"
    finally:
        result = await client.call_tool("unmount_disk_image", {"mount_point": mounted})

    assert not result.is_error, text(result)
    assert not Path(mounted).exists()


async def test_volume_that_does_not_exist_is_not_ejected(client: Client) -> None:
    result = await client.call_tool("eject_volume", {"volume": "no volume is named like this"})

    assert result.is_error
    assert "ValueError" in text(result)


async def test_processes(client: Client, tmp_path: Path) -> None:
    own = os.getpid()

    found = (await call(client, "get_process", {"pid": own, "cpu": True}))["process"]
    assert found["pid"] == own
    assert found["memory_bytes"] > 0
    assert found["cpu_percent"] is not None

    by_memory = await call(client, "list_processes", {"sort_by": "memory", "limit": 5})
    assert len(by_memory) == 5
    memories = [found["memory_bytes"] or 0 for found in by_memory]
    assert memories == sorted(memories, reverse=True)

    everything = await call(client, "list_processes", {"limit": 1000})
    assert own in [found["pid"] for found in everything]
    assert [found["pid"] for found in everything] == sorted(found["pid"] for found in everything)

    # A file this test holds open is among its open files, and this process among the ones using it.
    held = tmp_path / "held open.txt"
    with held.open("w"):
        files = await call(client, "list_open_files", {"pid": own})
        assert str(held.resolve()) in [str(Path(path).resolve()) for path in files]

        using = await call(client, "find_processes_using", {"path": str(held)})
        assert [found["pid"] for found in using] == [own]

    assert await call(client, "find_processes_using", {"path": str(held)}) == []


async def test_process_is_asked_to_quit_then_gone(client: Client) -> None:
    # A process of this test's own, which nothing else needs.
    sleeper = subprocess.Popen(["sleep", "300"])
    try:
        assert (await call(client, "get_process", {"pid": sleeper.pid}))["process"]["name"] == "sleep"

        result = await client.call_tool("kill_process", {"pid": sleeper.pid})
        assert not result.is_error, text(result)
        assert sleeper.wait(timeout=30) != 0
    finally:
        sleeper.kill()
        sleeper.wait()

    assert (await call(client, "get_process", {"pid": sleeper.pid}))["process"] is None
    result = await client.call_tool("kill_process", {"pid": sleeper.pid, "force": True})
    assert result.is_error
    assert "ProcessLookupError" in text(result)


async def test_port_is_found_with_its_owner(client: Client) -> None:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]

        ports = await call(client, "list_ports")
        assert (port, "tcp", os.getpid()) in [(found["port"], found["protocol"], found["pid"]) for found in ports]

        owner = (await call(client, "find_port_owner", {"port": port}))["process"]
        assert owner["pid"] == os.getpid()

    assert (await call(client, "find_port_owner", {"port": port}))["process"] is None

    for connection in await call(client, "list_connections", {"limit": 20}):
        assert connection["protocol"] in ("tcp", "udp")


async def test_usage_by_process(client: Client) -> None:
    for use in await call(client, "get_network_usage", {"limit": 5}):
        assert use["received_bytes"] >= 0 and use["sent_bytes"] >= 0

    result = await client.call_tool("get_energy_usage", {"interval_seconds": 0.3, "limit": 5})
    if result.is_error and "NotSupportedError" in text(result):
        pytest.skip("this macOS doesn't report the energy processes use")
    assert not result.is_error, text(result)


async def test_system_settings_are_read_and_none_is_changed(client: Client) -> None:
    settings = await call(client, "get_system_settings")

    assert settings["measurement_units"] in ("metric", "us")
    assert settings["temperature_unit"] in ("celsius", "fahrenheit")
    assert settings["menu_bar"]["clock"]["date"] in ("auto", "always", "never")
    assert set(settings["menu_bar"]["items"]) <= set(macos.system.MENU_BAR_ITEMS)

    # Refused before anything is changed.
    result = await client.call_tool("set_menu_bar_settings", {"items": {"airdrop": True}, "clock_seconds": True})
    assert result.is_error
    assert await call(client, "get_system_settings") == settings


async def test_diagnostics(client: Client) -> None:
    for crash in await call(client, "list_crash_reports", {"limit": 3}):
        assert crash["app"] and crash["path"]

    for entry in await call(client, "read_system_log", {"last": "1m", "limit": 5}):
        assert entry["level"] in ("default", "info", "debug", "error", "fault")

    for item in await call(client, "list_startup_items"):
        assert item["kind"] in ("agent", "daemon")
        assert item["path"].endswith(".plist")


async def test_waiting_for_the_mac_to_be_left_alone(client: Client) -> None:
    # Either answer is right: nobody touched the Mac in the last ten minutes (a machine running the
    # tests unattended), or the half second ran out. The unit tests hold each to its case.
    waited = await call(client, "wait_for_idle", {"idle_seconds": 600, "timeout_seconds": 0.5})

    assert waited in ({"idle": True}, {"idle": False})
