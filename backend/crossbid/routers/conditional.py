"""M13 — conditional GET, so a poll that changed nothing does not resend the matrix.

`GET /bids/{id}` is polled every two seconds for the whole length of a run and answers with
the bid, every requirement, every document and every matrix row each time: 144 rows on the FR
pack, 284 on the DE one. Most of those answers are identical to the one before. The route now
sends an `ETag`, the browser echoes it as `If-None-Match`, and an unchanged poll is a **304**
with no body at all.

**The tag is computed over the assembled body, deliberately, and that costs something.** The
cheaper design is a tag built from `max(updated_at)` and a row count per projection, which
would let the route answer 304 before reading the three tables. It does not work here:
`requirements` and `matrix_rows` have no `updated_at` column, and `UPSERT_MATRIX_ROW` edits in
place, so a row whose status the agent or a reviewer just changed keeps the `created_at` it
was inserted with and the count beside it does not move. A tag from those would keep saying
"unchanged" across exactly the writes a reviewer is waiting to see. Hashing the body cannot be
wrong that way — "changed" means a byte of the answer differs — and it saves the serialisation
and the transfer, which is what the finding names. Saving the reads as well needs `updated_at`
on both projections, which is a migration and its own card (ADR-0093).

**Weak, not strong.** `W/` says the tag identifies the answer semantically rather than
promising a byte-for-byte representation; anything between here and the browser may re-encode
or compress. RFC 9110 §8.8.3.
"""

from __future__ import annotations

import hashlib
from typing import Final

from pydantic import BaseModel

_DIGEST_CHARACTERS: Final = 16
"""Half a SHA-256, hex. The tag is a change detector between one client and one server, not a
signature: 64 bits is far past the point where two consecutive polls of one bid collide, and a
short header is cheaper on every one of them."""

_ANY_REPRESENTATION: Final = "*"


def etag_for(payload: BaseModel) -> str:
    """The weak entity tag for `payload` as this API would serialise it.

    Hashing `model_dump_json` rather than the response bytes keeps the tag independent of
    whatever encoding the transport chooses, and means the route can compute it before it has
    a `Response` to hold.
    """
    digest = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
    return f'W/"{digest[:_DIGEST_CHARACTERS]}"'


def is_unchanged(*, if_none_match: str | None, current: str) -> bool:
    """Whether the caller already holds `current`, per RFC 9110 §13.1.2.

    A header this cannot parse means *changed*, so the caller gets a body. It arrives from the
    network on every poll, and the failure mode of a strict reading would be a 500 on the one
    route a workspace cannot do without — where the failure mode of a lenient one is a
    response that was going to be sent anyway.
    """
    if if_none_match is None:
        return False
    candidates = [token.strip() for token in if_none_match.split(",")]
    if _ANY_REPRESENTATION in candidates:
        return True
    return current in candidates
