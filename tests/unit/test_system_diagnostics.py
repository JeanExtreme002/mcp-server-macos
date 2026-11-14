"""The tools of mcp_server_macos.tools.system.diagnostics, with macos.system faked."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio

BRT = timezone(timedelta(hours=-3))


async def test_list_crash_reports(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    crashes = [
        macos.system.CrashReport(
            app="Safari",
            version="18.6",
            date=datetime(2026, 11, 14, 1, 33, 9, tzinfo=BRT),
            reason="EXC_BAD_ACCESS (SIGSEGV)",
            path=Path("/Users/me/Library/Logs/DiagnosticReports/Safari-2026-11-14-013309.ips"),
        ),
        macos.system.CrashReport(app="helper", version=None, date=None, reason=None, path=Path("/Library/Logs/helper.ips")),
    ]
    monkeypatch.setattr(macos.system, "crash_reports", recorder.function("crash_reports", crashes))

    result = await client.call_tool("list_crash_reports", {})

    assert not result.is_error
    assert result.structured_content == {
        "result": [
            {
                "app": "Safari",
                "version": "18.6",
                "date": "2026-11-14T01:33:09-03:00",
                "reason": "EXC_BAD_ACCESS (SIGSEGV)",
                "path": "/Users/me/Library/Logs/DiagnosticReports/Safari-2026-11-14-013309.ips",
            },
            {"app": "helper", "version": None, "date": None, "reason": None, "path": "/Library/Logs/helper.ips"},
        ]
    }
    assert recorder.calls == [("crash_reports", (None,), {"since": None})]


async def test_list_crash_reports_of_an_app_since_a_moment(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    crash = macos.system.CrashReport(app="Safari", version=None, date=None, reason=None, path=Path("/a.ips"))
    monkeypatch.setattr(macos.system, "crash_reports", recorder.function("crash_reports", [crash] * 5))

    result = await client.call_tool(
        "list_crash_reports", {"app": "safari", "since": "2026-11-07T00:00:00-03:00", "limit": 2}
    )

    assert not result.is_error
    assert result.structured_content is not None
    assert len(result.structured_content["result"]) == 2
    assert recorder.calls == [("crash_reports", ("safari",), {"since": datetime(2026, 11, 7, tzinfo=BRT)})]


@pytest.mark.parametrize("arguments", [{"since": "last week"}, {"limit": 0}, {"limit": 501}, {"app": 5}])
async def test_list_crash_reports_refuses_what_it_does_not_take(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any]
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.system, "crash_reports", recorder.function("crash_reports", []))

    result = await client.call_tool("list_crash_reports", arguments)

    assert result.is_error
    assert recorder.calls == []


async def test_read_system_log(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    entries = [
        macos.system.LogEntry(
            date=datetime(2026, 11, 14, 7, 2, 12, 220344, tzinfo=BRT),
            process="bluetoothd",
            pid=757,
            subsystem="com.apple.bluetooth",
            category="Server",
            level="error",
            message="Connection to <private> failed",
        ),
        macos.system.LogEntry(
            date=None, process="kernel", pid=None, subsystem=None, category=None, level="default", message="wake"
        ),
    ]
    monkeypatch.setattr(macos.system, "logs", recorder.function("logs", entries))

    result = await client.call_tool("read_system_log", {})

    assert not result.is_error
    assert result.structured_content == {
        "result": [
            {
                "date": "2026-11-14T07:02:12.220344-03:00",
                "process": "bluetoothd",
                "pid": 757,
                "subsystem": "com.apple.bluetooth",
                "category": "Server",
                "level": "error",
                "message": "Connection to <private> failed",
            },
            {
                "date": None,
                "process": "kernel",
                "pid": None,
                "subsystem": None,
                "category": None,
                "level": "default",
                "message": "wake",
            },
        ]
    }
    # Ten minutes back and 200 messages at most, unless told otherwise: the log is large.
    assert recorder.calls == [
        ("logs", (), {"process": None, "subsystem": None, "contains": None, "level": None, "last": "10m", "limit": 200})
    ]


async def test_read_system_log_filtered(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.system, "logs", recorder.function("logs", []))

    result = await client.call_tool(
        "read_system_log",
        {
            "process": "Safari",
            "subsystem": "com.apple.WebKit",
            "contains": "crash",
            "level": "error",
            "last": "2h",
            "limit": 5,
        },
    )

    assert not result.is_error
    assert result.structured_content == {"result": []}
    assert recorder.calls == [
        (
            "logs",
            (),
            {
                "process": "Safari",
                "subsystem": "com.apple.WebKit",
                "contains": "crash",
                "level": "error",
                "last": "2h",
                "limit": 5,
            },
        )
    ]


@pytest.mark.parametrize("last", ["30s", "10m", "2h", "1d", "120m"])
async def test_read_system_log_goes_as_far_back_as_pymacos_takes(
    client: Client, monkeypatch: pytest.MonkeyPatch, last: str
) -> None:
    monkeypatch.setattr(macos.system, "logs", Recorder().function("logs", []))

    result = await client.call_tool("read_system_log", {"last": last})

    assert not result.is_error, text(result)


@pytest.mark.parametrize(
    "arguments",
    [
        {"last": "soon"},
        {"last": "10"},
        {"last": "10 minutes"},
        {"last": "-5m"},
        {"last": "1w"},
        {"level": "warning"},
        {"limit": 0},
        {"limit": 1001},
    ],
)
async def test_read_system_log_refuses_what_it_does_not_take(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any]
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.system, "logs", recorder.function("logs", []))

    result = await client.call_tool("read_system_log", arguments)

    assert result.is_error
    assert recorder.calls == []


async def test_read_system_log_that_takes_too_long(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    error = macos.CommandTimeoutError(["log", "show"], 120.0)
    monkeypatch.setattr(macos.system, "logs", Recorder().function("logs", error=error))

    result = await client.call_tool("read_system_log", {"last": "7d"})

    assert result.is_error
    assert "CommandTimeoutError" in text(result)


async def test_list_startup_items(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    items = [
        macos.system.StartupItem(
            label="com.google.keystone.agent",
            kind="agent",
            for_all_users=False,
            program="/Library/Google/GoogleSoftwareUpdate/ksagent",
            arguments=("/Library/Google/GoogleSoftwareUpdate/ksagent", "-runMode", "ifneeded"),
            run_at_load=True,
            keep_alive=False,
            enabled=True,
            running=False,
            path=Path("/Users/me/Library/LaunchAgents/com.google.keystone.agent.plist"),
        ),
        macos.system.StartupItem(
            label="com.docker.vmnetd",
            kind="daemon",
            for_all_users=True,
            program=None,
            arguments=(),
            run_at_load=False,
            keep_alive=True,
            enabled=False,
            running=None,
            path=Path("/Library/LaunchDaemons/com.docker.vmnetd.plist"),
        ),
    ]
    monkeypatch.setattr(macos.system, "startup_items", lambda: items)

    result = await client.call_tool("list_startup_items", {})

    assert not result.is_error
    assert result.structured_content == {
        "result": [
            {
                "label": "com.google.keystone.agent",
                "kind": "agent",
                "for_all_users": False,
                "program": "/Library/Google/GoogleSoftwareUpdate/ksagent",
                "arguments": ["/Library/Google/GoogleSoftwareUpdate/ksagent", "-runMode", "ifneeded"],
                "run_at_load": True,
                "keep_alive": False,
                "enabled": True,
                "running": False,
                "path": "/Users/me/Library/LaunchAgents/com.google.keystone.agent.plist",
            },
            {
                "label": "com.docker.vmnetd",
                "kind": "daemon",
                "for_all_users": True,
                "program": None,
                "arguments": [],
                "run_at_load": False,
                "keep_alive": True,
                "enabled": False,
                "running": None,
                "path": "/Library/LaunchDaemons/com.docker.vmnetd.plist",
            },
        ]
    }
