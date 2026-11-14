"""The tools of mcp_server_macos.tools.power, with macos.power faked."""

import threading
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import macos
import pytest
from mcp import Client

from mcp_server_macos.tools import power
from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


@pytest.fixture
def mac(monkeypatch: pytest.MonkeyPatch) -> None:
    """A desktop Mac: no battery, no charger to report, not in Low Power Mode."""
    monkeypatch.setattr(macos.power, "battery", lambda: None)
    monkeypatch.setattr(macos.power, "adapter", lambda: None)
    monkeypatch.setattr(macos.power, "low_power_mode", lambda: False)


@pytest.mark.usefixtures("mac")
async def test_get_power_status_of_a_desktop(client: Client) -> None:
    result = await client.call_tool("get_power_status", {})

    assert not result.is_error
    assert result.structured_content == {"battery": None, "adapter": None, "low_power_mode": False}


@pytest.mark.usefixtures("mac")
async def test_get_power_status_of_a_laptop_charging(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    battery = macos.power.Battery(
        percent=87,
        charging=True,
        plugged_in=True,
        time_remaining=timedelta(hours=1, minutes=2, seconds=3.9),
        cycle_count=600,
        health=79,
    )
    adapter = macos.power.Adapter(
        watts=96, name="96W USB-C Power Adapter", manufacturer="Apple Inc.", voltage=20.0, current=4.7
    )
    monkeypatch.setattr(macos.power, "battery", lambda: battery)
    monkeypatch.setattr(macos.power, "adapter", lambda: adapter)
    monkeypatch.setattr(macos.power, "low_power_mode", lambda: True)

    result = await client.call_tool("get_power_status", {})

    assert result.structured_content == {
        "battery": {
            "percent": 87,
            "charging": True,
            "plugged_in": True,
            "time_remaining_seconds": 3723,
            "cycle_count": 600,
            "health_percent": 79,
        },
        "adapter": {
            "watts": 96,
            "name": "96W USB-C Power Adapter",
            "manufacturer": "Apple Inc.",
            "voltage_volts": 20.0,
            "current_amperes": 4.7,
        },
        "low_power_mode": True,
    }


@pytest.mark.usefixtures("mac")
async def test_get_power_status_with_what_macos_does_not_know(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    # On battery, macOS still estimating the time left, and an old Mac that doesn't report its health.
    battery = macos.power.Battery(percent=3, charging=False, plugged_in=False, time_remaining=None)
    monkeypatch.setattr(macos.power, "battery", lambda: battery)

    result = await client.call_tool("get_power_status", {})

    assert result.structured_content == {
        "battery": {
            "percent": 3,
            "charging": False,
            "plugged_in": False,
            "time_remaining_seconds": None,
            "cycle_count": None,
            "health_percent": None,
        },
        "adapter": None,
        "low_power_mode": False,
    }


async def test_get_sleep_blockers(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    blockers = [
        macos.power.SleepBlocker(
            pid=352,
            process="powerd",
            reason="Prevent sleep while display is on",
            display=False,
            kind="PreventUserIdleSystemSleep",
            since=datetime(2026, 11, 14, 1, 26, 6),
            until=None,
        ),
        macos.power.SleepBlocker(
            pid=4242,
            process="caffeinate",
            reason="caffeinate command-line tool",
            display=True,
            kind="PreventUserIdleDisplaySleep",
            since=None,
            until=datetime(2026, 11, 14, 3, 0, 0),
        ),
    ]
    monkeypatch.setattr(macos.power, "sleep_blockers", lambda: blockers)

    result = await client.call_tool("get_sleep_blockers", {})

    assert not result.is_error
    assert result.structured_content == {
        "result": [
            {
                "pid": 352,
                "process": "powerd",
                "reason": "Prevent sleep while display is on",
                "display": False,
                "kind": "PreventUserIdleSystemSleep",
                "since": "2026-11-14T01:26:06",
                "until": None,
            },
            {
                "pid": 4242,
                "process": "caffeinate",
                "reason": "caffeinate command-line tool",
                "display": True,
                "kind": "PreventUserIdleDisplaySleep",
                "since": None,
                "until": "2026-11-14T03:00:00",
            },
        ]
    }


async def test_get_sleep_blockers_when_nothing_blocks(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(macos.power, "sleep_blockers", lambda: [])

    result = await client.call_tool("get_sleep_blockers", {})

    assert not result.is_error
    assert result.structured_content == {"result": []}


@pytest.mark.parametrize(
    "tool, function, said",
    [("sleep_mac", "sleep", "The Mac is going to sleep."), ("sleep_display", "sleep_display", "The display is turning off.")],
)
async def test_sleep(client: Client, monkeypatch: pytest.MonkeyPatch, tool: str, function: str, said: str) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.power, "sleep", recorder.function("sleep"))
    monkeypatch.setattr(macos.power, "sleep_display", recorder.function("sleep_display"))

    result = await client.call_tool(tool, {})

    assert not result.is_error
    assert text(result) == said
    assert recorder.calls == [(function, (), {})]


# Keeping the Mac awake: pymacos does it for the length of a with block, which the server enters in one
# call and leaves in another, or when a timer fires.


class Held:
    """What macos.power.keep_awake returns: here it only counts its entries and exits."""

    def __init__(self, log: List[str], name: str) -> None:
        self.log = log
        self.name = name

    def __enter__(self) -> None:
        self.log.append("{} entered".format(self.name))

    def __exit__(self, *error: Any) -> None:
        self.log.append("{} left".format(self.name))


class Timer:
    """threading.Timer, never started for real: the test fires it."""

    made: List["Timer"] = []

    def __init__(self, seconds: float, function: Callable[[], Any]) -> None:
        self.seconds = seconds
        self.function = function
        self.daemon = False
        self.started = False
        self.cancelled = False
        Timer.made.append(self)

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancelled = True


class Awake:
    """What the keep-awake tests look at."""

    def __init__(self) -> None:
        self.log: List[str] = []
        self.asked: List[Dict[str, Any]] = []
        self.refuse: Optional[BaseException] = None

    def keep_awake(self, **options: Any) -> Held:
        if self.refuse is not None:
            raise self.refuse
        self.asked.append(options)
        return Held(self.log, "hold {}".format(len(self.asked)))

    @property
    def timers(self) -> List[Timer]:
        return Timer.made


@pytest.fixture
def awake(monkeypatch: pytest.MonkeyPatch) -> Awake:
    state = Awake()
    monkeypatch.setattr(Timer, "made", [])
    monkeypatch.setattr(macos.power, "keep_awake", state.keep_awake)
    monkeypatch.setattr(threading, "Timer", Timer)
    monkeypatch.setattr(power, "_awake", power._Awake())  # nothing held from another test
    return state


async def test_keep_awake(client: Client, awake: Awake) -> None:
    result = await client.call_tool("keep_awake", {"minutes": 90})

    assert not result.is_error
    assert text(result) == "The Mac will stay awake for 90 minutes."
    assert awake.asked == [{"display": False, "reason": "mcp-server-macos keep_awake"}]
    assert awake.log == ["hold 1 entered"]

    (timer,) = awake.timers
    assert (timer.seconds, timer.started, timer.daemon, timer.cancelled) == (5400, True, True, False)


async def test_keep_awake_with_the_display_on(client: Client, awake: Awake) -> None:
    result = await client.call_tool("keep_awake", {"minutes": 1, "display": True})

    assert text(result) == "The Mac will stay awake for 1 minute, with the display on."
    assert awake.asked == [{"display": True, "reason": "mcp-server-macos keep_awake"}]
    assert awake.timers[0].seconds == 60


async def test_keep_awake_ends_when_its_time_is_up(client: Client, awake: Awake) -> None:
    await client.call_tool("keep_awake", {"minutes": 0.5})
    assert awake.timers[0].seconds == 30

    awake.timers[0].function()  # the timer fires

    assert awake.log == ["hold 1 entered", "hold 1 left"]
    result = await client.call_tool("allow_sleep", {})
    assert text(result) == "The Mac wasn't being kept awake by this server."
    assert awake.log == ["hold 1 entered", "hold 1 left"]


async def test_keep_awake_again_replaces_the_time_left(client: Client, awake: Awake) -> None:
    await client.call_tool("keep_awake", {"minutes": 10})
    await client.call_tool("keep_awake", {"minutes": 20, "display": True})

    # The new one is held before the old one is let go: the Mac is never free to sleep in between.
    assert awake.log == ["hold 1 entered", "hold 2 entered", "hold 1 left"]
    first, second = awake.timers
    assert (first.seconds, first.cancelled) == (600, True)
    assert (second.seconds, second.started, second.cancelled) == (1200, True, False)

    # The first timer is cancelled, so it can't end the second hold when its own time is up.
    await client.call_tool("allow_sleep", {})
    assert awake.log == ["hold 1 entered", "hold 2 entered", "hold 1 left", "hold 2 left"]
    assert second.cancelled


async def test_allow_sleep(client: Client, awake: Awake) -> None:
    await client.call_tool("keep_awake", {"minutes": 10})

    result = await client.call_tool("allow_sleep", {})

    assert not result.is_error
    assert text(result) == "The Mac may sleep again."
    assert awake.log == ["hold 1 entered", "hold 1 left"]
    assert awake.timers[0].cancelled


async def test_allow_sleep_when_nothing_is_held(client: Client, awake: Awake) -> None:
    result = await client.call_tool("allow_sleep", {})

    assert not result.is_error
    assert text(result) == "The Mac wasn't being kept awake by this server."
    assert awake.log == []


async def test_keep_awake_refused_by_macos_keeps_what_was_held(client: Client, awake: Awake) -> None:
    await client.call_tool("keep_awake", {"minutes": 10})
    awake.refuse = macos.MacOSError("could not create the power assertion")

    result = await client.call_tool("keep_awake", {"minutes": 20})

    assert result.is_error
    assert "MacOSError: could not create the power assertion" in text(result)
    assert awake.log == ["hold 1 entered"]
    assert not awake.timers[0].cancelled


@pytest.mark.parametrize("arguments", [{}, {"minutes": 0}, {"minutes": -5}, {"minutes": 1441}, {"minutes": "all night"}])
async def test_keep_awake_needs_a_time_of_a_day_at_most(client: Client, awake: Awake, arguments: Dict[str, Any]) -> None:
    result = await client.call_tool("keep_awake", arguments)

    assert result.is_error
    assert awake.log == []
    assert awake.timers == []
