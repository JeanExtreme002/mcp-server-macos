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
    permission, an invalid argument, a file, or macOS failing.
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
        errors = done.stderr.strip().splitlines()
        raise macos.MacOSError("{} failed: {}".format(function, errors[-1] if errors else done.returncode))
    answer = json.loads(lines[-1])  # the last line: a warning may have been printed before it
    if "error" not in answer:
        return answer["result"]
    kind, message = answer["error"]["kind"], answer["error"]["message"]
    if answer["error"]["denied"]:
        raise macos.PermissionDeniedError(message)
    for family in ("ValueError", "OSError", "LookupError"):
        if answer["error"][family]:
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
        print(
            json.dumps(
                {
                    "error": {
                        "kind": type(error).__name__,
                        "message": str(error),
                        "denied": isinstance(error, macos.PermissionDeniedError),
                        "ValueError": isinstance(error, ValueError),
                        "OSError": isinstance(error, OSError),
                        "LookupError": isinstance(error, LookupError) and not isinstance(error, (KeyError, IndexError)),
                    }
                }
            )
        )
        traceback.print_exc()
        return
    print(json.dumps({"result": result}))
