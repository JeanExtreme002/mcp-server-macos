"""Tools that run Python scripts on a schedule, with launchd, from ``macos.schedule``."""

from typing import Annotated, List, Literal, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._registry import DESTRUCTIVE, OPEN_ENDED, READ_ONLY, REPLACING, add_tool

JobName = Annotated[str, Field(description="The job's name, as list_scheduled_jobs gives it.", min_length=1)]
Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class Job(BaseModel):
    """A scheduled script."""

    name: str = Field(description="Its name.")
    script: str = Field(description="The Python script it runs.")
    args: List[str] = Field(description="The arguments the script is run with.")
    every_seconds: Optional[int] = Field(description="The seconds between runs, for a job run every so often.")
    at: List[str] = Field(description="The times of day it runs, such as '09:00'.")
    weekdays: List[str] = Field(description="The days the times apply to, such as 'mon'. Empty for every day.")
    at_login: bool = Field(description="Whether it runs each time the user logs in.")
    when_changed: List[str] = Field(description="The files or folders whose changes run it.")
    at_mount: bool = Field(description="Whether mounting a disk runs it.")
    paused: bool = Field(description="Whether it's paused: it doesn't run on its schedule.")
    log: str = Field(description="The file the script's output and errors go to.")
    running: bool = Field(description="Whether the script is running right now.")
    last_exit_status: Optional[int] = Field(
        description="How its last run ended: the exit code (0 is success), or minus the signal that stopped it. "
        "Null when it hasn't run yet."
    )


class JobFound(BaseModel):
    """A job that was looked for."""

    job: Optional[Job] = Field(description="The job. Null when there's none of that name.")


class Removed(BaseModel):
    """A job that was removed."""

    existed: bool = Field(description="Whether there was a job of that name.")


def _job(job: "macos.schedule.Job") -> Job:
    return Job(
        name=job.name,
        script=str(job.script),
        args=list(job.args),
        every_seconds=job.every,
        at=list(job.at),
        weekdays=list(job.weekdays),
        at_login=job.at_login,
        when_changed=[str(path) for path in job.when_changed],
        at_mount=job.at_mount,
        paused=job.paused,
        log=str(job.log),
        running=job.running,
        last_exit_status=job.last_exit_status,
    )


def list_scheduled_jobs() -> List[Job]:
    """List the scripts scheduled with schedule_script, by name, with when they run and how their last run ended."""
    return [_job(job) for job in macos.schedule.jobs()]


def get_scheduled_job(name: JobName) -> JobFound:
    """Get a scheduled script by its name. The job is null when there's none of that name."""
    job = macos.schedule.get(name)
    return JobFound(job=None if job is None else _job(job))


def schedule_script(
    name: Annotated[
        str, Field(description="The job's name, such as 'backup'. Scheduling a name again replaces that job.", min_length=1)
    ],
    script: Annotated[str, Field(description="The path of the Python script to run.", min_length=1)],
    every_seconds: Annotated[
        Optional[float],
        Field(description="Run it every so many seconds, while the Mac is awake. Not with at.", gt=0),
    ] = None,
    at: Annotated[
        Optional[List[str]],
        Field(description="Run it at these times of day, as 'HH:MM' ('09:00', '18:30'). Not with every_seconds.", min_length=1),
    ] = None,
    weekdays: Annotated[
        Optional[List[Weekday]],
        Field(description="With at: run it on these days only, such as ['mon', 'fri']. Every day by default.", min_length=1),
    ] = None,
    at_login: Annotated[bool, Field(description="True to run it each time the user logs in, and once right away.")] = False,
    when_changed: Annotated[
        Optional[List[str]],
        Field(description="Run it when one of these files or folders changes (in a folder: a file added, removed or renamed)."),
    ] = None,
    at_mount: Annotated[bool, Field(description="True to run it each time a disk is mounted.")] = False,
    args: Annotated[
        Optional[List[str]],
        Field(description="Arguments for the script. They show in the process list: keep secrets out of them."),
    ] = None,
    python: Annotated[
        Optional[str],
        Field(description="The Python to run it with, such as a virtual environment's. This server's Python by default."),
    ] = None,
) -> Job:
    """
    Run a Python script on a schedule, from now on, like cron: every so often, at times of day, at
    login, when a folder changes or when a disk is mounted. It runs as the user, outside any terminal,
    whatever is at the script's path at each run, until it's removed, and macOS shows a "Background
    Items Added" notification the first time. Schedule what the user asked for.
    """
    return _job(
        macos.schedule.add(
            name,
            script,
            every=every_seconds,
            at=at,
            weekdays=weekdays,
            at_login=at_login,
            when_changed=when_changed,
            at_mount=at_mount,
            args=args or (),
            python=python,
        )
    )


def run_scheduled_job_now(name: JobName) -> str:
    """
    Run a scheduled script right away, besides its schedule. Nothing happens if it's already running,
    and a paused job doesn't run.
    """
    macos.schedule.run_now(name)
    return "{} started.".format(name)


def pause_scheduled_job(name: JobName) -> str:
    """Stop a scheduled script from running on its schedule, without removing it. A run in progress is stopped too."""
    macos.schedule.pause(name)
    return "{} is paused.".format(name)


def resume_scheduled_job(name: JobName) -> str:
    """Put a paused script back on its schedule. One that runs at login also runs now."""
    macos.schedule.resume(name)
    return "{} is back on its schedule.".format(name)


def remove_scheduled_job(name: JobName) -> Removed:
    """Stop and remove a scheduled script, and a run in progress. Its log stays; the script itself isn't touched."""
    return Removed(existed=macos.schedule.remove(name))


def register(server: MCPServer) -> None:
    add_tool(server, list_scheduled_jobs, title="List the scheduled scripts", annotations=READ_ONLY)
    add_tool(server, get_scheduled_job, title="Get a scheduled script", annotations=READ_ONLY)
    # They make a script run, and what it does can't be told beforehand.
    add_tool(server, schedule_script, title="Schedule a script", annotations=OPEN_ENDED)
    add_tool(server, run_scheduled_job_now, title="Run a scheduled script now", annotations=OPEN_ENDED)
    add_tool(server, resume_scheduled_job, title="Resume a scheduled script", annotations=OPEN_ENDED)
    add_tool(server, pause_scheduled_job, title="Pause a scheduled script", annotations=REPLACING)
    add_tool(server, remove_scheduled_job, title="Remove a scheduled script", annotations=DESTRUCTIVE)
