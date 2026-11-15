"""Helpers shared by the tests."""

import math
import struct
import zlib
from typing import Any, Callable, Dict, List, Optional, Tuple

from mcp.types import CallToolResult, TextContent


def text(result: CallToolResult) -> str:
    """The text of a tool's result: what a model reads of it."""
    assert all(isinstance(block, TextContent) for block in result.content), result.content
    return "\n".join(block.text for block in result.content if isinstance(block, TextContent))


class Recorder:
    """
    Stands in for functions of pymacos, and keeps the calls made to them, in order.

    ::

        recorder = Recorder()
        monkeypatch.setattr(macos.volume, "set", recorder.function("set"))
        ...
        assert recorder.calls == [("set", (30,), {})]
    """

    def __init__(self) -> None:
        self.calls: List[Tuple[str, Tuple[Any, ...], Dict[str, Any]]] = []

    def function(self, name: str, result: Any = None, error: Optional[BaseException] = None) -> Callable[..., Any]:
        """A function that records its call as ``name``, then returns ``result`` or raises ``error``."""

        def call(*args: Any, **kwargs: Any) -> Any:
            self.calls.append((name, args, kwargs))
            if error is not None:
                raise error
            return result

        return call

    @property
    def names(self) -> List[str]:
        """The names of the functions called, in order."""
        return [name for name, _, _ in self.calls]


def png(width: int = 4, height: int = 4) -> bytes:
    """A real PNG, opaque red, written by hand: the tests need a picture macOS can open, and no library to draw it."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    rows = (b"\x00" + b"\xff\x00\x00" * width) * height  # each row: no filter, then its pixels as RGB
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def wav(seconds: float = 1.0, frequency: float = 440.0, rate: int = 22050) -> bytes:
    """A real WAV, a mono tone, written by hand: the tests need a sound that doesn't depend on a voice."""
    frames = b"".join(
        struct.pack("<h", int(12000 * math.sin(2 * math.pi * frequency * index / rate)))
        for index in range(int(seconds * rate))
    )
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(frames),
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        rate,
        rate * 2,
        2,
        16,
        b"data",
        len(frames),
    )
    return header + frames
