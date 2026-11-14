"""The tools of mcp_server_macos.tools.language, with macos.language faked."""

from typing import Any, Dict, Optional

import macos
import pytest
from mcp import Client

from tests.helpers import Recorder, text

pytestmark = pytest.mark.anyio


async def test_detect_language(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.language, "detect", recorder.function("detect", "pt"))
    monkeypatch.setattr(macos.language, "guess", recorder.function("guess", [("pt", 0.97), ("es", 0.02), ("gl", 0.01)]))

    result = await client.call_tool("detect_language", {"text": "Olá, tudo bem?"})

    assert not result.is_error
    assert result.structured_content == {
        "language": "pt",
        "candidates": [
            {"language": "pt", "probability": 0.97},
            {"language": "es", "probability": 0.02},
            {"language": "gl", "probability": 0.01},
        ],
    }
    assert recorder.calls == [("detect", ("Olá, tudo bem?",), {}), ("guess", ("Olá, tudo bem?",), {"limit": 3})]


async def test_detect_language_of_nothing_to_detect(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.language, "detect", recorder.function("detect", None))
    monkeypatch.setattr(macos.language, "guess", recorder.function("guess", []))

    result = await client.call_tool("detect_language", {"text": "12345", "limit": 5})

    assert not result.is_error
    assert result.structured_content == {"language": None, "candidates": []}
    assert recorder.calls[1] == ("guess", ("12345",), {"limit": 5})


@pytest.mark.parametrize("score", [0.8, -1.0, 0.0, None])
async def test_analyze_sentiment(client: Client, monkeypatch: pytest.MonkeyPatch, score: Optional[float]) -> None:
    # None: no words in the text, or a language the model doesn't cover.
    recorder = Recorder()
    monkeypatch.setattr(macos.language, "sentiment", recorder.function("sentiment", score))

    result = await client.call_tool("analyze_sentiment", {"text": "I love it"})

    assert not result.is_error
    assert result.structured_content == {"score": score}
    assert recorder.calls == [("sentiment", ("I love it",), {})]


@pytest.mark.parametrize("arguments, language", [({}, None), ({"language": "en"}, "en")])
async def test_compare_texts(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any], language: Optional[str]
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.language, "similarity", recorder.function("similarity", 0.71))

    result = await client.call_tool("compare_texts", {"first": "car", "second": "automobile", **arguments})

    assert not result.is_error
    assert result.structured_content == {"similarity": 0.71}
    assert recorder.calls == [("similarity", ("car", "automobile"), {"language": language})]


async def test_embed_text(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    vector = [0.25, -0.5, 0.125, 0.0]
    monkeypatch.setattr(macos.language, "embedding", recorder.function("embedding", vector))

    result = await client.call_tool("embed_text", {"text": "hello world", "language": "en"})

    assert not result.is_error
    assert result.structured_content == {"embedding": vector}
    assert recorder.calls == [("embedding", ("hello world",), {"language": "en"})]


async def test_find_entities(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    entities = [
        macos.language.Entity(text="Tim Cook", kind="person", start=0),
        macos.language.Entity(text="Apple", kind="organization", start=21),
        macos.language.Entity(text="Paris", kind="place", start=36),
    ]
    monkeypatch.setattr(macos.language, "entities", recorder.function("entities", entities))
    sentence = "Tim Cook, the CEO of Apple, visited Paris yesterday."

    result = await client.call_tool("find_entities", {"text": sentence})

    assert not result.is_error
    assert result.structured_content == {
        "result": [
            {"text": "Tim Cook", "kind": "person", "start": 0},
            {"text": "Apple", "kind": "organization", "start": 21},
            {"text": "Paris", "kind": "place", "start": 36},
        ]
    }
    assert recorder.calls == [("entities", (sentence,), {"language": None})]


@pytest.mark.parametrize(
    "arguments, options",
    [
        ({}, {"language": None, "verbs": False, "lemmas": False}),
        ({"language": "pt", "verbs": True, "lemmas": True}, {"language": "pt", "verbs": True, "lemmas": True}),
    ],
)
async def test_extract_keywords(
    client: Client, monkeypatch: pytest.MonkeyPatch, arguments: Dict[str, Any], options: Dict[str, Any]
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(macos.language, "keywords", recorder.function("keywords", ["MacBook", "battery", "life"]))

    result = await client.call_tool("extract_keywords", {"text": "The MacBook has battery life.", **arguments})

    assert not result.is_error
    assert result.structured_content == {"result": ["MacBook", "battery", "life"]}
    assert recorder.calls == [("keywords", ("The MacBook has battery life.",), options)]


@pytest.mark.parametrize(
    "tool, function, arguments",
    [
        ("find_entities", "entities", {"text": "Олег живёт в Москве", "language": "ru"}),
        ("extract_keywords", "keywords", {"text": "Олег живёт в Москве"}),
        ("compare_texts", "similarity", {"first": "a", "second": "b", "language": "xx"}),
        ("embed_text", "embedding", {"text": "x", "language": "xx"}),
    ],
)
async def test_language_this_mac_has_no_model_for(
    client: Client, monkeypatch: pytest.MonkeyPatch, tool: str, function: str, arguments: Dict[str, Any]
) -> None:
    error = macos.NotSupportedError("this Mac has no model for that language")
    monkeypatch.setattr(macos.language, function, Recorder().function(function, error=error))

    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert "NotSupportedError: this Mac has no model for that language" in text(result)


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("detect_language", {}),
        ("detect_language", {"text": ""}),
        ("detect_language", {"text": "hi", "limit": 0}),
        ("analyze_sentiment", {"text": ""}),
        ("compare_texts", {"first": "a"}),
        ("compare_texts", {"first": "", "second": "b"}),
        ("embed_text", {"text": ""}),
        ("find_entities", {}),
        ("extract_keywords", {"text": "a", "verbs": "some"}),
    ],
)
async def test_language_tools_need_a_text(
    client: Client, monkeypatch: pytest.MonkeyPatch, tool: str, arguments: Dict[str, Any]
) -> None:
    recorder = Recorder()
    for name in ("detect", "guess", "sentiment", "similarity", "embedding", "entities", "keywords"):
        monkeypatch.setattr(macos.language, name, recorder.function(name))

    result = await client.call_tool(tool, arguments)

    assert result.is_error
    assert recorder.calls == []
