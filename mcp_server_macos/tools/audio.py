"""Tools for the audio devices, the microphone, and audio files, from ``macos.audio``."""

from pathlib import Path
from typing import Annotated, List, Literal, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._permissions import MICROPHONE
from .._registry import DESTRUCTIVE, LONGEST_WAIT, OPEN_ENDED, READ_ONLY, REPLACING, add_tool

DeviceName = Annotated[
    str,
    Field(
        description="The device: its name, its uid, or a part of its name that matches only one device ('AirPods').",
        min_length=1,
    ),
]
Microphone = Annotated[
    Optional[str], Field(description="The microphone, as a device's name or uid. The default input otherwise.")
]
AudioPath = Annotated[
    str,
    Field(
        description="The path of the audio file: anything macOS plays, MP3 and videos' sound included.", min_length=1
    ),
]
Output = Annotated[
    str,
    Field(
        description="Where to save the result. Its extension picks the format: .m4a (AAC), .wav, .aiff or .caf. A file "
        "already there is replaced.",
        min_length=1,
    ),
]
Quality = Annotated[
    Literal["high", "medium", "low"], Field(description="For AAC: 'high', 'medium' or 'low'. Lower is smaller.")
]
Lossless = Annotated[bool, Field(description="For .m4a: true for Apple Lossless rather than AAC.")]
RecordingPath = Annotated[
    str,
    Field(
        description="Where to save the recording. Its extension picks the format: .m4a (small), .wav, .aiff or .caf. "
        "A file already there is replaced.",
        min_length=1,
    ),
]
Channels = Annotated[Literal[1, 2], Field(description="1 for mono, 2 for stereo.")]


class Device(BaseModel):
    """An audio device: speakers, headphones, a microphone, a display's audio..."""

    name: str = Field(description="Its name, as System Settings › Sound shows it.")
    uid: str = Field(description="A stable identifier, which survives reconnecting the device.")
    transport: str = Field(description="How it's connected: 'builtin', 'usb', 'bluetooth', 'hdmi', 'airplay'...")
    is_output: bool = Field(description="Whether it plays sound.")
    is_input: bool = Field(description="Whether it records sound.")


class AudioStatus(BaseModel):
    """The audio devices, and the microphone."""

    outputs: List[Device] = Field(description="The devices that play sound.")
    inputs: List[Device] = Field(description="The devices that record sound.")
    default_output: Optional[str] = Field(description="The uid of the device sound plays through now.")
    default_input: Optional[str] = Field(description="The uid of the microphone apps get by default.")
    input_volume: Optional[int] = Field(
        description="The default microphone's volume, from 0 to 100. Null when it has none."
    )
    input_muted: Optional[bool] = Field(
        description="Whether the default microphone is muted. Null when it has no mute switch."
    )
    microphone_permission: bool = Field(
        description="Whether the app that runs this server may record the microphone. Recording asks for it, the first time."
    )


class AudioInfo(BaseModel):
    """What an audio file contains."""

    duration_seconds: float = Field(description="How long it is, in seconds.")
    sample_rate: int = Field(description="Its samples per second, such as 44100 or 48000.")
    channels: int = Field(description="Its channels: 1 (mono), 2 (stereo)...")
    codec: str = Field(description="Its codec: 'aac', 'alac', 'pcm' (uncompressed), 'mp3'... or a four-character code.")
    bitrate_kbps: Optional[int] = Field(description="Its bitrate, in kilobits per second, when the file says.")


class Level(BaseModel):
    """How loud the microphone hears it."""

    level: float = Field(
        description="From 0 (silence) to 1 (the loudest it takes): about 0.01 in a quiet room, 0.1 to 0.3 for someone "
        "talking nearby."
    )


class Label(BaseModel):
    """Something a sound has."""

    label: str = Field(
        description="What it is, from Apple's list of over 300 sounds: 'speech', 'music', 'dog_bark', 'applause'..."
    )
    confidence: float = Field(description="How sure it is, from 0 to 1.")


class Saved(BaseModel):
    """A file that was written."""

    path: str = Field(description="The path of the file.")


def _device(device: "macos.audio.Device") -> Device:
    return Device(
        name=device.name,
        uid=device.uid,
        transport=device.transport,
        is_output=device.is_output,
        is_input=device.is_input,
    )


def _saved(path: Path) -> Saved:
    return Saved(path=str(path))


def get_audio_status() -> AudioStatus:
    """
    Get the audio devices, the ones sound plays through and records from by default, the default
    microphone's volume and mute, and whether recording the microphone is allowed.
    """
    output, microphone = macos.audio.default_output(), macos.audio.default_input()
    volume: Optional[int] = None
    muted: Optional[bool] = None
    if microphone is not None:
        try:
            volume = round(macos.audio.input_volume() * 100)
        except macos.MacOSError:
            pass  # a microphone without a volume control
        try:
            muted = macos.audio.input_muted()
        except macos.MacOSError:
            pass  # nor a mute switch
    every = macos.audio.devices()
    return AudioStatus(
        outputs=[_device(device) for device in every if device.is_output],
        inputs=[_device(device) for device in every if device.is_input],
        default_output=None if output is None else output.uid,
        default_input=None if microphone is None else microphone.uid,
        input_volume=volume,
        input_muted=muted,
        microphone_permission=macos.audio.has_permission(),
    )


def set_audio_output(device: DeviceName) -> Device:
    """
    Play the Mac's sound through a device: speakers, headphones, a display... An AirPlay device plays
    it elsewhere, over the network: whatever the Mac plays is heard where that device is.
    """
    return _device(macos.audio.set_output(device))


def set_audio_input(device: DeviceName) -> Device:
    """Record from a device by default: the microphone apps get."""
    return _device(macos.audio.set_input(device))


def set_microphone(
    volume: Annotated[
        Optional[int], Field(description="The microphone's input volume, from 0 to 100.", ge=0, le=100)
    ] = None,
    muted: Annotated[
        Optional[bool],
        Field(
            description="True to mute it for every app at once, false to unmute it. Some microphones have no mute switch."
        ),
    ] = None,
    device: Microphone = None,
) -> str:
    """Set the microphone's volume, or mute it for every app at once, like a "mute me" shortcut in meetings."""
    if volume is None and muted is None:
        raise ValueError("no setting was given: say the volume, muted, or both")
    changed: List[str] = []
    # Muting goes first, and unmuting last: if the other change fails, the microphone isn't left live
    # when it was asked to be muted, nor live at a volume it was asked to leave.
    if muted is True:
        macos.audio.mute_input(True, device=device)
        changed.append("muted")
    if volume is not None:
        macos.audio.set_input_volume(volume / 100, device=device)
        changed.append("volume {}".format(volume))
    if muted is False:
        macos.audio.mute_input(False, device=device)
        changed.append("unmuted")
    return "Microphone: {}.".format(", ".join(changed))


def record_microphone(
    path: RecordingPath,
    seconds: Annotated[float, Field(description="How long to record, in seconds: up to 600.", gt=0, le=LONGEST_WAIT)],
    channels: Channels = 1,
) -> Saved:
    """
    Record the default microphone for some seconds into a file, and return it when done. It records
    the room the user is in: record when they asked for it.
    """
    return _saved(macos.audio.record(path, seconds, channels=channels))


def record_until_silence(
    path: RecordingPath,
    max_seconds: Annotated[
        float, Field(description="The longest to record, in seconds: up to 600.", gt=0, le=LONGEST_WAIT)
    ] = 60.0,
    silence_seconds: Annotated[float, Field(description="How long a quiet ends it, in seconds.", gt=0, le=60)] = 1.5,
    threshold: Annotated[
        float, Field(description="The level that counts as sound, between 0 and 1, both left out.", gt=0, lt=1)
    ] = 0.02,
    channels: Channels = 1,
) -> Saved:
    """
    Record the microphone until the speaker stops talking: it waits for sound, then stops after a
    moment of quiet, or at the longest given. For voice notes and spoken commands. Record when the user
    asked for it.
    """
    return _saved(
        macos.audio.record_until_silence(
            path, max_seconds, silence=silence_seconds, threshold=threshold, channels=channels
        )
    )


def get_microphone_level(
    seconds: Annotated[float, Field(description="How long to listen, in seconds.", gt=0, le=10)] = 0.3,
) -> Level:
    """Say how loud the microphone hears it right now: to tell whether someone is speaking. Nothing is kept."""
    return Level(level=macos.audio.input_level(seconds))


def get_audio_info(path: AudioPath) -> AudioInfo:
    """Get an audio file's duration, sample rate, channels, codec and bitrate: or a video's sound's."""
    info = macos.audio.info(path)
    return AudioInfo(
        duration_seconds=info.duration,
        sample_rate=info.sample_rate,
        channels=info.channels,
        codec=info.codec,
        bitrate_kbps=info.bitrate,
    )


def classify_audio(
    path: AudioPath,
    limit: Annotated[int, Field(description="How many labels, at most.", ge=1, le=50)] = 5,
    min_confidence: Annotated[
        float, Field(description="Leave out the labels less sure than this, from 0 to 1.", ge=0, le=1)
    ] = 0.1,
) -> List[Label]:
    """Say what an audio file, or a video, sounds like, from over 300 sounds: speech, music, a dog, applause, rain... Offline."""
    return [
        Label(label=label, confidence=confidence)
        for label, confidence in macos.audio.classify(path, limit=limit, min_confidence=min_confidence)
    ]


def convert_audio(source: AudioPath, output: Output, quality: Quality = "high", lossless: Lossless = False) -> Saved:
    """Convert an audio file to another format, such as WAV or MP3 to M4A."""
    return _saved(macos.audio.convert(source, output, quality=quality, lossless=lossless))


def trim_audio(
    source: AudioPath,
    output: Output,
    start: Annotated[float, Field(description="Where to start, in seconds from the beginning.", ge=0)] = 0.0,
    duration: Annotated[
        Optional[float], Field(description="How long to keep, in seconds. To the end by default.", gt=0)
    ] = None,
    quality: Quality = "high",
    lossless: Lossless = False,
) -> Saved:
    """Keep part of an audio file."""
    return _saved(macos.audio.trim(source, output, start, duration, quality=quality, lossless=lossless))


def join_audio(
    files: Annotated[
        List[str], Field(description="The audio files, in order. They may differ in format.", min_length=1)
    ],
    output: Output,
    quality: Quality = "high",
    lossless: Lossless = False,
) -> Saved:
    """Join audio files one after another into one, in the first one's sample rate and channels."""
    return _saved(macos.audio.concat(files, output, quality=quality, lossless=lossless))


def fade_audio(
    source: AudioPath,
    output: Output,
    fade_in_seconds: Annotated[
        float, Field(description="How long to rise from silence at the start, in seconds.", ge=0)
    ] = 0.0,
    fade_out_seconds: Annotated[
        float, Field(description="How long to fall to silence at the end, in seconds.", ge=0)
    ] = 0.0,
    quality: Quality = "high",
    lossless: Lossless = False,
) -> Saved:
    """Fade an audio file in from silence at its start, and out to silence at its end."""
    return _saved(
        macos.audio.fade(
            source, output, fade_in=fade_in_seconds, fade_out=fade_out_seconds, quality=quality, lossless=lossless
        )
    )


def change_audio_volume(
    source: AudioPath,
    output: Output,
    decibels: Annotated[
        float, Field(description="How much louder, in decibels: +6 is about twice as loud, -6 half.", ge=-60, le=60)
    ],
    quality: Quality = "high",
    lossless: Lossless = False,
) -> Saved:
    """Make an audio file louder or quieter. Loud parts pushed past the maximum are clipped."""
    return _saved(macos.audio.gain(source, output, decibels, quality=quality, lossless=lossless))


def reverse_audio(source: AudioPath, output: Output, quality: Quality = "high", lossless: Lossless = False) -> Saved:
    """Save an audio file played backwards."""
    return _saved(macos.audio.reverse(source, output, quality=quality, lossless=lossless))


def change_audio_speed(
    source: AudioPath,
    output: Output,
    factor: Annotated[float, Field(description="How many times faster: 1.5, or 0.75 for slower.", gt=0, le=100)],
    keep_pitch: Annotated[
        bool, Field(description="False to change the pitch with the speed, like a record played faster.")
    ] = True,
    quality: Quality = "high",
    lossless: Lossless = False,
) -> Saved:
    """Play an audio file faster or slower, at the same pitch by default: a lecture or a podcast, without chipmunk voices."""
    return _saved(macos.audio.speed(source, output, factor, keep_pitch=keep_pitch, quality=quality, lossless=lossless))


def register(server: MCPServer) -> None:
    add_tool(server, get_audio_status, title="Get the audio devices", annotations=READ_ONLY)
    # An output may be an AirPlay receiver: the Mac's sound then goes over the network, to another room.
    add_tool(server, set_audio_output, title="Set the sound output", annotations=OPEN_ENDED)
    add_tool(server, set_audio_input, title="Set the microphone", annotations=REPLACING)
    add_tool(server, set_microphone, title="Set the microphone's volume or mute", annotations=REPLACING)
    add_tool(
        server,
        get_microphone_level,
        title="Hear how loud the microphone is",
        annotations=READ_ONLY,
        permission=MICROPHONE,
    )
    # Recording writes over a file, and records the room: marked to be asked about first.
    add_tool(server, record_microphone, title="Record the microphone", annotations=DESTRUCTIVE, permission=MICROPHONE)
    add_tool(server, record_until_silence, title="Record until silence", annotations=DESTRUCTIVE, permission=MICROPHONE)
    add_tool(server, get_audio_info, title="Get an audio file's information", annotations=READ_ONLY)
    add_tool(server, classify_audio, title="Say what a sound is", annotations=READ_ONLY)
    # These change the sound, and the output may be the source: done again, they cut, fade, amplify or
    # reverse it again, or lose more quality. Not idempotent, then, and they write over a file.
    for transform, title in (
        (convert_audio, "Convert an audio file"),
        (trim_audio, "Trim an audio file"),
        (join_audio, "Join audio files"),
        (fade_audio, "Fade an audio file"),
        (change_audio_volume, "Change an audio file's volume"),
        (reverse_audio, "Reverse an audio file"),
        (change_audio_speed, "Change an audio file's speed"),
    ):
        add_tool(server, transform, title=title, annotations=DESTRUCTIVE)
