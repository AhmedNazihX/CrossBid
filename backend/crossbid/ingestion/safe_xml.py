"""S2.5.1 — the one place this repository parses XML that a bidder uploaded.

**Why this module exists at all.** `xml.etree` is not safe against a hostile document, and
the usual answer — `defusedxml` — is *not installed here*, so it could not be used: adding a
dependency is a decision for the repository's owner (CLAUDE.md), not something a story
sneaks in. The defence is therefore written out below, and it is written once, so that the
ESPD reader and the upload boundary cannot each get it half right.

What the attacks are, and what answers each:

* **Entity expansion — "billion laughs", quadratic blowup.** A document declares an entity
  in terms of ten copies of another and the parser expands three gigabytes out of one
  kilobyte. Entities can only be declared in a **DTD**, so the answer is to refuse a
  document type declaration outright: `StartDoctypeDeclHandler` fires *before* the internal
  subset is read, and raising there means no entity is ever declared, let alone expanded.
* **XXE — external entity and external DTD.** `<!ENTITY xxe SYSTEM "file:///etc/passwd">`
  turns a parser into a file-read primitive, and a `SYSTEM` DTD turns it into an outbound
  HTTP client. Python has not resolved external general entities by default since 3.7.1,
  but "by default" is a setting somebody can change; the DOCTYPE refusal above closes the
  declaration site itself, which is a stronger statement than trusting the default.
* **Depth.** The one payload the DOCTYPE ban does not answer: a document nested a hundred
  thousand elements deep builds a tree whose *deallocation* recurses in C. The preflight
  counts depth and stops the parse at `max_depth`, before the tree is built.
* **Size.** Checked first, so a payload over the cap is never handed to a parser at all.

**How the two passes fit together.** The preflight uses `xml.parsers.expat` directly, which
is the only way to install the handlers above — the C `ElementTree` parser does not expose
its expat parser (the attribute defusedxml reaches for is gone in this Python). The preflight
builds no tree: it reads the document, refuses a DOCTYPE, counts depth, and returns. Only
then is the same immutable `bytes` object handed to `ET.fromstring`, which by then cannot
meet an entity declaration, because the preflight proved there is no DTD. Two passes over a
150 KB form is not a cost worth optimising away.

**Residual risk, stated rather than implied.** Parsing is still linear work on attacker-sized
input inside the request or a background task — the size cap is what bounds it. A document
under the cap may still hold a very large number of small elements (memory, bounded by the
cap) or one enormous attribute value (expat's own limits apply). Namespace and attribute
handling are expat's, not ours. And the caller still owns *meaning*: this module returns a
tree, never a promise that the tree is an ESPD request, which is `ingestion/espd.py`'s job.
"""

from __future__ import annotations

# Both imports are the standard library's XML machinery, used deliberately and only from
# here; the module docstring says what is done to make that safe.
import xml.etree.ElementTree as ET
from typing import Final
from xml.parsers import expat

MAX_XML_BYTES: Final = 4 * 1024 * 1024
"""Four megabytes. The French fixture's ESPD request is 145 KB and carries 30 criteria with
their full requirement groups, so this admits a form an order of magnitude larger than any
real one while keeping the parse bounded. The upload route's own 50 MB cap is about PDFs."""

MAX_XML_DEPTH: Final = 40
"""The ESPD schema nests six deep (`ESPDRequest → Criterion → RequirementGroup →
RequirementGroup → Requirement → ID`). Forty leaves room for a deeply grouped form and
still refuses the nesting bomb, which needs thousands of levels to hurt."""


class XmlRejectedError(ValueError):
    """The bytes were not parsed: too big, too deep, not well-formed, or carrying a DTD.

    One exception for all four because every caller does the same thing with them — answer
    "this file is not an ESPD request" — and because a type that separated "hostile" from
    "malformed" would invite a caller to treat one of them as recoverable. The message says
    which it was, and it never quotes the document: the document is untrusted input, and an
    error built from untrusted input is how untrusted input escapes (ADR-0008).
    """


def parse_xml(
    data: bytes, *, max_bytes: int = MAX_XML_BYTES, max_depth: int = MAX_XML_DEPTH
) -> ET.Element:
    """`data` as an element tree, or `XmlRejectedError` naming what was wrong with it.

    The caps are arguments rather than constants read inside, so a caller with a smaller
    document can say so; the defaults are what the ESPD reader uses.
    """
    if len(data) > max_bytes:
        raise XmlRejectedError(
            f"the document is larger than the {max_bytes} byte limit for XML uploads"
        )
    if not data.strip():
        raise XmlRejectedError("the document is empty")

    _preflight(data, max_depth=max_depth)
    try:
        # Safe by construction: `_preflight` has just proven this exact bytes object
        # declares no DTD, so no entity can be declared, let alone expanded.
        return ET.fromstring(data)  # noqa: S314 — see the module docstring
    except ET.ParseError as exc:  # pragma: no cover - unreachable after the preflight
        raise XmlRejectedError("the document is not well-formed XML") from exc


def _preflight(data: bytes, *, max_depth: int) -> None:
    """Read `data` once with expat, building nothing, and refuse what must not be parsed.

    The handlers are the whole point. `StartDoctypeDeclHandler` is the entity defence — it
    fires before the internal subset, so raising from it means no `<!ENTITY>` is ever seen —
    and the element handlers are the depth defence. Nothing else is installed: with the
    DOCTYPE refused, an entity declaration handler could never fire, and a handler that can
    never fire is a claim a reader would have to verify for themselves.
    """
    depth = 0

    def start_doctype(
        name: str, system_id: str | None, public_id: str | None, has_internal_subset: bool
    ) -> None:
        raise XmlRejectedError(
            "the document carries a document type declaration; these are refused because a "
            "DTD is where entity-expansion and external-entity attacks are written"
        )

    def start_element(name: str, attributes: dict[str, str]) -> None:
        nonlocal depth
        depth += 1
        if depth > max_depth:
            raise XmlRejectedError(
                f"the document is nested more than {max_depth} elements deep"
            )

    def end_element(name: str) -> None:
        nonlocal depth
        depth -= 1

    parser = expat.ParserCreate()
    parser.StartDoctypeDeclHandler = start_doctype
    parser.StartElementHandler = start_element
    parser.EndElementHandler = end_element
    try:
        parser.Parse(data, True)
    except expat.ExpatError as exc:
        raise XmlRejectedError("the document is not well-formed XML") from exc
