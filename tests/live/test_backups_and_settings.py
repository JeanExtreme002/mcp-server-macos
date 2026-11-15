"""
Time Machine, the settings, the printers, the scheduled scripts and the music players against this Mac.

They're read, mostly: no backup is started, no setting is changed, nothing is printed or scheduled,
and no player is opened. One folder of the tests' own is left out of the backups and put back.
"""

import shutil
import tempfile
from pathlib import Path
from typing import Iterator

import pytest
from mcp import Client

from tests.live.helpers import call

pytestmark = pytest.mark.anyio


@pytest.fixture
def folder() -> Iterator[Path]:
    """A folder in the home folder: the temporary one is already left out of the backups by macOS."""
    made = Path(tempfile.mkdtemp(prefix=".mcp-server-macos-test-", dir=Path.home()))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


async def test_backup_status(client: Client) -> None:
    status = await call(client, "get_backup_status")

    assert isinstance(status["destinations"], list)
    assert isinstance(status["backing_up"], bool)
    assert isinstance(status["last_backup_readable"], bool)
    if status["progress_percent"] is not None:
        assert 0 <= status["progress_percent"] <= 100


async def test_folder_is_left_out_of_the_backups_and_put_back(client: Client, folder: Path) -> None:
    assert await call(client, "check_backup_exclusion", {"path": str(folder)}) == {"excluded": False}

    await call(client, "set_backup_exclusion", {"path": str(folder), "excluded": True})
    assert await call(client, "check_backup_exclusion", {"path": str(folder)}) == {"excluded": True}

    await call(client, "set_backup_exclusion", {"path": str(folder), "excluded": False})
    assert await call(client, "check_backup_exclusion", {"path": str(folder)}) == {"excluded": False}


async def test_settings_are_exported_and_applied_as_they_are(client: Client) -> None:
    names = await call(client, "list_setting_names")
    assert "dock.autohide" in names

    exported = await call(client, "export_settings")
    assert set(exported["settings"]) <= {name.partition(".")[0] for name in names}
    assert all(isinstance(reason, str) for reason in exported["left_out"])

    # Applying nothing, or what's already there, changes nothing.
    assert await call(client, "apply_settings", {"settings": {}}) == {"changed": []}
    dock = {"dock": exported["settings"]["dock"]} if "dock" in exported["settings"] else {}
    assert await call(client, "apply_settings", {"settings": dock}) == {"changed": []}


async def test_printers_and_jobs(client: Client) -> None:
    printers = await call(client, "list_printers")

    names = [printer["name"] for printer in printers["printers"]]
    assert printers["default"] is None or printers["default"] in names
    for job in await call(client, "list_print_jobs", {"finished": True}):
        assert job["printer"]


async def test_scheduled_scripts(client: Client) -> None:
    for job in await call(client, "list_scheduled_jobs"):
        assert job["name"] and job["script"]
    assert await call(client, "get_scheduled_job", {"name": "no-job-is-named-like-this"}) == {"job": None}


async def test_now_playing_never_opens_a_player(client: Client) -> None:
    track = (await call(client, "get_now_playing"))["track"]

    assert track is None or track["app"] in ("Music", "Spotify")
