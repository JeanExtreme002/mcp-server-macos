"""mcp_server_macos._elsewhere, for real: functions called in a process of Python of their own."""

import os
from typing import Any

import macos
import pytest

from mcp_server_macos import _elsewhere

HERE = "tests.unit.test_elsewhere"


def refuse(kind: str) -> Any:
    """Raise the error ``kind`` names, in the process _elsewhere starts."""
    raise {
        "denied": macos.PermissionDeniedError("Camera permission is missing"),
        "value": ValueError("seconds must be positive"),
        "file": FileNotFoundError("no such file: clip.mov"),
        "timeout": macos.WaitTimeoutError("the camera didn't answer"),
        "macos": macos.MacOSError("the recording failed"),
        "bug": KeyError("width"),
    }[kind]


def whose_main_thread() -> Any:
    import threading

    return [os.getpid(), threading.current_thread() is threading.main_thread()]


def test_what_the_function_returns_comes_back() -> None:
    assert _elsewhere.call("os.path:join", ["a", "b"], lasts=5) == os.path.join("a", "b")
    pid, on_main_thread = _elsewhere.call(HERE + ":whose_main_thread", [], lasts=5)
    # In a process of its own, on its main thread.
    assert pid != os.getpid() and on_main_thread is True


@pytest.mark.parametrize(
    "kind, raised, said",
    [
        # A missing permission stays one, so the tool's permission is asked for and told of.
        ("denied", macos.PermissionDeniedError, "Camera permission is missing"),
        ("value", ValueError, "seconds must be positive"),
        ("file", OSError, "FileNotFoundError: no such file: clip.mov"),
        ("timeout", OSError, "WaitTimeoutError: the camera didn't answer"),
        ("macos", macos.MacOSError, "the recording failed"),
    ],
)
def test_what_the_function_raises_is_raised_here(kind: str, raised: type, said: str) -> None:
    with pytest.raises(raised) as error:
        _elsewhere.call(HERE + ":refuse", [kind], lasts=5)

    assert str(error.value) == said


def test_a_bug_in_the_function_isnt_told_to_the_client() -> None:
    # Not an error pymacos raises on purpose: a RuntimeError, which translate_errors leaves to the server,
    # which tells the client only that the tool failed.
    with pytest.raises(RuntimeError, match="KeyError"):
        _elsewhere.call(HERE + ":refuse", ["bug"], lasts=5)
