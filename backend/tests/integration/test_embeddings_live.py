"""S2.2.1's first acceptance criterion, against the real OpenRouter `/embeddings`.

*Given the demo pack, when I query in French for information-security certification, then
the German ISO 27001 chunk ranks first.* Cross-language retrieval cannot be faked: a stub
transport proves the plumbing, not that `openai/text-embedding-3-small` actually places a
French query next to a German certificate. So this test is `live`-marked and costs money.

The German passages below stand in for the demo GmbH pack, which is **S6.3 and not built
yet**. They are typed out here rather than read from a fixture on purpose: when S6.3 lands,
this file should start reading the real pack through `Chunker`, and a fixture path would
have hidden that this is a placeholder. The retrieval claim it makes is the same one --
French query, German answer, no shared vocabulary between them.

There is deliberately no database here. `ChunkVectorStore` needs a live Supabase, which is
a different dependency with a different failure mode; ranking is compared in Python with
the same cosine distance `<=>` computes, so a failure points at the embedding model and not
at pgvector.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import pytest

from crossbid.ingestion.chunker import Chunk
from crossbid.ingestion.embeddings import EmbeddingsClient, embed_chunks
from crossbid.settings import Settings, load_settings

pytestmark = pytest.mark.live

FRENCH_QUERY = "certification de sécurité de l'information selon une norme reconnue"
"""No token here also appears in the German passages -- not even "ISO"."""

GERMAN_PASSAGES = (
    "Unser Unternehmen ist seit 2019 nach ISO/IEC 27001 zertifiziert. Das Zertifikat für "
    "das Informationssicherheits-Managementsystem wurde vom TÜV Süd ausgestellt und ist "
    "bis zum 31.12.2027 gültig.",
    "Der Jahresumsatz der Gesellschaft betrug im Geschäftsjahr 2024 rund 4.200.000,00 EUR. "
    "Der Jahresabschluss wurde vom Steuerberater geprüft und im Bundesanzeiger "
    "veröffentlicht.",
    "Die Gesellschaft beschäftigt im Jahresdurchschnitt 38 Mitarbeiterinnen und "
    "Mitarbeiter, davon 24 in der Softwareentwicklung und 6 im technischen Support.",
    "Es liegen keine Eintragungen im Gewerbezentralregister vor. Eine "
    "Unbedenklichkeitsbescheinigung des Finanzamts München wird auf Verlangen "
    "nachgereicht.",
)
CERTIFICATION_PASSAGE_INDEX = 0


@pytest.fixture(scope="module")
def live_settings() -> Settings:
    """The real environment, including the real `OPENROUTER_API_KEY`."""
    return load_settings()


def cosine_distance(left: Sequence[float], right: Sequence[float]) -> float:
    """What `<=>` computes, in Python: 1 - cosine similarity."""
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    assert norm > 0, "a zero vector has no direction and cannot be ranked"
    return 1.0 - dot / norm


@pytest.mark.anyio
async def test_a_french_query_ranks_the_german_certificate_first(
    live_settings: Settings,
) -> None:
    # Arrange
    chunks = tuple(
        Chunk(
            document_id="demo-gmbh-pack",
            index=index,
            pages=(index + 1,),
            text=text,
            token_count=len(text.split()),
        )
        for index, text in enumerate(GERMAN_PASSAGES)
    )

    # Act
    async with EmbeddingsClient(live_settings) as client:
        embedded = await embed_chunks(client, chunks)
        query = await client.embed_query(FRENCH_QUERY)

    # Assert
    ranked = sorted(embedded, key=lambda row: cosine_distance(query, row.embedding))
    assert ranked[0].chunk.index == CERTIFICATION_PASSAGE_INDEX, [
        (row.chunk.index, cosine_distance(query, row.embedding)) for row in ranked
    ]


@pytest.mark.anyio
async def test_the_configured_slug_answers_and_returns_the_configured_width(
    live_settings: Settings,
) -> None:
    """ADR-0005 in one call: there is no `/models` listing for embeddings, so the only way
    to know the configured slug is usable on this account is to use it. A width other than
    `ingestion.embed_dimensions` would be rejected by the `vector(1536)` column later."""
    # Act
    async with EmbeddingsClient(live_settings) as client:
        values = await client.embed_query("ping")

        # Assert
        assert len(values) == client.dimensions
