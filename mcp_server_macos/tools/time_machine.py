"""Tools that start and follow Time Machine backups, and choose what they leave out, from ``macos.time_machine``."""

from datetime import datetime
from typing import Annotated, List, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._permissions import FULL_DISK_ACCESS
from .._registry import ADDITIVE, READ_ONLY, REPLACING, add_tool

Path = Annotated[str, Field(description="The path of a file or a folder.", min_length=1)]


class BackupStatus(BaseModel):
    """Time Machine on this Mac."""

    destinations: List[str] = Field(description="The names of the disks it backs up to. Empty when none is set up.")
    backing_up: bool = Field(description="Whether a backup is in progress.")
    progress_percent: Optional[float] = Field(
        description="How far the backup in progress is, from 0 to 100. Null when none is, or while it's getting ready."
    )
    last_backup: Optional[datetime] = Field(
        description="When the latest backup was made. Null when there's none yet, its disk isn't connected, or it "
        "can't be read: see last_backup_readable."
    )
    last_backup_readable: bool = Field(
        description="False when the date of the latest backup can't be read, for want of the Full Disk Access "
        "permission of the app that runs this server."
    )


class Exclusion(BaseModel):
    """Whether Time Machine backs a path up."""

    excluded: bool = Field(
        description="True when Time Machine leaves it out: by set_backup_exclusion, by System Settings' list, or by "
        "macOS itself (caches, the temporary folder). A file in an excluded folder is excluded."
    )


def get_backup_status() -> BackupStatus:
    """Get the disks Time Machine backs up to, whether a backup is in progress and how far, and when the last one was made."""
    try:
        last: Optional[datetime] = macos.time_machine.last_backup()
        readable = True
    except macos.PermissionDeniedError:
        last, readable = None, False
    progress = macos.time_machine.progress()
    return BackupStatus(
        destinations=macos.time_machine.destinations(),
        backing_up=macos.time_machine.is_backing_up(),
        progress_percent=None if progress is None else round(progress * 100, 1),
        last_backup=last,
        last_backup_readable=readable,
    )


def start_backup() -> str:
    """Start a Time Machine backup, like Back Up Now in its menu. It returns at once: follow it with get_backup_status."""
    macos.time_machine.backup_now()
    return "Backup started."


def stop_backup() -> str:
    """Stop the Time Machine backup in progress, like Skip This Backup."""
    macos.time_machine.stop_backup()
    return "Backup stopped."


def check_backup_exclusion(path: Path) -> Exclusion:
    """Check whether Time Machine leaves a file or a folder out of its backups."""
    return Exclusion(excluded=macos.time_machine.is_excluded(path))


def set_backup_exclusion(
    path: Path,
    excluded: Annotated[
        bool,
        Field(description="True to leave it out of the backups from the next one on, false to back it up again."),
    ],
) -> str:
    """
    Leave a file or a folder out of the Time Machine backups, or back it up again: for what can be
    downloaded or rebuilt (node_modules, virtual environments, caches), which makes backups big and
    slow. The choice travels with the file when it's moved. Copies already on the backup disk stay.
    """
    if excluded:
        macos.time_machine.exclude(path)
        return "{} is left out of the backups.".format(path)
    macos.time_machine.include(path)
    return "{} is backed up.".format(path)


def register(server: MCPServer) -> None:
    add_tool(server, get_backup_status, title="Get the Time Machine status", annotations=READ_ONLY)
    add_tool(server, start_backup, title="Start a Time Machine backup", annotations=ADDITIVE)
    add_tool(server, stop_backup, title="Stop the Time Machine backup", annotations=REPLACING)
    # In the folders macOS protects (Mail, Messages, the Trash), they need Full Disk Access.
    add_tool(
        server, check_backup_exclusion, title="Check whether a path is backed up", annotations=READ_ONLY,
        permission=FULL_DISK_ACCESS,
    )
    add_tool(
        server, set_backup_exclusion, title="Leave a path out of the backups", annotations=REPLACING, permission=FULL_DISK_ACCESS
    )
