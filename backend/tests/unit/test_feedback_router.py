"""S4.6.3 — `POST /bids/{id}/feedback` and `GET /bids/{id}/feedback`, offline over HTTP.

The router is the real one on a bare app whose `state.settings` is the offline settings
(what `current_company` reads); the database dependency is a stand-in that is never borrowed
from, and the two read-model functions are replaced by one in-memory store scoped exactly
the way the real statements are — a rating lands only when the bid belongs to the caller and
the named row belongs to that bid.

The last group is the one that matters most. Tenant isolation is application-level
(ADR-0009), so the in-memory store proves the *route* behaves, and one further test runs the
**real** read model over `conftest`'s recording connection to prove the scope is in the SQL
the route sends rather than in the fake that stands in for it.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from crossbid.auth import DEV_COMPANY_HEADER
from crossbid.deps import get_database
from crossbid.models.review import MAX_COMMENT_CHARS
from crossbid.readmodel.feedback import FeedbackRecord, Rating
from crossbid.routers import feedback as feedback_router
from crossbid.routers.feedback import (
    NOTHING_TO_RATE_DETAIL,
    FeedbackListResponse,
    FeedbackSubmission,
    router,
)
from crossbid.settings import Settings
from tests.conftest import FakeConnectionSource

COMPANY_ID = str(uuid.UUID("11111111-1111-4111-8111-111111111111"))
OTHER_COMPANY_ID = str(uuid.UUID("22222222-2222-4222-8222-222222222222"))
BID_ID = str(uuid.UUID("33333333-3333-4333-8333-333333333333"))
ROW_ID = str(uuid.UUID("77777777-7777-4777-8777-777777777777"))
OTHER_ROW_ID = str(uuid.UUID("88888888-8888-4888-8888-888888888888"))

READ_MODEL_FUNCTIONS = ("record_feedback", "fetch_feedback")

COMMENT = "Die Bescheinigung deckt das ab — siehe Seite 2."
NOW = datetime(2026, 9, 14, 10, 30, tzinfo=UTC)


# --------------------------------------------------------------------------------- fakes


class InMemoryFeedback:
    """The two read-model functions over a list, scoped the way the statements are.

    The scope is modelled rather than assumed: `record_feedback` answers `None` — which is
    what an `insert ... select` that matched nothing returns — for a bid this company does
    not own and for a row that is not that bid's, and `fetch_feedback` filters by both.
    """

    def __init__(self) -> None:
        self.bids: dict[str, str] = {BID_ID: COMPANY_ID}
        """bid id -> the company that owns it."""
        self.rows: dict[str, str] = {ROW_ID: BID_ID}
        """matrix row id -> the bid it belongs to."""
        self.stored: list[FeedbackRecord] = []

    async def record_feedback(
        self,
        _db: object,
        *,
        company_id: str,
        bid_id: str,
        rating: Rating,
        matrix_row_id: str | None = None,
        comment: str | None = None,
    ) -> FeedbackRecord | None:
        if self.bids.get(bid_id) != company_id:
            return None
        if matrix_row_id is not None and self.rows.get(matrix_row_id) != bid_id:
            return None
        record = FeedbackRecord(
            id=len(self.stored) + 1,
            bid_id=bid_id,
            matrix_row_id=matrix_row_id,
            rating=rating,
            comment=comment,
            created_at=NOW,
        )
        self.stored.append(record)
        return record

    async def fetch_feedback(
        self, _db: object, *, company_id: str, bid_id: str
    ) -> list[FeedbackRecord]:
        if self.bids.get(bid_id) != company_id:
            return []
        latest: dict[str | None, FeedbackRecord] = {}
        for record in self.stored:
            if record.bid_id == bid_id:
                latest[record.matrix_row_id] = record
        return list(latest.values())


class FakeDatabase:
    """Handed to the read-model functions, which are fakes here; never borrowed from."""


# ------------------------------------------------------------------------------ fixtures


def build_api(settings: Settings, db: object) -> TestClient:
    """The real router on a bare app with only the database dependency replaced."""
    app = FastAPI()
    app.state.settings = settings
    app.state.db = None
    app.include_router(router)
    app.dependency_overrides[get_database] = lambda: db
    return TestClient(app)


@pytest.fixture
def records(monkeypatch: pytest.MonkeyPatch) -> InMemoryFeedback:
    store = InMemoryFeedback()
    for name in READ_MODEL_FUNCTIONS:
        monkeypatch.setattr(feedback_router, name, getattr(store, name))
    return store


@pytest.fixture
def api(offline_settings: Settings, records: InMemoryFeedback) -> Iterator[TestClient]:
    with build_api(offline_settings, FakeDatabase()) as client:
        yield client


def headers(company_id: str = COMPANY_ID) -> dict[str, str]:
    return {DEV_COMPANY_HEADER: company_id}


def rating_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {"rating": 1, "matrix_row_id": ROW_ID}
    return body | overrides


# ------------------------------------------------------------------------ registration


def test_the_feedback_routes_are_registered(client: TestClient) -> None:
    """S4.6.3 is wired; the OpenAPI schema is what `frontend/lib/api.ts` is generated from."""
    schema = client.get("/openapi.json").json()

    assert set(schema["paths"]["/bids/{bid_id}/feedback"]) == {"get", "post"}


# ------------------------------------------------------------------------------- rating


def test_a_thumb_up_on_a_row_is_stored_with_the_row_id(
    api: TestClient, records: InMemoryFeedback
) -> None:
    """The story's criterion: a thumbs rating is stored with the row it is about."""
    # Act
    response = api.post(f"/bids/{BID_ID}/feedback", json=rating_body(), headers=headers())

    # Assert
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["rating"], body["matrix_row_id"], body["bid_id"]) == (1, ROW_ID, BID_ID)
    assert [(r.rating, r.matrix_row_id) for r in records.stored] == [(Rating.UP, ROW_ID)]


def test_a_thumb_down_with_a_comment_keeps_the_correction(
    api: TestClient, records: InMemoryFeedback
) -> None:
    """The comment is the correction the story exists to keep, so it is stored verbatim."""
    # Act
    response = api.post(
        f"/bids/{BID_ID}/feedback",
        json=rating_body(rating=-1, comment=COMMENT),
        headers=headers(),
    )

    # Assert
    assert response.status_code == 201, response.text
    assert response.json()["comment"] == COMMENT
    assert records.stored[0].rating is Rating.DOWN


def test_a_rating_with_no_row_is_about_the_bids_own_answer(
    api: TestClient, records: InMemoryFeedback
) -> None:
    """`matrix_row_id` is nullable in 0001; a chat answer will use this target (F3.5)."""
    response = api.post(f"/bids/{BID_ID}/feedback", json={"rating": 1}, headers=headers())

    assert response.status_code == 201, response.text
    assert response.json()["matrix_row_id"] is None
    assert records.stored[0].matrix_row_id is None


def test_a_comment_of_nothing_but_whitespace_is_stored_as_no_comment(
    api: TestClient, records: InMemoryFeedback
) -> None:
    """ "Rated, said nothing" must be one state in the table rather than two."""
    api.post(f"/bids/{BID_ID}/feedback", json=rating_body(comment="   \n"), headers=headers())

    assert records.stored[0].comment is None


def test_rating_the_same_row_again_appends_rather_than_replacing(
    api: TestClient, records: InMemoryFeedback
) -> None:
    """The bidder's first answer is part of the record; only the *read* prefers the latest."""
    # Act
    api.post(f"/bids/{BID_ID}/feedback", json=rating_body(), headers=headers())
    api.post(f"/bids/{BID_ID}/feedback", json=rating_body(rating=-1), headers=headers())

    # Assert
    assert [record.rating for record in records.stored] == [Rating.UP, Rating.DOWN]
    listed = api.get(f"/bids/{BID_ID}/feedback", headers=headers()).json()["feedback"]
    assert [item["rating"] for item in listed] == [-1], "the screen shows the latest word"


def test_a_recorded_rating_is_logged_without_what_the_bidder_wrote(
    api: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """The comment is free text about the bidder's own tender; the log gets the fact only."""
    # Act
    with caplog.at_level(logging.INFO):
        api.post(
            f"/bids/{BID_ID}/feedback",
            json=rating_body(comment=COMMENT),
            headers=headers(),
        )

    # Assert
    assert BID_ID in caplog.text and ROW_ID in caplog.text
    assert COMMENT not in caplog.text


# ------------------------------------------------------------------------------ refusals


def test_rating_another_companys_bid_is_a_404_and_stores_nothing(
    api: TestClient, records: InMemoryFeedback
) -> None:
    """Never 403: a "forbidden" would confirm the bid exists (`routers/bids.py`'s rule)."""
    # Act
    response = api.post(
        f"/bids/{BID_ID}/feedback", json=rating_body(), headers=headers(OTHER_COMPANY_ID)
    )

    # Assert
    assert response.status_code == 404
    assert response.json()["detail"] == NOTHING_TO_RATE_DETAIL
    assert records.stored == []


def test_rating_a_row_that_belongs_to_another_bid_is_the_same_404(
    api: TestClient, records: InMemoryFeedback
) -> None:
    """The row check is what stops a caller attaching their thumb to somebody else's row."""
    # Arrange -- a real row, but not this bid's
    records.rows[OTHER_ROW_ID] = str(uuid.uuid4())

    # Act
    response = api.post(
        f"/bids/{BID_ID}/feedback",
        json=rating_body(matrix_row_id=OTHER_ROW_ID),
        headers=headers(),
    )

    # Assert
    assert response.status_code == 404
    assert records.stored == []


@pytest.mark.parametrize("rating", [0, 2, -2, "up"])
def test_a_rating_outside_the_two_the_column_stores_is_a_422(
    api: TestClient, rating: object
) -> None:
    """The check constraint allows -1 and 1; anything else must never reach Postgres."""
    response = api.post(
        f"/bids/{BID_ID}/feedback", json=rating_body(rating=rating), headers=headers()
    )

    assert response.status_code == 422
    assert [error["loc"] for error in response.json()["detail"]] == [["body", "rating"]]


def test_a_rating_with_no_thumb_at_all_is_a_422(api: TestClient) -> None:
    """A comment is optional; the thumb is the rating, so it is not."""
    response = api.post(
        f"/bids/{BID_ID}/feedback", json={"comment": COMMENT}, headers=headers()
    )

    assert response.status_code == 422


def test_an_unknown_field_is_refused_rather_than_dropped(api: TestClient) -> None:
    """`extra="forbid"`: a typo in a client must not become a silently lost rating."""
    response = api.post(
        f"/bids/{BID_ID}/feedback", json=rating_body(reason="typo"), headers=headers()
    )

    assert response.status_code == 422


def test_a_comment_longer_than_the_review_bound_is_refused(api: TestClient) -> None:
    """The same bound a reviewer's override reason carries: it is the same kind of text."""
    response = api.post(
        f"/bids/{BID_ID}/feedback",
        json=rating_body(comment="x" * (MAX_COMMENT_CHARS + 1)),
        headers=headers(),
    )

    assert response.status_code == 422


def test_a_malformed_row_id_is_refused_before_it_reaches_the_database(api: TestClient) -> None:
    """`uuid.UUID` in the request model, so a bad id is a 422 naming the field, not a 500."""
    response = api.post(
        f"/bids/{BID_ID}/feedback",
        json=rating_body(matrix_row_id="not-a-uuid"),
        headers=headers(),
    )

    assert response.status_code == 422
    assert [error["loc"] for error in response.json()["detail"]] == [["body", "matrix_row_id"]]


# ------------------------------------------------------------------------- reading back


def test_the_list_answers_what_this_company_has_rated_on_this_bid(
    api: TestClient, records: InMemoryFeedback
) -> None:
    # Arrange
    api.post(f"/bids/{BID_ID}/feedback", json=rating_body(), headers=headers())
    api.post(f"/bids/{BID_ID}/feedback", json={"rating": -1}, headers=headers())

    # Act
    body = api.get(f"/bids/{BID_ID}/feedback", headers=headers()).json()

    # Assert
    assert [(item["rating"], item["matrix_row_id"]) for item in body["feedback"]] == [
        (1, ROW_ID),
        (-1, None),
    ]
    assert records.stored[0].bid_id == BID_ID


def test_another_companys_bid_lists_nothing_rather_than_answering_404(
    api: TestClient, records: InMemoryFeedback
) -> None:
    """A 404 here would tell a caller which bid ids exist; the statement is scoped, so an
    unrelated bid simply has no ratings of theirs to show."""
    # Arrange
    api.post(f"/bids/{BID_ID}/feedback", json=rating_body(), headers=headers())

    # Act
    response = api.get(f"/bids/{BID_ID}/feedback", headers=headers(OTHER_COMPANY_ID))

    # Assert
    assert response.status_code == 200
    assert response.json() == {"feedback": []}
    assert len(records.stored) == 1


# --------------------------------------------------------------------- the scope itself


def test_the_write_is_scoped_to_the_caller_by_the_statement_itself(
    offline_settings: Settings,
) -> None:
    """The real read model over a recording connection: the scope is in the SQL, not in code.

    The fakes above model the scope; this is the test that the route actually sends it.
    """
    # Arrange
    source = FakeConnectionSource(())

    # Act
    with build_api(offline_settings, source) as api:
        api.post(f"/bids/{BID_ID}/feedback", json=rating_body(), headers=headers())

    # Assert
    assert source.only.params["company_id"] == COMPANY_ID
    assert "b.company_id = %(company_id)s" in source.only.sql
    assert "m.company_id = %(company_id)s" in source.only.sql


def test_the_read_is_scoped_to_the_caller_by_the_statement_itself(
    offline_settings: Settings,
) -> None:
    # Arrange
    source = FakeConnectionSource(())

    # Act
    with build_api(offline_settings, source) as api:
        api.get(f"/bids/{BID_ID}/feedback", headers=headers())

    # Assert
    assert source.only.params == {"company_id": COMPANY_ID, "bid_id": BID_ID}
    assert "company_id = %(company_id)s" in source.only.sql


# ------------------------------------------------------------------- the contract itself


def test_every_field_of_the_contract_is_described_for_the_generated_client() -> None:
    """`frontend/lib/api.ts` is generated from this schema; a bare field is a bare type.

    `bid_id` and `created_at` are exempt: their names already say what they hold, and a
    description restating a name is noise in every generated client that reads it.
    """
    obvious = {"bid_id", "created_at"}
    for model in (FeedbackSubmission, FeedbackListResponse, FeedbackRecord):
        for name, info in model.model_fields.items():
            if name in obvious:
                continue
            assert info.description, f"{model.__name__}.{name} has no description"
