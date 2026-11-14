"""Tools that understand text, offline, with the models macOS has, from ``macos.language``."""

from typing import Annotated, List, Optional

import macos
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from .._registry import READ_ONLY, add_tool

Text = Annotated[str, Field(description="The text.", min_length=1)]
Language = Annotated[
    Optional[str],
    Field(
        description="The text's language, as an ISO code ('en', 'fr', 'pt'...). Detected when left out, which needs "
        "a few words: give it for a single word or a very short text."
    ),
]


class Candidate(BaseModel):
    """A language a text may be in."""

    language: str = Field(description="The language's ISO code, such as 'en', 'fr' or 'zh-Hans'.")
    probability: float = Field(description="How likely it is, from 0 to 1.")


class DetectedLanguage(BaseModel):
    """The language of a text."""

    language: Optional[str] = Field(description="The most likely language, as an ISO code. Null when there's nothing to detect.")
    candidates: List[Candidate] = Field(description="The most likely languages, with how likely each is.")


class Sentiment(BaseModel):
    """How positive a text sounds."""

    score: Optional[float] = Field(
        description="From -1 (very negative) to 1 (very positive). Null when there's nothing to score: no words, "
        "or a language the model doesn't cover (Chinese, Japanese and Russian among others)."
    )


class Similarity(BaseModel):
    """How close two texts are in meaning."""

    similarity: float = Field(description="From -1 to 1: the higher, the closer.")


class Embedding(BaseModel):
    """The meaning of a text, as numbers."""

    embedding: List[float] = Field(description="The vector that represents the text's meaning.")


class Entity(BaseModel):
    """A name found in a text."""

    text: str = Field(description="The name, as written.")
    kind: str = Field(description="What it names: 'person', 'place' or 'organization'.")
    start: int = Field(description="Where it starts in the text, counting characters from 0.")


def detect_language(
    text: Text,
    limit: Annotated[int, Field(description="How many candidates to return.", ge=1, le=20)] = 3,
) -> DetectedLanguage:
    """
    Detect the language of a text, with how likely the answer and its runners-up are. A few words are
    enough, but a single word is often guessed wrong: the probabilities say how sure it is.
    """
    return DetectedLanguage(
        language=macos.language.detect(text),
        candidates=[
            Candidate(language=language, probability=probability)
            for language, probability in macos.language.guess(text, limit=limit)
        ],
    )


def analyze_sentiment(text: Text) -> Sentiment:
    """
    Score how positive a text sounds. The score is a rough signal, best for comparing texts such as
    reviews or messages: a neutral sentence won't always come out at exactly 0.
    """
    return Sentiment(score=macos.language.sentiment(text))


def compare_texts(
    first: Annotated[str, Field(description="A text.", min_length=1)],
    second: Annotated[str, Field(description="The text to compare it with.", min_length=1)],
    language: Language = None,
) -> Similarity:
    """
    Score how close two texts are in meaning. The scores are for comparing: which of two texts is
    closer to a third. A score alone means little, and opposites ('happy', 'sad') often score as
    related, since they show up in the same contexts.
    """
    return Similarity(similarity=macos.language.similarity(first, second, language=language))


def embed_text(text: Text, language: Language = None) -> Embedding:
    """
    Get the sentence embedding of a text: a vector of a few hundred numbers that represents its
    meaning, to search many texts by meaning (compare vectors with cosine similarity). The texts must
    be embedded in the same language to be comparable.
    """
    return Embedding(embedding=macos.language.embedding(text, language=language))


def find_entities(text: Text, language: Language = None) -> List[Entity]:
    """
    Find the names of people, places and organizations in a text. It's a statistical model: common
    names are found reliably, unusual ones can be missed or mislabelled, and names typed in lowercase
    usually are. Fails for a language whose model this Mac doesn't have.
    """
    return [
        Entity(text=entity.text, kind=entity.kind, start=entity.start)
        for entity in macos.language.entities(text, language=language)
    ]


def extract_keywords(
    text: Text,
    language: Language = None,
    verbs: Annotated[bool, Field(description="True to add the verbs to the nouns.")] = False,
    lemmas: Annotated[
        bool,
        Field(description="True for each word's base form ('displays' becomes 'display'), which groups its variations."),
    ] = False,
) -> List[str]:
    """
    Get the main words of a text: its nouns, names included, in order and without repeats. Fails for a
    language whose model this Mac doesn't have.
    """
    return macos.language.keywords(text, language=language, verbs=verbs, lemmas=lemmas)


def register(server: MCPServer) -> None:
    add_tool(server, detect_language, title="Detect a text's language", annotations=READ_ONLY)
    add_tool(server, analyze_sentiment, title="Score a text's sentiment", annotations=READ_ONLY)
    add_tool(server, compare_texts, title="Compare two texts' meaning", annotations=READ_ONLY)
    add_tool(server, embed_text, title="Get a text's embedding", annotations=READ_ONLY)
    add_tool(server, find_entities, title="Find the names in a text", annotations=READ_ONLY)
    add_tool(server, extract_keywords, title="Get a text's keywords", annotations=READ_ONLY)
