"""What went on in the Mac: crashes, the system log, and what macOS starts by itself."""

from datetime import datetime
from typing import Annotated, List, Literal, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from ..._registry import READ_ONLY, add_tool


class CrashReport(BaseModel):
    """An app or a process that crashed, as the report macOS wrote tells."""

    app: str = Field(description="What crashed.")
    version: Optional[str] = Field(description="Its version.")
    date: Optional[datetime] = Field(description="When it crashed.")
    reason: Optional[str] = Field(description="What stopped it, such as 'EXC_BAD_ACCESS (SIGSEGV)'.")
    path: str = Field(description="The report's file, to read or share with the app's developers.")


class LogEntry(BaseModel):
    """A message in the system log."""

    date: Optional[datetime] = Field(description="When it was logged.")
    process: str = Field(description="The process that logged it.")
    pid: Optional[int] = Field(description="The process's ID.")
    subsystem: Optional[str] = Field(description="Its subsystem, such as 'com.apple.bluetooth'.")
    category: Optional[str] = Field(description="Its category within the subsystem.")
    level: str = Field(description="'default', 'info', 'debug', 'error' or 'fault'.")
    message: str = Field(description="The message. Some hide private data as '<private>'.")


class StartupItem(BaseModel):
    """Something macOS starts by itself: a launch agent or a daemon."""

    label: str = Field(description="Its name for launchd, such as 'com.google.keystone.agent'.")
    kind: str = Field(
        description="'agent' (runs as a user, in their session) or 'daemon' (runs as the system, before anyone "
        "logs in)."
    )
    for_all_users: bool = Field(description="Whether it's installed for every user of the Mac, not only this one.")
    program: Optional[str] = Field(description="What it runs.")
    arguments: List[str] = Field(description="The arguments it's run with.")
    run_at_load: bool = Field(description="Whether it starts when loaded: at login for an agent, at startup for a daemon.")
    keep_alive: bool = Field(description="Whether it's started again whenever it stops.")
    enabled: bool = Field(description="Whether it's not turned off, by its own file or by launchctl.")
    running: Optional[bool] = Field(description="Whether it's running now. Null when launchd didn't say.")
    path: str = Field(description="Its description file (a .plist).")


def list_crash_reports(
    app: Annotated[
        Optional[str], Field(description="Keep one app's crashes, by its name, in any case. Every app's by default.")
    ] = None,
    since: Annotated[
        Optional[datetime],
        Field(description="Keep the crashes from this moment on, in this Mac's local time unless it carries a time zone."),
    ] = None,
    limit: Annotated[int, Field(description="How many to return, at most.", ge=1, le=500)] = 20,
) -> List[CrashReport]:
    """
    List the crashes macOS recorded, the latest first: which app, when, and why. macOS deletes the
    reports after a while.
    """
    return [
        CrashReport(app=crash.app, version=crash.version, date=crash.date, reason=crash.reason, path=str(crash.path))
        for crash in macos.system.crash_reports(app, since=since)[:limit]
    ]


def read_system_log(
    process: Annotated[Optional[str], Field(description="Keep the messages of this process, such as 'Safari'.")] = None,
    subsystem: Annotated[
        Optional[str], Field(description="Keep the messages of this subsystem, such as 'com.apple.bluetooth'.")
    ] = None,
    contains: Annotated[
        Optional[str], Field(description="Keep the messages holding this text, in any case.")
    ] = None,
    level: Annotated[
        Optional[Literal["debug", "info", "default", "error", "fault"]],
        Field(description="Keep the messages from this level up. 'error' leaves out the routine ones."),
    ] = None,
    last: Annotated[
        str,
        Field(
            description="How far back to read: a number and s, m, h or d, as '30s', '10m', '2h' or '1d'.",
            pattern=r"^\d+[smhd]$",
        ),
    ] = "10m",
    limit: Annotated[int, Field(description="How many messages to return, at most.", ge=1, le=1000)] = 200,
) -> List[LogEntry]:
    """
    Read the system log (the one the Console app shows), oldest first. The log is large, thousands of
    messages a minute: filter it by process, subsystem, text or level. Reading far back without a
    filter takes long, and is stopped after two minutes.
    """
    entries = macos.system.logs(
        process=process, subsystem=subsystem, contains=contains, level=level, last=last, limit=limit
    )
    return [
        LogEntry(
            date=entry.date,
            process=entry.process,
            pid=entry.pid,
            subsystem=entry.subsystem,
            category=entry.category,
            level=entry.level,
            message=entry.message,
        )
        for entry in entries
    ]


def list_startup_items() -> List[StartupItem]:
    """
    List what macOS starts by itself, besides the apps opened at login: launch agents and daemons, of
    the user and of the Mac, leaving out Apple's own.
    """
    return [
        StartupItem(
            label=item.label,
            kind=item.kind,
            for_all_users=item.for_all_users,
            program=item.program,
            arguments=list(item.arguments),
            run_at_load=item.run_at_load,
            keep_alive=item.keep_alive,
            enabled=item.enabled,
            running=item.running,
            path=str(item.path),
        )
        for item in macos.system.startup_items()
    ]


def register(server: MCPServer) -> None:
    add_tool(server, list_crash_reports, title="List the crash reports", annotations=READ_ONLY)
    add_tool(server, read_system_log, title="Read the system log", annotations=READ_ONLY)
    add_tool(server, list_startup_items, title="List what starts by itself", annotations=READ_ONLY)
