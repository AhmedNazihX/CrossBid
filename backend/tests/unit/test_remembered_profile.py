"""`RememberedProfile` — the read that makes `profile/{company_id}` memory rather than a copy.

The audit finding this closes (H9) was that the namespace had no reader at all: the company
form and the demo seed wrote it, `routers/companies.py` said in its docstring that the agent
reasons from it, and both nodes that want the bidder's facts went to Postgres. These tests
pin the two halves of the fix — the memory answers first, and the row answers when the memory
cannot — and the failure modes in between, each of which has to end in a profile rather than
in a raise, because a run that cannot name its bidder checks a pack against nobody.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from crossbid.memory.profile import (
    PROFILE_STORE_KEY,
    RememberedProfile,
    profile_namespace,
)
from crossbid.models import CompanyProfile, LegalForm
from crossbid.readmodel.companies import CompanyReadModelError

pytestmark = pytest.mark.anyio

COMPANY = uuid.UUID("11111111-1111-4111-8111-111111111111")


def profile(name: str = "Beispiel IT Services GmbH", country: str = "de") -> CompanyProfile:
    return CompanyProfile(name=name, country=country, legal_form=LegalForm.GMBH)


class StoredItem:
    """What `BaseStore.aget` answers with: the document under `.value`."""

    def __init__(self, value: Any) -> None:
        self.value = value


class FakeStore:
    """The slice of `BaseStore` the memory uses, with a failure per call it can raise."""

    def __init__(
        self,
        items: dict[tuple[tuple[str, ...], str], Any] | None = None,
        *,
        get_error: Exception | None = None,
        put_error: Exception | None = None,
    ) -> None:
        self.items = dict(items or {})
        self.get_error = get_error
        self.put_error = put_error
        self.puts: list[tuple[tuple[str, ...], str, Any]] = []

    async def aget(self, namespace: tuple[str, ...], key: str) -> StoredItem | None:
        if self.get_error is not None:
            raise self.get_error
        if (namespace, key) not in self.items:
            return None
        return StoredItem(self.items[(namespace, key)])

    async def aput(self, namespace: tuple[str, ...], key: str, value: Any) -> None:
        self.puts.append((namespace, key, value))
        if self.put_error is not None:
            raise self.put_error
        self.items[(namespace, key)] = value


class FakeRow:
    """The slice of `CompaniesReadModel` the memory falls back to."""

    def __init__(
        self, answer: CompanyProfile | None = None, *, error: Exception | None = None
    ) -> None:
        self.answer = answer
        self.error = error
        self.asked: list[uuid.UUID] = []

    async def get(self, *, company_id: uuid.UUID) -> CompanyProfile | None:
        self.asked.append(company_id)
        if self.error is not None:
            raise self.error
        return self.answer


def remembering(value: Any) -> FakeStore:
    return FakeStore({(profile_namespace(COMPANY), PROFILE_STORE_KEY): value})


# ------------------------------------------------------------------ the memory answers


async def test_a_remembered_profile_is_answered_without_reading_the_row() -> None:
    """The point of the namespace: the agent's facts come from the agent's memory."""
    remembered = profile(name="Erinnerte GmbH")
    row = FakeRow(profile(name="Zeilen GmbH"))

    answer = await RememberedProfile(
        remembering(remembered.model_dump(mode="json")),  # type: ignore[arg-type]
        row,
    ).get(company_id=COMPANY)

    assert answer == remembered
    assert row.asked == []


async def test_the_memory_is_read_under_this_company_and_no_other() -> None:
    store = remembering(profile().model_dump(mode="json"))
    other = uuid.UUID("22222222-2222-4222-8222-222222222222")
    row = FakeRow(profile(name="Zeilen GmbH"))

    answer = await RememberedProfile(store, row).get(company_id=other)  # type: ignore[arg-type]

    assert answer == row.answer
    assert row.asked == [other]


# ---------------------------------------------------------------- the row answers behind it


async def test_an_empty_namespace_falls_back_to_the_row_and_repairs_the_memory() -> None:
    """Every company saved before this shipped has a row and no memory of it."""
    store = FakeStore()
    row = FakeRow(profile())

    answer = await RememberedProfile(store, row).get(company_id=COMPANY)  # type: ignore[arg-type]

    assert answer == row.answer
    assert store.items[(profile_namespace(COMPANY), PROFILE_STORE_KEY)] == (
        row.answer.model_dump(mode="json") if row.answer is not None else None
    )


async def test_a_remembered_document_that_no_longer_validates_is_replaced_by_the_row() -> None:
    """A profile shape that moved on under an item written by an older build."""
    store = remembering({"name": "Beispiel IT Services GmbH", "country": "de"})
    row = FakeRow(profile())

    answer = await RememberedProfile(store, row).get(company_id=COMPANY)  # type: ignore[arg-type]

    assert answer == row.answer
    assert store.items[
        (profile_namespace(COMPANY), PROFILE_STORE_KEY)
    ] == row.answer.model_dump(mode="json")


async def test_a_store_that_cannot_be_read_falls_back_rather_than_failing_the_run() -> None:
    store = FakeStore(get_error=OSError("connection pool exhausted"))
    row = FakeRow(profile())

    answer = await RememberedProfile(store, row).get(company_id=COMPANY)  # type: ignore[arg-type]

    assert answer == row.answer


async def test_a_repair_that_cannot_be_written_still_answers_with_the_row() -> None:
    """The repair is a courtesy. Failing it must not cost the caller its answer."""
    store = FakeStore(put_error=OSError("connection pool exhausted"))
    row = FakeRow(profile())

    answer = await RememberedProfile(store, row).get(company_id=COMPANY)  # type: ignore[arg-type]

    assert answer == row.answer
    assert len(store.puts) == 1


async def test_a_company_with_neither_memory_nor_row_is_none_and_writes_nothing() -> None:
    store = FakeStore()
    row = FakeRow(None)

    answer = await RememberedProfile(store, row).get(company_id=COMPANY)  # type: ignore[arg-type]

    assert answer is None
    assert store.puts == []


async def test_a_row_that_cannot_be_read_still_raises_through_the_memory() -> None:
    """The nodes catch `CompanyReadModelError` themselves; the memory must not eat it."""
    store = FakeStore()
    row = FakeRow(error=CompanyReadModelError("the profile jsonb drifted"))

    with pytest.raises(CompanyReadModelError):
        await RememberedProfile(store, row).get(company_id=COMPANY)  # type: ignore[arg-type]
