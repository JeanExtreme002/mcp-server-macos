"""The tools of mcp_server_macos.tools.time_machine, with macos.time_machine faked: no backup is made."""

from datetime import datetime
from typing import Any, Dict

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


@pytest.fixture
def time_machine(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    recorder = Recorder()
    monkeypatch.setattr(macos.time_machine, "destinations", lambda: ["Backup Disk"])
    monkeypatch.setattr(macos.time_machine, "is_backing_up", lambda: True)
    monkeypatch.setattr(macos.time_machine, "progress", lambda: 0.4237)
    monkeypatch.setattr(macos.time_machine, "last_backup", lambda: datetime(2026, 11, 14, 23, 10, 4))
    monkeypatch.setattr(macos.time_machine, "is_excluded", recorder.function("is_excluded", True))
    for name in ("backup_now", "stop_backup", "exclude", "include"):
        monkeypatch.setattr(macos.time_machine, name, recorder.function(name))
    return recorder


async def test_get_backup_status(client: Client, time_machine: Recorder) -> None:
    result = await client.call_tool("get_backup_status", {})

    assert not result.is_error
    assert result.structured_content == {
        "destinations": ["Backup Disk"],
        "backing_up": True,
        "progress_percent": 42.4,  # pymacos says 0.0 to 1.0
        "last_backup": "2026-11-14T23:10:04",
        "last_backup_readable": True,
    }


async def test_get_backup_status_without_full_disk_access(
    client: Client, time_machine: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The date can't be read: said apart from "no backup yet", and the rest still answers.
    def last_backup() -> Any:
        raise macos.PermissionDeniedError("reading the backups needs Full Disk Access")

    monkeypatch.setattr(macos.time_machine, "last_backup", last_backup)
    monkeypatch.setattr(macos.time_machine, "progress", lambda: None)

    result = await client.call_tool("get_backup_status", {})

    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["last_backup"] is None
    assert result.structured_content["last_backup_readable"] is False
    assert result.structured_content["progress_percent"] is None
    assert result.structured_content["destinations"] == ["Backup Disk"]


@pytest.mark.parametrize(
    "tool, call, said",
    [("start_backup", "backup_now", "Backup started."), ("stop_backup", "stop_backup", "Backup stopped.")],
)
async def test_backups_are_started_and_stopped(client: Client, time_machine: Recorder, tool: str, call: str, said: str) -> None:
    result = await client.call_tool(tool, {})

    assert text(result) == said
    # Started without waiting: a backup can take hours.
    assert time_machine.calls == [(call, (), {})]


@pytest.mark.parametrize(
    "excluded, call, said",
    [
        (True, "exclude", "~/code/node_modules is left out of the backups."),
        (False, "include", "~/code/node_modules is backed up."),
    ],
)
async def test_set_backup_exclusion(client: Client, time_machine: Recorder, excluded: bool, call: str, said: str) -> None:
    result = await client.call_tool("set_backup_exclusion", {"path": "~/code/node_modules", "excluded": excluded})

    assert text(result) == said
    assert time_machine.calls == [(call, ("~/code/node_modules",), {})]


async def test_check_backup_exclusion(client: Client, time_machine: Recorder) -> None:
    result = await client.call_tool("check_backup_exclusion", {"path": "~/Library/Caches"})

    assert result.structured_content == {"excluded": True}
    assert time_machine.calls == [("is_excluded", ("~/Library/Caches",), {})]


async def test_exclusion_in_a_protected_folder_says_what_to_allow(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    error = macos.PermissionDeniedError("~/Library/Mail is protected")
    monkeypatch.setattr(macos.time_machine, "exclude", Recorder().function("exclude", error=error))

    result = await client.call_tool("set_backup_exclusion", {"path": "~/Library/Mail", "excluded": True})

    assert result.is_error
    assert "System Settings › Privacy & Security › Full Disk Access" in text(result)


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("set_backup_exclusion", {"path": "~/x"}),
        ("set_backup_exclusion", {"path": "", "excluded": True}),
        ("check_backup_exclusion", {}),
        ("check_backup_exclusion", {"path": ""}),
    ],
)
async def test_exclusions_need_a_path(client: Client, time_machine: Recorder, tool: str, arguments: Dict[str, Any]) -> None:
    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert time_machine.calls == []
