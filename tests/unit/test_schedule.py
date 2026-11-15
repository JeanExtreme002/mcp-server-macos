"""The tools of mcp_server_macos.tools.schedule, with macos.schedule faked: nothing is scheduled."""

from pathlib import Path
from typing import Any, Dict

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio

JOB = macos.schedule.Job(
    name="report",
    script=Path("/Users/me/report.py"),
    args=("--quiet",),
    every=None,
    at=("09:00", "18:30"),
    weekdays=("mon", "fri"),
    at_login=False,
    when_changed=(Path("/Users/me/Inbox"),),
    at_mount=False,
    paused=False,
    log=Path("/Users/me/Library/Logs/pymacos/report.log"),
    running=False,
    last_exit_status=0,
)
LISTED = {
    "name": "report",
    "script": "/Users/me/report.py",
    "args": ["--quiet"],
    "every_seconds": None,
    "at": ["09:00", "18:30"],
    "weekdays": ["mon", "fri"],
    "at_login": False,
    "when_changed": ["/Users/me/Inbox"],
    "at_mount": False,
    "paused": False,
    "log": "/Users/me/Library/Logs/pymacos/report.log",
    "running": False,
    "last_exit_status": 0,
}


@pytest.fixture
def schedule(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    recorder = Recorder()
    monkeypatch.setattr(macos.schedule, "jobs", lambda: [JOB])
    monkeypatch.setattr(macos.schedule, "get", lambda name: JOB if name == "report" else None)
    monkeypatch.setattr(macos.schedule, "add", recorder.function("add", JOB))
    monkeypatch.setattr(macos.schedule, "remove", recorder.function("remove", True))
    for name in ("run_now", "pause", "resume"):
        monkeypatch.setattr(macos.schedule, name, recorder.function(name))
    return recorder


async def test_list_and_get_scheduled_jobs(client: Client, schedule: Recorder) -> None:
    listed = await client.call_tool("list_scheduled_jobs", {})
    found = await client.call_tool("get_scheduled_job", {"name": "report"})
    missing = await client.call_tool("get_scheduled_job", {"name": "nope"})

    assert listed.structured_content == {"result": [LISTED]}
    assert found.structured_content == {"job": LISTED}
    assert missing.structured_content == {"job": None}


async def test_schedule_script(client: Client, schedule: Recorder) -> None:
    result = await client.call_tool(
        "schedule_script",
        {
            "name": "report",
            "script": "~/report.py",
            "at": ["09:00", "18:30"],
            "weekdays": ["mon", "fri"],
            "when_changed": ["~/Inbox"],
            "args": ["--quiet"],
            "python": "~/.venv/bin/python",
        },
    )

    assert not result.is_error, text(result)
    assert result.structured_content == LISTED
    assert schedule.calls == [
        (
            "add",
            ("report", "~/report.py"),
            {
                "every": None,
                "at": ["09:00", "18:30"],
                "weekdays": ["mon", "fri"],
                "at_login": False,
                "when_changed": ["~/Inbox"],
                "at_mount": False,
                "args": ["--quiet"],
                "python": "~/.venv/bin/python",
            },
        )
    ]


async def test_schedule_script_every_hour(client: Client, schedule: Recorder) -> None:
    await client.call_tool("schedule_script", {"name": "backup", "script": "backup.py", "every_seconds": 3600, "at_mount": True})

    ((_, arguments, options),) = schedule.calls
    assert arguments == ("backup", "backup.py")
    assert options == {
        "every": 3600.0,
        "at": None,
        "weekdays": None,
        "at_login": False,
        "when_changed": None,
        "at_mount": True,
        "args": (),
        "python": None,
    }


async def test_schedule_script_that_pymacos_refuses(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    error = ValueError("every and at can't go together")
    monkeypatch.setattr(macos.schedule, "add", Recorder().function("add", error=error))

    result = await client.call_tool("schedule_script", {"name": "x", "script": "x.py", "every_seconds": 60, "at": ["09:00"]})

    assert result.is_error
    assert "every and at can't go together" in text(result)


@pytest.mark.parametrize(
    "tool, call, said",
    [
        ("run_scheduled_job_now", "run_now", "report started."),
        ("pause_scheduled_job", "pause", "report is paused."),
        ("resume_scheduled_job", "resume", "report is back on its schedule."),
    ],
)
async def test_jobs_are_run_paused_and_resumed(client: Client, schedule: Recorder, tool: str, call: str, said: str) -> None:
    result = await client.call_tool(tool, {"name": "report"})

    assert text(result) == said
    assert schedule.calls == [(call, ("report",), {})]


@pytest.mark.parametrize("existed", [True, False])
async def test_remove_scheduled_job(client: Client, monkeypatch: pytest.MonkeyPatch, existed: bool) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.schedule, "remove", recorder.function("remove", existed))

    result = await client.call_tool("remove_scheduled_job", {"name": "report"})

    assert result.structured_content == {"existed": existed}
    assert recorder.calls == [("remove", ("report",), {})]


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("schedule_script", {"name": "x"}),
        ("schedule_script", {"script": "x.py"}),
        ("schedule_script", {"name": "", "script": "x.py"}),
        ("schedule_script", {"name": "x", "script": "x.py", "every_seconds": 0}),
        ("schedule_script", {"name": "x", "script": "x.py", "at": []}),
        ("schedule_script", {"name": "x", "script": "x.py", "at": ["09:00"], "weekdays": ["monday"]}),
        ("run_scheduled_job_now", {}),
        ("remove_scheduled_job", {"name": ""}),
    ],
)
async def test_jobs_are_not_touched_without_knowing_which(
    client: Client, schedule: Recorder, tool: str, arguments: Dict[str, Any]
) -> None:
    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert schedule.calls == []
