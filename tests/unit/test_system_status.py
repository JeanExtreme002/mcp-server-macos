"""The tools of mcp_server_macos.tools.system.status, with macos.system faked."""

from datetime import timedelta
from typing import Any, Dict

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder

pytestmark = pytest.mark.anyio

GIB = 1024**3


@pytest.fixture
def mac(monkeypatch: pytest.MonkeyPatch) -> None:
    """A MacBook at work, lid open."""
    usage = macos.system.MemoryUsage(total=16 * GIB, used=12 * GIB, wired=4 * GIB, compressed=2 * GIB, cached=1 * GIB)
    monkeypatch.setattr(macos.system, "cpu_usage", lambda: 0.3834)
    monkeypatch.setattr(macos.system, "memory_usage", lambda: usage)
    monkeypatch.setattr(macos.system, "thermal_state", lambda: "fair")
    monkeypatch.setattr(macos.system, "idle_time", lambda: timedelta(minutes=2, seconds=5.7))
    monkeypatch.setattr(macos.system, "lid_closed", lambda: False)
    monkeypatch.setattr(macos.system, "camera_in_use", lambda: True)
    monkeypatch.setattr(macos.system, "microphone_in_use", lambda: False)


@pytest.mark.usefixtures("mac")
async def test_get_system_status(client: Client) -> None:
    result = await client.call_tool("get_system_status", {})

    assert not result.is_error
    assert result.structured_content == {
        "cpu_percent": 38.3,  # pymacos says 0.0 to 1.0
        "memory": {
            "total_bytes": 16 * GIB,
            "used_bytes": 12 * GIB,
            "wired_bytes": 4 * GIB,
            "compressed_bytes": 2 * GIB,
            "cached_bytes": 1 * GIB,
            "free_bytes": 4 * GIB,
            "used_percent": 75.0,
        },
        "thermal_state": "fair",
        "idle_seconds": 125,
        "lid_closed": False,
        "camera_in_use": True,
        "microphone_in_use": False,
    }


@pytest.mark.usefixtures("mac")
async def test_get_system_status_of_a_mac_without_a_lid(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    def lid_closed() -> bool:
        raise macos.NotSupportedError("this Mac has no lid")

    monkeypatch.setattr(macos.system, "lid_closed", lid_closed)

    result = await client.call_tool("get_system_status", {})

    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["lid_closed"] is None


async def test_get_gpu_usage(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    gpus = [
        macos.system.GPUUsage(name="AGXAcceleratorG14X", percent=37, memory=406667264),
        macos.system.GPUUsage(name="Radeon", percent=0, memory=None),
    ]
    monkeypatch.setattr(macos.system, "gpu_usage", lambda: gpus)

    result = await client.call_tool("get_gpu_usage", {})

    assert result.structured_content == {
        "result": [
            {"name": "AGXAcceleratorG14X", "percent": 37, "memory_bytes": 406667264},
            {"name": "Radeon", "percent": 0, "memory_bytes": None},
        ]
    }


@pytest.mark.parametrize("idle", [True, False])
async def test_wait_for_idle(client: Client, monkeypatch: pytest.MonkeyPatch, idle: bool) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.system, "wait_for_idle", recorder.function("wait_for_idle", idle))

    result = await client.call_tool("wait_for_idle", {"idle_seconds": 300, "timeout_seconds": 400})

    assert not result.is_error
    assert result.structured_content == {"idle": idle}  # false: the time ran out, which isn't an error
    assert recorder.calls == [("wait_for_idle", (300.0,), {"timeout": 400.0})]


@pytest.mark.parametrize("active", [True, False])
async def test_wait_for_user_activity(client: Client, monkeypatch: pytest.MonkeyPatch, active: bool) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.system, "wait_for_activity", recorder.function("wait_for_activity", active))

    result = await client.call_tool("wait_for_user_activity", {})

    assert result.structured_content == {"active": active}
    assert recorder.calls == [("wait_for_activity", (), {"timeout": 60.0})]


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("wait_for_idle", {}),
        ("wait_for_idle", {"idle_seconds": 0}),
        ("wait_for_idle", {"idle_seconds": 601}),
        ("wait_for_idle", {"idle_seconds": 10, "timeout_seconds": 601}),
        ("wait_for_idle", {"idle_seconds": 10, "timeout_seconds": 0}),
        ("wait_for_user_activity", {"timeout_seconds": 86400}),
        ("wait_for_user_activity", {"timeout_seconds": -1}),
    ],
)
async def test_waits_do_not_last_forever(
    client: Client, monkeypatch: pytest.MonkeyPatch, tool: str, arguments: Dict[str, Any]
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.system, "wait_for_idle", recorder.function("wait_for_idle", True))
    monkeypatch.setattr(macos.system, "wait_for_activity", recorder.function("wait_for_activity", True))

    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert recorder.calls == []
