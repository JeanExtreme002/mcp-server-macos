"""Tools for the battery, sleep and keeping the Mac awake, from ``macos.power``."""

import threading
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Annotated, Any, List, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._registry import DESTRUCTIVE, READ_ONLY, REPLACING, add_tool


class Battery(BaseModel):
    """The internal battery."""

    percent: int = Field(description="The charge level, from 0 to 100.")
    charging: bool = Field(description="Whether it's charging right now: false once full, even if plugged in.")
    plugged_in: bool = Field(description="Whether the Mac is running on AC power.")
    time_remaining_seconds: Optional[int] = Field(
        description="Seconds until empty on battery, or until full while charging. Null while macOS is still "
        "estimating, or when plugged in but not charging."
    )
    cycle_count: Optional[int] = Field(description="How many full charge cycles the battery has gone through.")
    health_percent: Optional[int] = Field(
        description="The full charge it holds now, compared with when it was new, in percent."
    )


class Adapter(BaseModel):
    """The power adapter (charger) the Mac is plugged into."""

    watts: Optional[int] = Field(description="What it can give, in watts, such as 96.")
    name: Optional[str] = Field(description="Its name, such as '96W USB-C Power Adapter'.")
    manufacturer: Optional[str] = Field(description="Who made it.")
    voltage_volts: Optional[float] = Field(description="The voltage it's delivering now, in volts.")
    current_amperes: Optional[float] = Field(description="The most current it's delivering now, in amperes.")


class PowerStatus(BaseModel):
    """How the Mac is powered."""

    battery: Optional[Battery] = Field(description="The internal battery. Null on a Mac without one, like a Mac mini.")
    adapter: Optional[Adapter] = Field(
        description="The charger the Mac is plugged into. Null on battery, and on a desktop Mac."
    )
    low_power_mode: bool = Field(description="Whether Low Power Mode is on, making the Mac slower to save energy.")


class SleepBlocker(BaseModel):
    """A process keeping the Mac from going to sleep on its own."""

    pid: int = Field(description="The process's ID.")
    process: str = Field(description="The process's name, such as 'caffeinate' or 'zoom.us'.")
    reason: str = Field(description="What the process says it's doing, such as 'Playing video'.")
    display: bool = Field(description="Whether it keeps the display on too, not only the Mac awake.")
    kind: str = Field(description="The macOS name of the request, such as 'PreventUserIdleSystemSleep'.")
    since: Optional[datetime] = Field(description="When it started.")
    until: Optional[datetime] = Field(
        description="When it gives up by itself. Null when it holds until its process lets go."
    )


def get_power_status() -> PowerStatus:
    """
    Get how the Mac is powered: the battery (its charge, whether it's charging, the time remaining, its
    health), the charger it's plugged into, and whether Low Power Mode is on.
    """
    battery = macos.power.battery()
    adapter = macos.power.adapter()
    return PowerStatus(
        battery=None if battery is None else _battery(battery),
        adapter=None if adapter is None else _adapter(adapter),
        low_power_mode=macos.power.low_power_mode(),
    )


def _battery(battery: "macos.power.Battery") -> Battery:
    remaining = battery.time_remaining
    return Battery(
        percent=battery.percent,
        charging=battery.charging,
        plugged_in=battery.plugged_in,
        time_remaining_seconds=None if remaining is None else int(remaining.total_seconds()),
        cycle_count=battery.cycle_count,
        health_percent=battery.health,
    )


def _adapter(adapter: "macos.power.Adapter") -> Adapter:
    return Adapter(
        watts=adapter.watts,
        name=adapter.name,
        manufacturer=adapter.manufacturer,
        voltage_volts=adapter.voltage,
        current_amperes=adapter.current,
    )


def get_sleep_blockers() -> List[SleepBlocker]:
    """
    List the processes keeping the Mac from going to sleep, oldest first: the answer to "why doesn't my
    Mac sleep?". macOS itself shows up as powerd while the display is on.
    """
    return [
        SleepBlocker(
            pid=blocker.pid,
            process=blocker.process,
            reason=blocker.reason,
            display=blocker.display,
            kind=blocker.kind,
            since=blocker.since,
            until=blocker.until,
        )
        for blocker in macos.power.sleep_blockers()
    ]


def sleep_mac() -> str:
    """
    Put the Mac to sleep right away, like the Apple menu's Sleep. Whatever is running stops until the
    Mac wakes, this server and the connection to it included.
    """
    macos.power.sleep()
    return "The Mac is going to sleep."


def sleep_display() -> str:
    """
    Turn the display off right away. The Mac keeps running. With the default settings this also locks
    the screen.
    """
    macos.power.sleep_display()
    return "The display is turning off."


class _Awake:
    """
    The one request this server holds to keep the Mac awake, and the timer that ends it.

    pymacos keeps the Mac awake for the length of a ``with`` block. A tool call is over long before
    that should end, so the block is entered by one call and left by a timer, or by another call.
    macOS drops the request by itself if the server stops.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._held: Optional[AbstractContextManager[Any]] = None
        self._timer: Optional[threading.Timer] = None

    def hold(self, seconds: float, display: bool) -> None:
        """Keep the Mac awake for ``seconds``, in place of what was held before."""
        with self._lock:
            # The new one first: if macOS refuses it, the one held before stays.
            held = macos.power.keep_awake(display=display, reason="mcp-server-macos keep_awake")
            held.__enter__()
            self._release()
            self._held = held
            self._timer = threading.Timer(seconds, self.release)
            self._timer.daemon = True  # a server that's stopping doesn't wait for it
            self._timer.start()

    def release(self) -> bool:
        """Let the Mac sleep again. Return whether it was being kept awake."""
        with self._lock:
            return self._release()

    def _release(self) -> bool:
        held, timer, self._held, self._timer = self._held, self._timer, None, None
        if timer is not None:
            timer.cancel()
        if held is None:
            return False
        held.__exit__(None, None, None)
        return True


_awake = _Awake()


def keep_awake(
    minutes: Annotated[
        float,
        Field(description="How long to keep the Mac awake, in minutes: up to 1440, a day.", gt=0, le=1440),
    ],
    display: Annotated[
        bool, Field(description="True to keep the display on too. By default it may still turn off.")
    ] = False,
) -> str:
    """
    Keep the Mac from going to sleep on its own for some time, for a download or a long job to finish.
    Calling it again replaces the time left, and allow_sleep ends it early. It lasts while this server
    runs, and closing a laptop's lid still puts it to sleep.
    """
    _awake.hold(minutes * 60, display)
    return "The Mac will stay awake for {:g} minute{}{}.".format(
        minutes, "" if minutes == 1 else "s", ", with the display on" if display else ""
    )


def allow_sleep() -> str:
    """Let the Mac sleep on its own again, ending what keep_awake started."""
    if _awake.release():
        return "The Mac may sleep again."
    return "The Mac wasn't being kept awake by this server."


def register(server: MCPServer) -> None:
    add_tool(server, get_power_status, title="Get the battery and power status", annotations=READ_ONLY)
    add_tool(server, get_sleep_blockers, title="List what keeps the Mac awake", annotations=READ_ONLY)
    add_tool(server, keep_awake, title="Keep the Mac awake", annotations=REPLACING)
    add_tool(server, allow_sleep, title="Let the Mac sleep again", annotations=REPLACING)
    # Sleep stops whatever is running, the connection to the client included.
    add_tool(server, sleep_mac, title="Put the Mac to sleep", annotations=DESTRUCTIVE)
    add_tool(server, sleep_display, title="Turn the display off", annotations=REPLACING)
