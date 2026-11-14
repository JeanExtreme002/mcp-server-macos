"""The language tools against this Mac's models: nothing is changed, and nothing leaves the Mac."""

import pytest
from mcp import Client

from tests.helpers import text
from tests.live.helpers import call

pytestmark = pytest.mark.anyio


async def test_detect_language(client: Client) -> None:
    detected = await call(client, "detect_language", {"text": "Bonjour, comment allez-vous aujourd'hui ?"})

    assert detected["language"] == "fr"
    assert detected["candidates"][0]["language"] == "fr"
    assert 0.5 < detected["candidates"][0]["probability"] <= 1
    assert len(detected["candidates"]) <= 3


async def test_analyze_sentiment(client: Client) -> None:
    good = (await call(client, "analyze_sentiment", {"text": "This is wonderful, I love it!"}))["score"]
    bad = (await call(client, "analyze_sentiment", {"text": "This is terrible, I hate it."}))["score"]

    if good is None or bad is None:
        pytest.skip("this Mac's sentiment model doesn't score English")
    assert -1 <= bad < good <= 1

    assert (await call(client, "analyze_sentiment", {"text": "12345"}))["score"] is None


async def test_models_of_a_language(client: Client) -> None:
    # The models are per language, and macOS has the ones for the languages it uses: one that's
    # missing is said, not guessed around.
    sentence = "Tim Cook, the CEO of Apple, visited Paris yesterday."
    for tool, arguments in (
        ("find_entities", {"text": sentence, "language": "en"}),
        ("extract_keywords", {"text": sentence, "language": "en"}),
        ("compare_texts", {"first": "The cat sat on the mat.", "second": "A kitten rests on a rug.", "language": "en"}),
        ("embed_text", {"text": sentence, "language": "en"}),
    ):
        result = await client.call_tool(tool, arguments)
        if result.is_error:
            assert "NotSupportedError" in text(result), text(result)
            continue
        content = result.structured_content
        assert content is not None
        if tool == "find_entities":
            assert {"text": "Paris", "kind": "place", "start": sentence.index("Paris")} in content["result"]
        elif tool == "extract_keywords":
            assert "Paris" in content["result"]
        elif tool == "compare_texts":
            assert -1 <= content["similarity"] <= 1
        else:
            assert len(content["embedding"]) > 100
