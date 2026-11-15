"""
Calling a function of the server's in a process of Python of its own, on that process's main thread.

A few features of macOS only work on the main thread, for as long as they last: the events of the system
are delivered there, the camera records there. The main thread is the server's, which would answer
nothing else meanwhile, for minutes. A process of its own has a main thread free for it: the function
runs there, and what it returns, or the error it raised, comes back as JSON.
"""

import json
import subprocess
import sys
import traceback
from typing import Any, List

import macos

#: The time a process of Python takes to start, and to get ready, past what the function itself takes.
STARTING = 30.0

_SCRIPT = "import sys; from mcp_server_macos._elsewhere import _serve; _serve(sys.argv[1], sys.argv[2])"


def call(function: str, args: List[Any], *, lasts: float) -> Any:
    """
    Call ``function`` (``"module:name"``, a function of the server's that takes and returns what JSON
    can carry) with ``args`` in a process of its own, and return what it returns.

    ``lasts`` is how long the call may take, in seconds, before the process is let go of. An error it
    raised is raised again here as what it was, as far as the server tells errors apart: a missing
    permission, an invalid argument, a file, or macOS failing. Any other error, a bug, is a
    :class:`RuntimeError`, which the client isn't told the text of.
    """
    try:
        done = subprocess.run(
            [sys.executable, "-c", _SCRIPT, function, json.dumps(args)],
            capture_output=True,
            text=True,
            timeout=lasts + STARTING,
        )
    except subprocess.TimeoutExpired:
        raise macos.MacOSError("{} didn't end in time".format(function.rpartition(":")[2])) from None
    lines = done.stdout.strip().splitlines()
    if done.returncode != 0 or not lines:
        # The process ended without a word: what it printed may be anything, so it isn't told to the
        # client, as an unexpected error of a tool isn't (see translate_errors).
        raise RuntimeError("{} ended without an answer: {}".format(function, done.stderr.strip()[-2000:]))
    answer = json.loads(lines[-1])  # the last line: a warning may have been printed before it
    if "error" not in answer:
        return answer["result"]
    error = answer["error"]
    kind, message = error["kind"], error["message"]
    if not error["expected"]:
        # Not an error pymacos raises on purpose: its text may hold anything, and stays on this machine.
        raise RuntimeError("{} raised {}: {}".format(function, kind, message))
    if error["denied"]:
        raise macos.PermissionDeniedError(message)
    for family in ("ValueError", "OSError", "LookupError"):
        if error[family]:
            raise {"ValueError": ValueError, "OSError": OSError, "LookupError": LookupError}[family](
                "{}: {}".format(kind, message) if kind != family else message
            )
    raise macos.MacOSError("{}: {}".format(kind, message) if kind != "MacOSError" else message)


def _serve(function: str, args: str) -> None:
    """In the process :func:`call` starts: call the function, and print what it returned or raised."""
    import importlib

    module, _, name = function.partition(":")
    try:
        result = getattr(importlib.import_module(module), name)(*json.loads(args))
    except Exception as error:  # every error is told to the server, which tells them apart
        looked_up = isinstance(error, LookupError) and not isinstance(error, (KeyError, IndexError))
        print(
            json.dumps(
                {
                    "error": {
                        "kind": type(error).__name__,
                        "message": str(error),
                        "denied": isinstance(error, macos.PermissionDeniedError),
                        "ValueError": isinstance(error, ValueError),
                        "OSError": isinstance(error, OSError),
                        "LookupError": looked_up,
                        # The errors translate_errors tells the client of: the others are bugs.
                        "expected": isinstance(error, (macos.MacOSError, ValueError, OSError)) or looked_up,
                    }
                }
            )
        )
        traceback.print_exc()
        return
    print(json.dumps({"result": result}))
