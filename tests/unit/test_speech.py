"""The tools of mcp_server_macos.tools.speech, with macos.speech faked."""

from pathlib import Path
from typing import Any, Dict, List

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio

VOICES = [
    macos.speech.Voice(name="Samantha", locale="en_US", sample="Hello! My name is Samantha."),
    macos.speech.Voice(name="Daniel", locale="en_GB", sample="Hello! My name is Daniel."),
    macos.speech.Voice(name="Luciana", locale="pt_BR", sample="Olá, meu nome é Luciana."),
    macos.speech.Voice(name="Joana", locale="pt_PT", sample="Olá, chamo-me Joana."),
]


@pytest.fixture
def speech(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    """Four voices, and the calls made to macos.speech.say, which says nothing."""
    recorder = Recorder()
    monkeypatch.setattr(macos.speech, "voices", lambda: list(VOICES))
    monkeypatch.setattr(macos.speech, "say", recorder.function("say"))
    return recorder


@pytest.mark.parametrize(
    "arguments, expected",
    [
        ({}, ["Samantha", "Daniel", "Luciana", "Joana"]),
        ({"locale": "pt"}, ["Luciana", "Joana"]),
        ({"locale": "pt_BR"}, ["Luciana"]),
        ({"locale": "PT-br"}, ["Luciana"]),
        ({"locale": "en_GB"}, ["Daniel"]),
        ({"locale": "ja"}, []),
    ],
)
async def test_list_voices(client: Client, speech: Recorder, arguments: Dict[str, Any], expected: List[str]) -> None:
    result = await client.call_tool("list_voices", arguments)

    assert not result.is_error
    assert result.structured_content is not None
    assert [voice["name"] for voice in result.structured_content["result"]] == expected
    assert speech.calls == []


async def test_list_voices_says_what_each_speaks(client: Client, speech: Recorder) -> None:
    result = await client.call_tool("list_voices", {"locale": "pt_PT"})

    assert result.structured_content == {
        "result": [{"name": "Joana", "locale": "pt_PT", "sample": "Olá, chamo-me Joana."}]
    }


@pytest.mark.parametrize(
    "arguments, options, said",
    [
        ({"text": "Hello"}, {"voice": None, "rate": None, "wait": True}, "Spoken."),
        (
            {"text": "Olá!", "voice": "Luciana", "rate": 180, "wait": False},
            {"voice": "Luciana", "rate": 180.0, "wait": False},
            "Speaking.",
        ),
    ],
)
async def test_speak(client: Client, speech: Recorder, arguments: Dict[str, Any], options: Dict[str, Any], said: str) -> None:
    result = await client.call_tool("speak", arguments)

    assert not result.is_error
    assert text(result) == said
    assert speech.calls == [("say", (arguments["text"],), options)]


async def test_speak_takes_text_as_it_is(client: Client, speech: Recorder) -> None:
    # Text that starts like an option of the say command, or looks like a shell's: pymacos passes it as text.
    spoken = "-v ? $(id) \"quoted\" — it's fine"

    result = await client.call_tool("speak", {"text": spoken})

    assert not result.is_error
    assert speech.calls == [("say", (spoken,), {"voice": None, "rate": None, "wait": True})]


@pytest.mark.parametrize(
    "arguments", [{}, {"text": ""}, {"text": "Hi", "rate": 0}, {"text": "Hi", "rate": -10}, {"text": "Hi", "rate": 10000}]
)
async def test_speak_refuses_what_it_does_not_take(client: Client, speech: Recorder, arguments: Dict[str, Any]) -> None:
    result = await client.call_tool("speak", arguments)

    assert result.is_error
    assert speech.calls == []


async def test_save_speech(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.speech, "say", recorder.function("say", Path("/Users/me/hello.m4a")))

    result = await client.call_tool(
        "save_speech", {"text": "Hello", "path": "~/hello.m4a", "voice": "Samantha", "rate": 200}
    )

    assert not result.is_error
    # The path pymacos wrote to, which it made whole.
    assert result.structured_content == {"path": "/Users/me/hello.m4a"}
    assert recorder.calls == [("say", ("Hello",), {"voice": "Samantha", "rate": 200.0, "output": "~/hello.m4a"})]


async def test_save_speech_in_a_format_there_is_not(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    error = ValueError("unsupported audio format '.mp3'; use one of .aif, .aiff, .caf, .m4a, .wav")
    monkeypatch.setattr(macos.speech, "say", Recorder().function("say", error=error))

    result = await client.call_tool("save_speech", {"text": "Hello", "path": "/tmp/hello.mp3"})

    assert result.is_error
    assert "unsupported audio format '.mp3'" in text(result)


@pytest.mark.parametrize("arguments", [{"text": "Hello"}, {"path": "/tmp/a.m4a"}, {"text": "Hello", "path": ""}])
async def test_save_speech_needs_a_text_and_a_file(client: Client, speech: Recorder, arguments: Dict[str, Any]) -> None:
    result = await client.call_tool("save_speech", arguments)

    assert result.is_error
    assert speech.calls == []
