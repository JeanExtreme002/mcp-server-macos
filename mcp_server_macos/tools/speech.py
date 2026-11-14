"""Tools that speak text with the system voices, from ``macos.speech``."""

from typing import Annotated, List, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._registry import ADDITIVE, READ_ONLY, REPLACING, add_tool

Text = Annotated[str, Field(description="The text to speak.", min_length=1)]
VoiceName = Annotated[
    Optional[str],
    Field(description="The name of a voice, such as 'Samantha': list_voices lists them. The system's default one otherwise."),
]
Rate = Annotated[
    Optional[float],
    Field(description="The speed, in words per minute: about 175 to 200 is normal. The voice's own by default.", gt=0, le=720),
]


class Voice(BaseModel):
    """An installed speech voice."""

    name: str = Field(description="Its name, which speak takes.")
    locale: str = Field(description="The language and region it speaks, such as 'en_US' or 'pt_BR'.")
    sample: str = Field(description="A sentence it says to introduce itself.")


class Saved(BaseModel):
    """A file that was written."""

    path: str = Field(description="The path of the file.")


def list_voices(
    locale: Annotated[
        Optional[str],
        Field(
            description="Keep the voices of a language or a region: 'pt' for Portuguese, 'pt_BR' for Brazil's. All "
            "of them by default."
        ),
    ] = None,
) -> List[Voice]:
    """List the speech voices installed on this Mac, with the language each speaks. There may be over a hundred."""
    voices = macos.speech.voices()
    if locale is not None:
        wanted = locale.replace("-", "_").casefold()
        voices = [voice for voice in voices if voice.locale.replace("-", "_").casefold().startswith(wanted)]
    return [Voice(name=voice.name, locale=voice.locale, sample=voice.sample) for voice in voices]


def speak(
    text: Text,
    voice: VoiceName = None,
    rate: Rate = None,
    wait: Annotated[
        bool,
        Field(description="True to return when the speech ends, false to return right away while it's spoken."),
    ] = True,
) -> str:
    """
    Speak text out loud, through the Mac's speakers, with a system voice. A voice that isn't installed
    isn't an error: the default voice speaks instead.
    """
    macos.speech.say(text, voice=voice, rate=rate, wait=wait)
    return "Spoken." if wait else "Speaking."


def save_speech(
    text: Text,
    path: Annotated[
        str,
        Field(
            description="The path of the audio file to write, ending in .aiff, .m4a, .wav or .caf. A file already "
            "there is replaced.",
            min_length=1,
        ),
    ],
    voice: VoiceName = None,
    rate: Rate = None,
) -> Saved:
    """Save text spoken by a system voice to an audio file, without playing it."""
    saved = macos.speech.say(text, voice=voice, rate=rate, output=path)
    return Saved(path=str(path if saved is None else saved))


def register(server: MCPServer) -> None:
    add_tool(server, list_voices, title="List the speech voices", annotations=READ_ONLY)
    add_tool(server, speak, title="Speak text out loud", annotations=ADDITIVE)
    # It writes a file, over the one that may be there.
    add_tool(server, save_speech, title="Save speech to an audio file", annotations=REPLACING)
