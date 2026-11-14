"""The tools of mcp_server_macos.tools.system.processes, with macos.system faked."""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio

MIB = 1024**2


def process(pid: int, name: str, memory: Optional[int] = None, cpu_percent: Optional[float] = None) -> Any:
    """A process of this user's, when it has a memory; of another user's, when it has none."""
    own = memory is not None
    return macos.system.Process(
        pid=pid,
        name=name,
        path=Path("/Applications/{0}.app/Contents/MacOS/{0}".format(name)),
        user="me" if own else "root",
        parent_pid=1,
        started=datetime(2026, 11, 14, 9, 0, pid % 60) if own else None,
        memory=memory,
        cpu_time=timedelta(seconds=pid / 10) if own else None,
        cpu_percent=cpu_percent,
    )


def listed(found: Any) -> Dict[str, Any]:
    """What a tool says of a process."""
    return {
        "pid": found.pid,
        "name": found.name,
        "path": str(found.path),
        "user": found.user,
        "parent_pid": 1,
        "started": None if found.started is None else found.started.isoformat(),
        "memory_bytes": found.memory,
        "cpu_time_seconds": None if found.cpu_time is None else found.cpu_time.total_seconds(),
        "cpu_percent": found.cpu_percent,
    }


LAUNCHD = process(1, "launchd")
FINDER = process(310, "Finder", memory=250 * MIB)
SAFARI = process(420, "Safari", memory=1840 * MIB)
HELPER = process(421, "Safari Helper", memory=90 * MIB)
RUNNING = [LAUNCHD, FINDER, SAFARI, HELPER]


@pytest.fixture
def running(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    """Four processes, by pid, and the calls made to macos.system.processes."""
    recorder = Recorder()

    def processes(*, cpu: bool = False) -> List[Any]:
        recorder.calls.append(("processes", (), {"cpu": cpu}))
        if not cpu:
            return list(RUNNING)
        # Measured: the helper is the busy one, and another user's process has no measure.
        measures = {1: None, 310: 0.4, 420: 12.5, 421: 187.5}
        return [process(found.pid, found.name, found.memory, measures[found.pid]) for found in RUNNING]

    monkeypatch.setattr(macos.system, "processes", processes)
    return recorder


async def names(client: Client, arguments: Dict[str, Any]) -> List[str]:
    result = await client.call_tool("list_processes", arguments)
    assert not result.is_error, text(result)
    assert result.structured_content is not None
    return [found["name"] for found in result.structured_content["result"]]


async def test_list_processes(client: Client, running: Recorder) -> None:
    result = await client.call_tool("list_processes", {})

    assert not result.is_error
    assert result.structured_content == {"result": [listed(found) for found in RUNNING]}
    # The CPU isn't measured unless asked for: it takes half a second.
    assert running.calls == [("processes", (), {"cpu": False})]


async def test_list_processes_of_another_user_come_without_what_macos_keeps(client: Client, running: Recorder) -> None:
    result = await client.call_tool("list_processes", {"limit": 1})

    assert result.structured_content == {
        "result": [
            {
                "pid": 1,
                "name": "launchd",
                "path": "/Applications/launchd.app/Contents/MacOS/launchd",
                "user": "root",
                "parent_pid": 1,
                "started": None,
                "memory_bytes": None,
                "cpu_time_seconds": None,
                "cpu_percent": None,
            }
        ]
    }


@pytest.mark.parametrize(
    "arguments, expected",
    [
        ({"name": "safari"}, ["Safari", "Safari Helper"]),
        ({"name": "HELP"}, ["Safari Helper"]),
        ({"name": "nope"}, []),
        ({"limit": 2}, ["launchd", "Finder"]),
        ({"sort_by": "memory"}, ["Safari", "Finder", "Safari Helper", "launchd"]),
        ({"sort_by": "memory", "limit": 1}, ["Safari"]),
        ({"sort_by": "cpu"}, ["Safari Helper", "Safari", "Finder", "launchd"]),
        ({"sort_by": "cpu", "name": "safari", "limit": 1}, ["Safari Helper"]),
        ({"sort_by": "pid", "name": "a"}, ["launchd", "Safari", "Safari Helper"]),
    ],
)
async def test_list_processes_filtered_and_sorted(
    client: Client, running: Recorder, arguments: Dict[str, Any], expected: List[str]
) -> None:
    assert await names(client, arguments) == expected
    assert running.calls == [("processes", (), {"cpu": arguments.get("sort_by") == "cpu"})]


async def test_list_processes_by_cpu_says_the_cpu(client: Client, running: Recorder) -> None:
    result = await client.call_tool("list_processes", {"sort_by": "cpu", "limit": 2})

    assert result.structured_content is not None
    assert [found["cpu_percent"] for found in result.structured_content["result"]] == [187.5, 12.5]


@pytest.mark.parametrize("arguments", [{"limit": 0}, {"limit": 1001}, {"sort_by": "name"}, {"name": 5}])
async def test_list_processes_refuses_what_it_does_not_take(
    client: Client, running: Recorder, arguments: Dict[str, Any]
) -> None:
    result = await client.call_tool("list_processes", arguments)

    assert result.is_error
    assert running.calls == []


async def test_get_process(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.system, "process", recorder.function("process", SAFARI))

    result = await client.call_tool("get_process", {"pid": 420})

    assert not result.is_error
    assert result.structured_content == {"process": listed(SAFARI)}
    assert recorder.calls == [("process", (420,), {"cpu": False})]


async def test_get_process_with_its_cpu(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.system, "process", recorder.function("process", process(420, "Safari", 5 * MIB, 3.5)))

    result = await client.call_tool("get_process", {"pid": 420, "cpu": True})

    assert result.structured_content is not None
    assert result.structured_content["process"]["cpu_percent"] == 3.5
    assert recorder.calls == [("process", (420,), {"cpu": True})]


async def test_get_process_that_is_gone(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(macos.system, "process", Recorder().function("process", None))

    result = await client.call_tool("get_process", {"pid": 99999})

    # Not an error: a process that quit is an answer.
    assert not result.is_error
    assert result.structured_content == {"process": None}


@pytest.mark.parametrize(
    "arguments, force, said",
    [
        ({"pid": 420}, False, "Process 420 was asked to quit."),
        ({"pid": 420, "force": False}, False, "Process 420 was asked to quit."),
        ({"pid": 420, "force": True}, True, "Process 420 was ended."),
    ],
)
async def test_kill_process(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any], force: bool, said: str
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.system, "kill", recorder.function("kill"))

    result = await client.call_tool("kill_process", arguments)

    assert not result.is_error
    assert text(result) == said
    assert recorder.calls == [("kill", (420,), {"force": force})]


@pytest.mark.parametrize("arguments", [{}, {"pid": 0}, {"pid": -1}, {"pid": "Safari"}, {"pid": None}, {"force": True}])
async def test_kill_process_only_takes_the_id_of_a_process(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any]
) -> None:
    # 0 and -1 mean "every process of the group" and "every process" to the kill of Unix.
    recorder = Recorder()
    monkeypatch.setattr(macos.system, "kill", recorder.function("kill"))

    result = await client.call_tool("kill_process", arguments)

    assert result.is_error
    assert recorder.calls == []


@pytest.mark.parametrize(
    "error, expected",
    [
        (ProcessLookupError(3, "No such process"), "ProcessLookupError"),
        (PermissionError(1, "Operation not permitted"), "PermissionError"),
    ],
)
async def test_kill_process_that_is_gone_or_someone_else_s(
    client: Client, monkeypatch: pytest.MonkeyPatch, error: Exception, expected: str
) -> None:
    monkeypatch.setattr(macos.system, "kill", Recorder().function("kill", error=error))

    result = await client.call_tool("kill_process", {"pid": 1})

    assert result.is_error
    assert expected in text(result)
    # Another user's process isn't a privacy permission the user could grant.
    assert "Only the user can grant a permission" not in text(result)


async def test_list_open_files(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    files = [Path("/Users/me/notes.txt"), Path("/Users/me"), Path("/usr/bin/vim")]
    monkeypatch.setattr(macos.system, "open_files", recorder.function("open_files", files))

    result = await client.call_tool("list_open_files", {"pid": 4242})

    assert not result.is_error
    assert result.structured_content == {"result": ["/Users/me/notes.txt", "/Users/me", "/usr/bin/vim"]}
    assert recorder.calls == [("open_files", (4242,), {})]


async def test_find_processes_using(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.system, "who_uses", recorder.function("who_uses", [FINDER, SAFARI, HELPER]))

    result = await client.call_tool("find_processes_using", {"path": "/Volumes/Backup", "limit": 2})

    assert not result.is_error
    assert result.structured_content == {"result": [listed(FINDER), listed(SAFARI)]}
    assert recorder.calls == [("who_uses", ("/Volumes/Backup",), {})]


async def test_list_ports(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    ports = [
        macos.system.Port(port=5432, protocol="tcp", address="127.0.0.1", pid=900, process="postgres"),
        macos.system.Port(port=5353, protocol="udp", address="::", pid=901, process="mDNSResponder"),
    ]
    monkeypatch.setattr(macos.system, "ports", lambda: ports)

    result = await client.call_tool("list_ports", {})

    assert result.structured_content == {
        "result": [
            {"port": 5432, "protocol": "tcp", "address": "127.0.0.1", "pid": 900, "process": "postgres"},
            {"port": 5353, "protocol": "udp", "address": "::", "pid": 901, "process": "mDNSResponder"},
        ]
    }


@pytest.mark.parametrize("arguments, protocol", [({"port": 8000}, "tcp"), ({"port": 53, "protocol": "udp"}, "udp")])
async def test_find_port_owner(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any], protocol: str
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.system, "port_owner", recorder.function("port_owner", SAFARI))

    result = await client.call_tool("find_port_owner", arguments)

    assert result.structured_content == {"process": listed(SAFARI)}
    assert recorder.calls == [("port_owner", (arguments["port"], protocol), {})]


async def test_find_port_owner_of_a_free_port(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(macos.system, "port_owner", Recorder().function("port_owner", None))

    result = await client.call_tool("find_port_owner", {"port": 8000})

    assert not result.is_error
    assert result.structured_content == {"process": None}


@pytest.mark.parametrize("arguments", [{}, {"port": 0}, {"port": 65536}, {"port": 80, "protocol": "icmp"}])
async def test_find_port_owner_only_takes_a_port(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any]
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.system, "port_owner", recorder.function("port_owner", None))

    result = await client.call_tool("find_port_owner", arguments)

    assert result.is_error
    assert recorder.calls == []


async def test_list_connections(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    connections = [
        macos.system.Connection(
            protocol="tcp",
            local_address="192.168.0.2",
            local_port=65413,
            remote_address="142.250.79.46",
            remote_port=443,
            state="established",
            pid=420,
            process="Safari",
        ),
        macos.system.Connection(
            protocol="udp",
            local_address="192.168.0.2",
            local_port=5353,
            remote_address="224.0.0.251",
            remote_port=5353,
            state=None,
            pid=901,
            process="mDNSResponder",
        ),
    ]
    monkeypatch.setattr(macos.system, "connections", lambda: connections)

    result = await client.call_tool("list_connections", {})

    assert result.structured_content == {
        "result": [
            {
                "protocol": "tcp",
                "local_address": "192.168.0.2",
                "local_port": 65413,
                "remote_address": "142.250.79.46",
                "remote_port": 443,
                "state": "established",
                "pid": 420,
                "process": "Safari",
            },
            {
                "protocol": "udp",
                "local_address": "192.168.0.2",
                "local_port": 5353,
                "remote_address": "224.0.0.251",
                "remote_port": 5353,
                "state": None,
                "pid": 901,
                "process": "mDNSResponder",
            },
        ]
    }

    result = await client.call_tool("list_connections", {"limit": 1})
    assert result.structured_content is not None
    assert [found["process"] for found in result.structured_content["result"]] == ["Safari"]


@pytest.mark.parametrize("arguments, interval", [({}, None), ({"interval_seconds": 2}, 2.0)])
async def test_get_network_usage(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any], interval: Optional[float]
) -> None:
    recorder = Recorder()
    usage = [
        macos.system.NetworkUsage(pid=420, process="Safari", received=5000000, sent=40000),
        macos.system.NetworkUsage(pid=7, process="mDNSResponder", received=10, sent=20),
    ]
    monkeypatch.setattr(macos.system, "network_usage", recorder.function("network_usage", usage))

    result = await client.call_tool("get_network_usage", {**arguments, "limit": 1})

    assert not result.is_error
    assert result.structured_content == {
        "result": [{"pid": 420, "process": "Safari", "received_bytes": 5000000, "sent_bytes": 40000}]
    }
    assert recorder.calls == [("network_usage", (interval,), {})]


async def test_get_energy_usage(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    usage = [macos.system.EnergyUsage(pid=420, process="Safari", watts=1.84, disk_read=4096, disk_written=0)]
    monkeypatch.setattr(macos.system, "energy_usage", recorder.function("energy_usage", usage))

    result = await client.call_tool("get_energy_usage", {})

    assert not result.is_error
    assert result.structured_content == {
        "result": [{"pid": 420, "process": "Safari", "watts": 1.84, "disk_read_bytes": 4096, "disk_written_bytes": 0}]
    }
    assert recorder.calls == [("energy_usage", (1.0,), {})]


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("get_network_usage", {"interval_seconds": 0.5}),
        ("get_network_usage", {"interval_seconds": 61}),
        ("get_energy_usage", {"interval_seconds": 0}),
        ("get_energy_usage", {"interval_seconds": 3600}),
        ("get_energy_usage", {"limit": 0}),
    ],
)
async def test_usage_is_not_measured_for_too_long(
    client: Client, monkeypatch: pytest.MonkeyPatch, tool: str, arguments: Dict[str, Any]
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.system, "network_usage", recorder.function("network_usage", []))
    monkeypatch.setattr(macos.system, "energy_usage", recorder.function("energy_usage", []))

    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert recorder.calls == []


async def test_get_energy_usage_on_a_macos_too_old(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    error = macos.NotSupportedError("macOS 12 doesn't report the energy processes use")
    monkeypatch.setattr(macos.system, "energy_usage", Recorder().function("energy_usage", error=error))

    result = await client.call_tool("get_energy_usage", {})

    assert result.is_error
    assert "NotSupportedError: macOS 12 doesn't report" in text(result)
