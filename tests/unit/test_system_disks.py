"""The tools of mcp_server_macos.tools.system.disks, with macos.system faked."""

from pathlib import Path
from typing import Any, Dict

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


@pytest.fixture
def disks(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    """The calls made to the functions of macos.system that mount and unmount."""
    recorder = Recorder()
    monkeypatch.setattr(macos.system, "eject", recorder.function("eject"))
    monkeypatch.setattr(macos.system, "mount_image", recorder.function("mount_image", Path("/Volumes/Tool")))
    monkeypatch.setattr(macos.system, "unmount_image", recorder.function("unmount_image"))
    return recorder


async def test_list_volumes(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    volumes = [
        macos.system.Volume(
            name="Macintosh HD",
            path=Path("/"),
            total=494384795648,
            free=176987188988,
            is_internal=True,
            is_removable=False,
            is_ejectable=False,
        ),
        macos.system.Volume(
            name="My Backup",
            path=Path("/Volumes/My Backup"),
            total=2000000000000,
            free=0,
            is_internal=False,
            is_removable=True,
            is_ejectable=True,
        ),
    ]
    monkeypatch.setattr(macos.system, "volumes", lambda: volumes)

    result = await client.call_tool("list_volumes", {})

    assert not result.is_error
    assert result.structured_content == {
        "result": [
            {
                "name": "Macintosh HD",
                "path": "/",
                "total_bytes": 494384795648,
                "free_bytes": 176987188988,
                "is_internal": True,
                "is_removable": False,
                "is_ejectable": False,
            },
            {
                "name": "My Backup",
                "path": "/Volumes/My Backup",
                "total_bytes": 2000000000000,
                "free_bytes": 0,
                "is_internal": False,
                "is_removable": True,
                "is_ejectable": True,
            },
        ]
    }


async def test_get_disk_health(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    disks = [
        macos.system.DiskHealth(
            device="disk0", name="APPLE SSD AP0512Z", size=500277792768, internal=True, solid_state=True, smart="verified"
        ),
        macos.system.DiskHealth(device="disk4", name="USB Stick", size=32000000000, internal=False, solid_state=None, smart=None),
    ]
    monkeypatch.setattr(macos.system, "disk_health", lambda: disks)

    result = await client.call_tool("get_disk_health", {})

    assert result.structured_content == {
        "result": [
            {
                "device": "disk0",
                "name": "APPLE SSD AP0512Z",
                "size_bytes": 500277792768,
                "internal": True,
                "solid_state": True,
                "smart": "verified",
            },
            {
                "device": "disk4",
                "name": "USB Stick",
                "size_bytes": 32000000000,
                "internal": False,
                "solid_state": None,
                "smart": None,
            },
        ]
    }


@pytest.mark.parametrize("volume", ["Backup", "/Volumes/My Backup"])
async def test_eject_volume(client: Client, disks: Recorder, volume: str) -> None:
    result = await client.call_tool("eject_volume", {"volume": volume})

    assert not result.is_error
    assert text(result) == "Ejected {}.".format(volume)
    assert disks.calls == [("eject", (volume,), {})]


async def test_eject_volume_that_is_busy_says_who_holds_it(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    error = macos.CommandError(["diskutil"], 1, "Volume Backup failed to unmount: dissented by PID 4242 (Preview)")
    monkeypatch.setattr(macos.system, "eject", Recorder().function("eject", error=error))

    result = await client.call_tool("eject_volume", {"volume": "Backup"})

    assert result.is_error
    assert "CommandError" in text(result)
    assert "dissented by PID 4242 (Preview)" in text(result)


async def test_mount_disk_image(client: Client, disks: Recorder) -> None:
    result = await client.call_tool("mount_disk_image", {"path": "/Users/me/Downloads/Tool.dmg"})

    assert not result.is_error
    assert result.structured_content == {"mount_point": "/Volumes/Tool"}
    assert disks.calls == [("mount_image", ("/Users/me/Downloads/Tool.dmg",), {})]


async def test_mount_disk_image_that_is_missing(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(macos.system, "mount_image", Recorder().function("mount_image", error=FileNotFoundError("/nope.dmg")))

    result = await client.call_tool("mount_disk_image", {"path": "/nope.dmg"})

    assert result.is_error
    assert "FileNotFoundError: /nope.dmg" in text(result)


@pytest.mark.parametrize("arguments, force", [({}, False), ({"force": False}, False), ({"force": True}, True)])
async def test_unmount_disk_image(client: Client, disks: Recorder, arguments: Dict[str, Any], force: bool) -> None:
    result = await client.call_tool("unmount_disk_image", {"mount_point": "/Volumes/Tool", **arguments})

    assert not result.is_error
    assert text(result) == "Unmounted /Volumes/Tool."
    assert disks.calls == [("unmount_image", ("/Volumes/Tool",), {"force": force})]


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("eject_volume", {}),
        ("eject_volume", {"volume": ""}),
        ("eject_volume", {"volume": None}),
        ("mount_disk_image", {}),
        ("mount_disk_image", {"path": ""}),
        ("unmount_disk_image", {}),
        ("unmount_disk_image", {"mount_point": ""}),
        ("unmount_disk_image", {"mount_point": "/Volumes/Tool", "force": "yes please"}),
    ],
)
async def test_disks_are_not_touched_without_knowing_which(
    client: Client, disks: Recorder, tool: str, arguments: Dict[str, Any]
) -> None:
    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert disks.calls == []
