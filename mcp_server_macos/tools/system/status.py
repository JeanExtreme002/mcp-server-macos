"""How the Mac is doing right now: processor, memory, heat, and whether someone is at it."""

from typing import Annotated, List, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from ..._registry import LONGEST_WAIT, READ_ONLY, add_tool


class Memory(BaseModel):
    """The memory in use, counted as Activity Monitor's Memory tab does."""

    total_bytes: int = Field(description="The installed memory, in bytes.")
    used_bytes: int = Field(description="What isn't free to give to an app: app, wired and compressed memory.")
    wired_bytes: int = Field(description="Memory the system keeps, which can't be compressed or paged out.")
    compressed_bytes: int = Field(description="Memory that was compressed to make room.")
    cached_bytes: int = Field(description="Recently used files, kept in memory while nothing needs it.")
    free_bytes: int = Field(description="The total less what's used.")
    used_percent: float = Field(description="What's used, as a percentage of the total.")


class SystemStatus(BaseModel):
    """How the Mac is doing right now."""

    cpu_percent: float = Field(
        description="How busy the processor is, from 0 (idle) to 100 (every core busy), like Activity Monitor's "
        "CPU graph."
    )
    memory: Memory = Field(description="How the memory is used.")
    thermal_state: str = Field(
        description="How hot it's running: 'nominal', 'fair', 'serious' (macOS slows the processor to cool it), "
        "'critical' (close to shutting down), or 'unknown'."
    )
    idle_seconds: int = Field(description="Seconds since the last keyboard, mouse or trackpad input.")
    lid_closed: Optional[bool] = Field(
        description="Whether the MacBook's lid is closed, as when it runs with an external display. Null on a Mac "
        "without a lid."
    )
    camera_in_use: bool = Field(description="Whether an app is using a camera right now. It doesn't say which.")
    microphone_in_use: bool = Field(
        description="Whether an app is recording from a microphone right now. It doesn't say which."
    )


class GPUUsage(BaseModel):
    """How busy a graphics processor is."""

    name: str = Field(description="The driver's name for it, such as 'AGXAcceleratorG14X'.")
    percent: int = Field(description="How busy it is, from 0 to 100, as Activity Monitor's GPU History shows.")
    memory_bytes: Optional[int] = Field(description="The memory it uses, in bytes. Null when its driver doesn't say.")


class Idle(BaseModel):
    """Whether the Mac was left alone for long enough."""

    idle: bool = Field(description="True when nobody touched the Mac for that long. False when the time to wait ran out.")


class Active(BaseModel):
    """Whether someone used the Mac."""

    active: bool = Field(description="True when someone used the Mac. False when the time to wait ran out.")


def get_system_status() -> SystemStatus:
    """
    Get how the Mac is doing right now: how busy the processor is (measured over half a second), how
    the memory is used, how hot it's running, how long since someone touched it, whether the lid is
    closed, and whether the camera or the microphone is in use.
    """
    cpu = macos.system.cpu_usage()
    memory = macos.system.memory_usage()
    try:
        lid_closed: Optional[bool] = macos.system.lid_closed()
    except macos.NotSupportedError:
        lid_closed = None  # a Mac without a lid
    return SystemStatus(
        cpu_percent=round(cpu * 100, 1),
        memory=Memory(
            total_bytes=memory.total,
            used_bytes=memory.used,
            wired_bytes=memory.wired,
            compressed_bytes=memory.compressed,
            cached_bytes=memory.cached,
            free_bytes=memory.free,
            used_percent=round(memory.percent * 100, 1),
        ),
        thermal_state=macos.system.thermal_state(),
        idle_seconds=int(macos.system.idle_time().total_seconds()),
        lid_closed=lid_closed,
        camera_in_use=macos.system.camera_in_use(),
        microphone_in_use=macos.system.microphone_in_use(),
    )


def get_gpu_usage() -> List[GPUUsage]:
    """Get how busy each graphics processor is, and the memory it uses: handy to watch a local AI model or a game."""
    return [GPUUsage(name=gpu.name, percent=gpu.percent, memory_bytes=gpu.memory) for gpu in macos.system.gpu_usage()]


def wait_for_idle(
    idle_seconds: Annotated[
        float,
        Field(description="How long the Mac must be left alone, in seconds.", gt=0, le=LONGEST_WAIT),
    ],
    timeout_seconds: Annotated[
        float,
        Field(description="How long to wait for that, in seconds, before giving up.", gt=0, le=LONGEST_WAIT),
    ] = 60.0,
) -> Idle:
    """
    Wait until nobody has touched the keyboard, mouse or trackpad for some time: for work that should
    wait for the user to step away.
    """
    return Idle(idle=macos.system.wait_for_idle(idle_seconds, timeout=timeout_seconds))


def wait_for_user_activity(
    timeout_seconds: Annotated[
        float,
        Field(description="How long to wait, in seconds, before giving up.", gt=0, le=LONGEST_WAIT),
    ] = 60.0,
) -> Active:
    """Wait until someone uses the keyboard, mouse or trackpad: the user is back at the Mac."""
    return Active(active=macos.system.wait_for_activity(timeout=timeout_seconds))


def register(server: MCPServer) -> None:
    add_tool(server, get_system_status, title="Get the Mac's current status", annotations=READ_ONLY)
    add_tool(server, get_gpu_usage, title="Get the GPU usage", annotations=READ_ONLY)
    add_tool(server, wait_for_idle, title="Wait for the Mac to be left alone", annotations=READ_ONLY)
    add_tool(server, wait_for_user_activity, title="Wait for someone to use the Mac", annotations=READ_ONLY)
