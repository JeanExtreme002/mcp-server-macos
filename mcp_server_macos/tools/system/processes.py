"""The running processes: which they are, what they use, the ports and files they hold, and ending one."""

from datetime import datetime
from typing import Annotated, List, Literal, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from ..._registry import DESTRUCTIVE, READ_ONLY, add_tool

Pid = Annotated[int, Field(description="The process's ID (pid).", gt=0)]
Limit = Annotated[int, Field(description="How many to return, at most.", ge=1, le=1000)]


class Process(BaseModel):
    """A running process, as it was when read."""

    pid: int = Field(description="Its ID.")
    name: str = Field(description="Its name.")
    path: Optional[str] = Field(description="Its executable. Null for the few the system hides.")
    user: Optional[str] = Field(description="The user it runs as.")
    parent_pid: int = Field(description="The ID of the process that started it.")
    started: Optional[datetime] = Field(description="When it started. Null for other users' processes.")
    memory_bytes: Optional[int] = Field(description="The memory it uses, in bytes. Null for other users' processes.")
    cpu_time_seconds: Optional[float] = Field(
        description="The processor time it used since it started, in seconds. Null for other users' processes."
    )
    cpu_percent: Optional[float] = Field(
        description="The share of a processor core it used lately, like Activity Monitor's % CPU: over 100 on "
        "several cores. Null unless the CPU was asked for, and for other users' processes."
    )


class ProcessFound(BaseModel):
    """A process that was looked for."""

    process: Optional[Process] = Field(description="The process. Null when there's none.")


class Port(BaseModel):
    """A port a process listens on: a TCP server, or a bound UDP socket."""

    port: int = Field(description="The port's number.")
    protocol: str = Field(description="'tcp' or 'udp'.")
    address: str = Field(
        description="The address it listens on: '0.0.0.0' or '::' for every one, '127.0.0.1' for this Mac only..."
    )
    pid: int = Field(description="The ID of the process listening.")
    process: str = Field(description="The process's name.")


class Connection(BaseModel):
    """A network connection a process has open: its end, and the other one."""

    protocol: str = Field(description="'tcp' or 'udp'.")
    local_address: str = Field(description="The address on this Mac.")
    local_port: int = Field(description="The port on this Mac.")
    remote_address: str = Field(description="The address it's talking to.")
    remote_port: int = Field(description="The port it's talking to.")
    state: Optional[str] = Field(
        description="TCP's state: 'established', 'syn_sent', 'close_wait', 'time_wait'... Null for UDP."
    )
    pid: int = Field(description="The ID of the process.")
    process: str = Field(description="The process's name.")


class NetworkUsage(BaseModel):
    """How much a process sent and received over the network."""

    pid: int = Field(description="The process's ID.")
    process: str = Field(description="The process's name.")
    received_bytes: int = Field(description="What it received, in bytes: since it started, or in the interval asked for.")
    sent_bytes: int = Field(description="What it sent, in bytes: since it started, or in the interval asked for.")


class EnergyUsage(BaseModel):
    """How much power a process drew, and how much it read and wrote on disk, over an interval."""

    pid: int = Field(description="The process's ID.")
    process: str = Field(description="The process's name.")
    watts: float = Field(description="The average power it drew, in watts: what drains the battery. 0 on Intel Macs.")
    disk_read_bytes: int = Field(description="What it read from disk in the interval, in bytes.")
    disk_written_bytes: int = Field(description="What it wrote to disk in the interval, in bytes.")


def _process(process: "macos.system.Process") -> Process:
    return Process(
        pid=process.pid,
        name=process.name,
        path=None if process.path is None else str(process.path),
        user=process.user,
        parent_pid=process.parent_pid,
        started=process.started,
        memory_bytes=process.memory,
        cpu_time_seconds=None if process.cpu_time is None else process.cpu_time.total_seconds(),
        cpu_percent=process.cpu_percent,
    )


def list_processes(
    name: Annotated[
        Optional[str],
        Field(description="Keep only the processes whose name has this text, in any case. All of them by default."),
    ] = None,
    sort_by: Annotated[
        Literal["pid", "memory", "cpu"],
        Field(
            description="'memory' for the ones using the most memory first, 'cpu' for the busiest first (measured "
            "over half a second), 'pid' for the order of their IDs."
        ),
    ] = "pid",
    limit: Limit = 50,
) -> List[Process]:
    """
    List the running processes, like Activity Monitor. A Mac runs hundreds: filter by name, or sort by
    memory or CPU and keep the first few. Other users' processes, the system's included, come without
    their memory, processor time and start.
    """
    found = macos.system.processes(cpu=sort_by == "cpu")
    if name is not None:
        found = [process for process in found if name.casefold() in process.name.casefold()]
    if sort_by == "memory":
        found = sorted(found, key=lambda process: process.memory or 0, reverse=True)
    elif sort_by == "cpu":
        found = sorted(found, key=lambda process: process.cpu_percent or 0.0, reverse=True)
    return [_process(process) for process in found[:limit]]


def get_process(
    pid: Pid,
    cpu: Annotated[
        bool, Field(description="True to also measure its share of the processor, which takes half a second.")
    ] = False,
) -> ProcessFound:
    """Get a running process by its ID. The process is null when there's none with that ID: it may have quit."""
    found = macos.system.process(pid, cpu=cpu)
    return ProcessFound(process=None if found is None else _process(found))


def kill_process(
    pid: Pid,
    force: Annotated[
        bool,
        Field(
            description="False asks the process to quit, which lets it save and clean up, and it may take a moment "
            "or refuse. True ends it at once: what it didn't save is lost."
        ),
    ] = False,
) -> str:
    """
    Ask a process to quit, or end it at once. It acts on whatever process has that ID now: check it with
    get_process first. Fails for a process that's already gone, and for another user's.
    """
    macos.system.kill(pid, force=force)
    return "Process {} was {}.".format(pid, "ended" if force else "asked to quit")


def list_open_files(pid: Pid) -> List[str]:
    """
    List the files and folders a process has open, with its working folder and executable. Empty for
    another user's process, which macOS keeps from this user.
    """
    return [str(path) for path in macos.system.open_files(pid)]


def find_processes_using(
    path: Annotated[
        str,
        Field(description="The path of a file, a folder or a disk, such as '/Volumes/Backup'.", min_length=1),
    ],
    limit: Limit = 50,
) -> List[Process]:
    """
    Find the processes using a path: with it open, or a file in it, working in it, or run from it. The
    answer to "why won't this disk eject?". Only this user's processes are seen.
    """
    return [_process(process) for process in macos.system.who_uses(path)[:limit]]


def list_ports() -> List[Port]:
    """
    List the ports processes listen on: TCP servers and bound UDP sockets, by port. Only this user's
    processes are seen.
    """
    return [
        Port(port=port.port, protocol=port.protocol, address=port.address, pid=port.pid, process=port.process)
        for port in macos.system.ports()
    ]


def find_port_owner(
    port: Annotated[int, Field(description="The port's number.", ge=1, le=65535)],
    protocol: Annotated[Literal["tcp", "udp"], Field(description="'tcp' or 'udp'.")] = "tcp",
) -> ProcessFound:
    """
    Find the process listening on a port: what's using port 8000? The process is null when nothing
    listens there. Only this user's processes are seen.
    """
    found = macos.system.port_owner(port, protocol)
    return ProcessFound(process=None if found is None else _process(found))


def list_connections(limit: Limit = 200) -> List[Connection]:
    """
    List the network connections processes have open: which address and port each is talking to. Only
    this user's processes are seen.
    """
    return [
        Connection(
            protocol=connection.protocol,
            local_address=connection.local_address,
            local_port=connection.local_port,
            remote_address=connection.remote_address,
            remote_port=connection.remote_port,
            state=connection.state,
            pid=connection.pid,
            process=connection.process,
        )
        for connection in macos.system.connections()[:limit]
    ]


def get_network_usage(
    interval_seconds: Annotated[
        Optional[float],
        Field(
            description="Measure what each process moves in that many seconds, from 1 to 60. By default, the totals "
            "since each process started.",
            ge=1,
            le=60,
        ),
    ] = None,
    limit: Limit = 20,
) -> List[NetworkUsage]:
    """
    Get how much each process received and sent over the network, the busiest first: who's using the
    internet? It sees every user's processes, the system's included.
    """
    usage = macos.system.network_usage(interval_seconds)
    return [
        NetworkUsage(pid=use.pid, process=use.process, received_bytes=use.received, sent_bytes=use.sent)
        for use in usage[:limit]
    ]


def get_energy_usage(
    interval_seconds: Annotated[
        float, Field(description="How long to measure for, in seconds: up to 60.", gt=0, le=60)
    ] = 1.0,
    limit: Limit = 20,
) -> List[EnergyUsage]:
    """
    Get how much power each process drew over an interval, the hungriest first: what drains the
    battery? It also tells how much each read and wrote on disk. Only this user's processes are seen.
    """
    usage = macos.system.energy_usage(interval_seconds)
    return [
        EnergyUsage(
            pid=use.pid,
            process=use.process,
            watts=use.watts,
            disk_read_bytes=use.disk_read,
            disk_written_bytes=use.disk_written,
        )
        for use in usage[:limit]
    ]


def register(server: MCPServer) -> None:
    add_tool(server, list_processes, title="List the running processes", annotations=READ_ONLY)
    add_tool(server, get_process, title="Get a process", annotations=READ_ONLY)
    add_tool(server, list_open_files, title="List a process's open files", annotations=READ_ONLY)
    add_tool(server, find_processes_using, title="Find the processes using a path", annotations=READ_ONLY)
    add_tool(server, list_ports, title="List the listening ports", annotations=READ_ONLY)
    add_tool(server, find_port_owner, title="Find the process using a port", annotations=READ_ONLY)
    add_tool(server, list_connections, title="List the network connections", annotations=READ_ONLY)
    add_tool(server, get_network_usage, title="Get the network usage by process", annotations=READ_ONLY)
    add_tool(server, get_energy_usage, title="Get the energy usage by process", annotations=READ_ONLY)
    # What a process didn't save is lost when it's ended.
    add_tool(server, kill_process, title="Quit or end a process", annotations=DESTRUCTIVE)
