"""Values of Python, as JSON can carry them: what pymacos reads from macOS isn't always text and numbers."""

import base64
from datetime import date, datetime, time, timedelta
from pathlib import PurePath
from typing import Any


def plain(value: Any) -> Any:
    """
    ``value`` with what JSON lacks turned into what it has, at any depth.

    A date and a time become ISO 8601 text, a duration its seconds, a path its text, bytes their Base64
    text, and tuples and sets lists. A dictionary's keys become text.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, PurePath):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(value)).decode("ascii")
    if isinstance(value, dict):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [plain(item) for item in value]
    return str(value)  # nothing pymacos returns today: better its text than a tool that fails
