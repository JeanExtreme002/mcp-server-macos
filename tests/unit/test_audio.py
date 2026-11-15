"""The tools of mcp_server_macos.tools.audio, with macos.audio faked: no device is switched, nothing is recorded."""

from pathlib import Path
from typing import Any, Dict, Tuple

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio

OUT = Path("/Users/me/out.m4a")
SPEAKERS = macos.audio.Device(
    id=1, name="MacBook Pro Speakers", uid="BuiltInSpeakerDevice", transport="builtin", is_output=True, is_input=False
)
MIC = macos.audio.Device(
    id=2,
    name="MacBook Pro Microphone",
    uid="BuiltInMicrophoneDevice",
    transport="builtin",
    is_output=False,
    is_input=True,
)
HEADSET = macos.audio.Device(
    id=3, name="AirPods Pro", uid="E4-61:output", transport="bluetooth", is_output=True, is_input=True
)


def listed(device: Any) -> Dict[str, Any]:
    return {
        "name": device.name,
        "uid": device.uid,
        "transport": device.transport,
        "is_output": device.is_output,
        "is_input": device.is_input,
    }


@pytest.fixture
def audio(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    recorder = Recorder()
    monkeypatch.setattr(macos.audio, "devices", lambda: [SPEAKERS, MIC, HEADSET])
    monkeypatch.setattr(macos.audio, "default_output", lambda: HEADSET)
    monkeypatch.setattr(macos.audio, "default_input", lambda: MIC)
    monkeypatch.setattr(macos.audio, "input_volume", lambda device=None: 0.754)
    monkeypatch.setattr(macos.audio, "input_muted", lambda device=None: False)
    monkeypatch.setattr(macos.audio, "has_permission", lambda: True)
    monkeypatch.setattr(macos.audio, "set_output", recorder.function("set_output", HEADSET))
    monkeypatch.setattr(macos.audio, "set_input", recorder.function("set_input", MIC))
    for name in ("mute_input", "set_input_volume"):
        monkeypatch.setattr(macos.audio, name, recorder.function(name))
    monkeypatch.setattr(macos.audio, "record", recorder.function("record", OUT))
    monkeypatch.setattr(macos.audio, "record_until_silence", recorder.function("record_until_silence", OUT))
    monkeypatch.setattr(macos.audio, "input_level", recorder.function("input_level", 0.12))
    return recorder


async def test_get_audio_status(client: Client, audio: Recorder) -> None:
    result = await client.call_tool("get_audio_status", {})

    assert not result.is_error
    # A device that does both is among the outputs and the inputs.
    assert result.structured_content == {
        "outputs": [listed(SPEAKERS), listed(HEADSET)],
        "inputs": [listed(MIC), listed(HEADSET)],
        "default_output": "E4-61:output",
        "default_input": "BuiltInMicrophoneDevice",
        "input_volume": 75,
        "input_muted": False,
        "microphone_permission": True,
    }


async def test_get_audio_status_with_a_microphone_without_volume_or_mute(
    client: Client, audio: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(device: Any = None) -> Any:
        raise macos.NotSupportedError("this microphone has no mute switch")

    monkeypatch.setattr(macos.audio, "input_volume", refuse)
    monkeypatch.setattr(macos.audio, "input_muted", refuse)

    result = await client.call_tool("get_audio_status", {})

    assert not result.is_error
    assert result.structured_content is not None
    assert (result.structured_content["input_volume"], result.structured_content["input_muted"]) == (None, None)


@pytest.mark.parametrize(
    "tool, function, device", [("set_audio_output", "set_output", HEADSET), ("set_audio_input", "set_input", MIC)]
)
async def test_devices_are_switched(client: Client, audio: Recorder, tool: str, function: str, device: Any) -> None:
    result = await client.call_tool(tool, {"device": "AirPods"})

    assert result.structured_content == listed(device)
    assert audio.calls == [(function, ("AirPods",), {})]


@pytest.mark.parametrize(
    "arguments, calls, said",
    [
        ({"muted": True}, [("mute_input", (True,), {"device": None})], "Microphone: muted."),
        (
            {"volume": 30, "device": "USB Mic"},
            [("set_input_volume", (0.3,), {"device": "USB Mic"})],
            "Microphone: volume 30.",
        ),
        (
            {"volume": 0, "muted": False},
            [("mute_input", (False,), {"device": None}), ("set_input_volume", (0.0,), {"device": None})],
            "Microphone: unmuted, volume 0.",
        ),
    ],
)
async def test_set_microphone(
    client: Client, audio: Recorder, arguments: Dict[str, Any], calls: Any, said: str
) -> None:
    result = await client.call_tool("set_microphone", arguments)

    assert text(result) == said
    assert audio.calls == calls


async def test_record_microphone(client: Client, audio: Recorder) -> None:
    result = await client.call_tool("record_microphone", {"path": "memo.m4a", "seconds": 30})

    assert result.structured_content == {"path": str(OUT)}
    assert audio.calls == [("record", ("memo.m4a", 30.0), {"channels": 1})]


async def test_record_until_silence(client: Client, audio: Recorder) -> None:
    result = await client.call_tool("record_until_silence", {"path": "note.m4a", "channels": 2})

    assert result.structured_content == {"path": str(OUT)}
    assert audio.calls == [
        ("record_until_silence", ("note.m4a", 60.0), {"silence": 1.5, "threshold": 0.02, "channels": 2})
    ]


async def test_microphone_level(client: Client, audio: Recorder) -> None:
    result = await client.call_tool("get_microphone_level", {})

    assert result.structured_content == {"level": 0.12}
    assert audio.calls == [("input_level", (0.3,), {})]


async def test_recording_without_the_permission_asks_for_it(
    client: Client, audio: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(
        macos.audio,
        "record",
        Recorder().function("record", error=macos.PermissionDeniedError("Microphone access was denied")),
    )
    monkeypatch.setattr(macos.audio, "request_permission", recorder.function("request_permission", False))

    result = await client.call_tool("record_microphone", {"path": "memo.m4a", "seconds": 5})

    assert result.is_error
    assert recorder.names == ["request_permission"]
    assert "System Settings › Privacy & Security › Microphone" in text(result)


async def test_audio_file_is_read(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    info = macos.audio.AudioInfo(duration=95.5, sample_rate=44100, channels=2, codec="aac", bitrate=256)
    monkeypatch.setattr(macos.audio, "info", lambda path: info)
    monkeypatch.setattr(macos.audio, "classify", lambda path, limit, min_confidence: [("speech", 0.97), ("music", 0.4)])

    described = await client.call_tool("get_audio_info", {"path": "a.m4a"})
    classified = await client.call_tool("classify_audio", {"path": "a.m4a"})

    assert described.structured_content == {
        "duration_seconds": 95.5,
        "sample_rate": 44100,
        "channels": 2,
        "codec": "aac",
        "bitrate_kbps": 256,
    }
    assert classified.structured_content == {
        "result": [{"label": "speech", "confidence": 0.97}, {"label": "music", "confidence": 0.4}]
    }


QUALITY = {"quality": "high", "lossless": False}
WRITERS: Dict[str, Tuple[Dict[str, Any], str, Tuple[Any, ...], Dict[str, Any]]] = {
    "convert_audio": (
        {"source": "a.wav", "output": "a.m4a", "quality": "medium"},
        "convert",
        ("a.wav", "a.m4a"),
        {"quality": "medium", "lossless": False},
    ),
    "trim_audio": (
        {"source": "a.m4a", "output": "b.m4a", "start": 95, "duration": 30},
        "trim",
        ("a.m4a", "b.m4a", 95.0, 30.0),
        QUALITY,
    ),
    "join_audio": (
        {"files": ["a.m4a", "b.wav"], "output": "c.m4a", "lossless": True},
        "concat",
        (["a.m4a", "b.wav"], "c.m4a"),
        {"quality": "high", "lossless": True},
    ),
    "fade_audio": (
        {"source": "a.m4a", "output": "b.m4a", "fade_in_seconds": 2, "fade_out_seconds": 5},
        "fade",
        ("a.m4a", "b.m4a"),
        {"fade_in": 2.0, "fade_out": 5.0, **QUALITY},
    ),
    "change_audio_volume": (
        {"source": "a.m4a", "output": "b.m4a", "decibels": -6},
        "gain",
        ("a.m4a", "b.m4a", -6.0),
        QUALITY,
    ),
    "reverse_audio": ({"source": "a.m4a", "output": "b.m4a"}, "reverse", ("a.m4a", "b.m4a"), QUALITY),
    "change_audio_speed": (
        {"source": "a.m4a", "output": "b.m4a", "factor": 1.5, "keep_pitch": False},
        "speed",
        ("a.m4a", "b.m4a", 1.5),
        {"keep_pitch": False, **QUALITY},
    ),
}


@pytest.mark.parametrize("tool", sorted(WRITERS))
async def test_audio_file_is_written_as_asked(client: Client, monkeypatch: pytest.MonkeyPatch, tool: str) -> None:
    arguments, function, args, options = WRITERS[tool]
    recorder = Recorder()
    monkeypatch.setattr(macos.audio, function, recorder.function(function, OUT))

    result = await client.call_tool(tool, arguments)

    assert not result.is_error, text(result)
    assert result.structured_content == {"path": str(OUT)}
    assert recorder.calls == [(function, args, options)]


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("set_audio_output", {}),
        ("set_audio_output", {"device": ""}),
        ("set_microphone", {}),
        ("set_microphone", {"volume": 101}),
        ("record_microphone", {"path": "a.m4a"}),
        ("record_microphone", {"path": "a.m4a", "seconds": 601}),
        ("record_microphone", {"path": "a.m4a", "seconds": 5, "channels": 3}),
        ("record_until_silence", {"path": "a.m4a", "max_seconds": 0}),
        ("get_microphone_level", {"seconds": 11}),
        ("convert_audio", {"source": "a.wav", "output": "b.m4a", "quality": "best"}),
        ("change_audio_volume", {"source": "a.wav", "output": "b.wav", "decibels": 100}),
        ("change_audio_speed", {"source": "a.wav", "output": "b.wav", "factor": 0}),
        ("join_audio", {"files": [], "output": "c.m4a"}),
    ],
)
async def test_audio_is_not_touched_without_what_it_needs(
    client: Client, audio: Recorder, monkeypatch: pytest.MonkeyPatch, tool: str, arguments: Dict[str, Any]
) -> None:
    for name in ("convert", "trim", "concat", "fade", "gain", "reverse", "speed"):
        monkeypatch.setattr(macos.audio, name, audio.function(name, OUT))

    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert audio.calls == []
