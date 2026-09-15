"""What the injection guard decides about a set of chunks, for every corpus that has one.

Both corpora reach a model the same way -- retrieved by a RAG tool and pasted into a prompt
as evidence -- so both get the same treatment, and it lives here rather than in either
caller. `ingestion/pipeline.py` uses it for a company's evidence at upload;
`ingestion/tender_index.py` uses it for a tender pack at bid start.

**Withholding is the retrieval answer, and it is not the answer everywhere.** ADR-0049 draws
the line by *path*, not by document kind: text destined for a corpus is withheld when it is
flagged, because a flagged chunk retrieved into a check prompt is the attack working; a
tender *page* on its way to `extract_reqs` is reported and still read, because dropping it
would let an attacker delete the requirement they least want checked. The same tender PDF
therefore meets both rules -- withheld from `tender_chunks`, reported to the reviewer -- and
that is the asymmetry working as designed rather than an inconsistency.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence

from crossbid.guards.injection import InjectionFinding, scan
from crossbid.ingestion.chunker import Chunk
from crossbid.ingestion.injection_review import InjectionConfirmer, released

logger = logging.getLogger(__name__)


def partition_by_guard(
    chunks: Sequence[Chunk],
) -> tuple[list[Chunk], list[tuple[int, InjectionFinding]]]:
    """The chunks that may be stored, and the numbered ones the guard refused.

    Numbered by position in the document's own chunk sequence, one-based, because that is
    what `documents.flagged_chunks` means and what a reviewer counts when they go looking.
    """
    kept: list[Chunk] = []
    flagged: list[tuple[int, InjectionFinding]] = []
    for number, chunk in enumerate(chunks, start=1):
        finding = scan(chunk.text)
        if finding is None:
            kept.append(chunk)
        else:
            flagged.append((number, finding))
    return kept, flagged


async def review_flagged(
    chunks: Sequence[Chunk],
    suspected: Sequence[tuple[int, InjectionFinding]],
    confirm: InjectionConfirmer,
    document_id: uuid.UUID,
) -> tuple[list[Chunk], list[tuple[int, InjectionFinding]]]:
    """S5.3 — a second opinion on each flagged chunk, and the partition that survives it.

    `kept` is rebuilt from the whole chunk list rather than by moving released chunks back
    into the first partition's list, so the corpus keeps document order however many are
    released. Order is not cosmetic here: a chunk carries the pages it came from, and a
    reviewer reading two retrieved chunks expects the earlier page first.

    Reviews run one after another, not under `gather`. The expected number on an honest
    upload is zero (ADR-0049 measured 351 real chunks flagging none), so there is no latency
    to win, and a poisoned document is exactly where a burst of concurrent calls to the
    cheap model would be the wrong reflex.
    """
    confirmed: list[tuple[int, InjectionFinding]] = []
    for number, finding in suspected:
        if await confirm(chunks[number - 1].text, finding.signals):
            confirmed.append((number, finding))
            continue
        logger.info(
            "document %s chunk %d released by review: %s",
            document_id,
            number,
            released(finding),
        )
    withheld = {number for number, _ in confirmed}
    kept = [chunk for number, chunk in enumerate(chunks, start=1) if number not in withheld]
    return kept, confirmed
