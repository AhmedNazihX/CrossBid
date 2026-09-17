"""M13 — the entity tag that lets an unchanged poll answer 304.

Offline and pure. `GET /bids/{id}` is polled every two seconds for the length of a run and
answers with every requirement and every matrix row each time — 144 rows on the FR pack, 284
on the DE one — whether or not anything moved. The tag is computed over the assembled body,
so "changed" means exactly "a byte of the answer is different", which is the only definition
that cannot drift from what the browser is holding.

Why not over the rows' timestamps, which is the obvious cheaper thing: `requirements` and
`matrix_rows` have no `updated_at` column, and `UPSERT_MATRIX_ROW` edits in place, so a row
whose status a reviewer changed has the same `created_at` it always had and the same count
beside it. A tag built from those would go on saying "unchanged" across the one write the
reviewer most needs to see. See ADR-0093.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from crossbid.routers.conditional import etag_for, is_unchanged


class Payload(BaseModel):
    name: str
    rows: list[int] = []


class TestTheTag:
    def test_the_same_body_gives_the_same_tag(self) -> None:
        assert etag_for(Payload(name="a", rows=[1, 2])) == etag_for(
            Payload(name="a", rows=[1, 2])
        )

    def test_a_different_body_gives_a_different_tag(self) -> None:
        assert etag_for(Payload(name="a", rows=[1, 2])) != etag_for(
            Payload(name="a", rows=[1, 3])
        )

    def test_a_row_appended_changes_the_tag(self) -> None:
        """The run's own progress: `check_reqs` writes matrix rows one at a time."""
        assert etag_for(Payload(name="a", rows=[1])) != etag_for(Payload(name="a", rows=[1, 2]))

    def test_reordering_changes_the_tag(self) -> None:
        """The body is ordered and the browser renders it in order, so a reorder is a change
        even though the set is the same."""
        assert etag_for(Payload(name="a", rows=[1, 2])) != etag_for(
            Payload(name="a", rows=[2, 1])
        )

    def test_the_tag_is_weak_and_quoted(self) -> None:
        """RFC 9110 §8.8.3. Weak because it is a semantic identity, not a byte-for-byte
        promise about a representation that may be compressed differently on the way out."""
        # Act
        tag = etag_for(Payload(name="a"))

        # Assert
        assert tag.startswith('W/"')
        assert tag.endswith('"')

    def test_the_tag_carries_no_content(self) -> None:
        """It travels in a header a proxy may log. A tag that quoted the body would put the
        bid's own text there."""
        # Act
        tag = etag_for(Payload(name="Vergabekammer", rows=[7]))

        # Assert
        assert "Vergabekammer" not in tag


class TestTheComparison:
    def test_a_matching_tag_is_unchanged(self) -> None:
        tag = etag_for(Payload(name="a"))
        assert is_unchanged(if_none_match=tag, current=tag)

    def test_no_header_at_all_is_changed(self) -> None:
        """The first poll of a workspace holds nothing, and must get a body."""
        assert not is_unchanged(if_none_match=None, current=etag_for(Payload(name="a")))

    def test_a_stale_tag_is_changed(self) -> None:
        assert not is_unchanged(
            if_none_match=etag_for(Payload(name="a")), current=etag_for(Payload(name="b"))
        )

    def test_a_star_matches_anything(self) -> None:
        """RFC 9110 §13.1.2: `*` means "if any representation exists"."""
        assert is_unchanged(if_none_match="*", current=etag_for(Payload(name="a")))

    def test_one_of_a_list_matching_is_unchanged(self) -> None:
        """A browser that has more than one cached representation sends them comma-separated."""
        # Arrange
        current = etag_for(Payload(name="b"))
        sent = f"{etag_for(Payload(name='a'))}, {current}"

        # Act / Assert
        assert is_unchanged(if_none_match=sent, current=current)

    @pytest.mark.parametrize("sent", ['W/"", ', "", "   ", "garbage"])
    def test_a_header_that_makes_no_sense_is_changed_rather_than_an_error(
        self, sent: str
    ) -> None:
        """A malformed `If-None-Match` must cost the caller a body, never a 500: the value is
        caller-controlled and reaches this on every poll."""
        assert not is_unchanged(if_none_match=sent, current=etag_for(Payload(name="a")))

    def test_the_weak_prefix_is_not_required_to_match_by_accident(self) -> None:
        """A tag compared without its `W/` would match a strong tag of the same hash, which is
        a different thing under RFC 9110. Compare the whole token."""
        # Arrange
        weak = etag_for(Payload(name="a"))
        strong = weak.removeprefix("W/")

        # Act / Assert
        assert not is_unchanged(if_none_match=strong, current=weak)
