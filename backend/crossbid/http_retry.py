"""What is worth retrying over HTTP, in one place — the four clients used to each decide.

Crossbid talks to four third parties: TED, Frankfurter, eCertis and OpenRouter's embeddings
endpoint. Each has a retry loop, and before M21 each answered *"is this failure worth trying
again?"* differently — three of them by not asking at all. `except httpx.HTTPError` catches a
400 as readily as a connection reset, so a malformed TED query was sent twice and a 403 from a
data policy was sent three times. Retrying a permanent refusal is not merely wasteful: it
doubles the time a bidder waits to be told something that was already decided.

**What lives here is the judgement, not the loop.** The four loops stay where they are, and
they are deliberately not the same loop: eCertis reads a whole catalogue on a 60-second
timeout and can afford to sleep between attempts, while a TED search sits inside a request a
person is waiting on and is bounded at two attempts with no pause at all. Collapsing those
into one parameterised helper would have meant a function with a flag for every difference,
which is how a shared abstraction becomes harder to read than the four things it replaced.
What they *must* agree on is which failures are permanent, because that is a fact about HTTP
rather than a policy of the caller.

**Timeouts and attempt counts stay per client, under per-client names.** They were all called
`REQUEST_TIMEOUT_S` and `MAX_ATTEMPTS`, four modules deep, with four different values — and
three call sites imported one by bare name, correct only because each happened to import from
the matching module. `crossbid.tools.currency_convert` importing TED's twenty seconds for a
Frankfurter call would have been invisible. The names now say whose they are.
"""

from __future__ import annotations

from typing import Final

import httpx

RETRYABLE_STATUS_CODES: Final = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
"""The status codes a second identical request might genuinely answer differently.

Request timeout, conflict, too-early, too-many-requests, and the five hundreds. Everything
else — 400, 401, 403, 404, 422 — is the server saying the request itself is the problem, and
it will say it again. This set was `ingestion/embeddings.py`'s, the one client that had
thought about it, and it is now every client's.
"""


def is_retryable(error: httpx.HTTPError) -> bool:
    """Whether `error` is worth one more attempt.

    A transport failure — a reset connection, a DNS failure, a read timeout — is retryable by
    nature: nothing about it says the request was wrong. A response that arrived is judged on
    its status. Anything else that is an `HTTPError` but carries no response is treated as
    transport, which is the safe direction: one wasted attempt beats giving up on a blip.
    """
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in RETRYABLE_STATUS_CODES
    return True
