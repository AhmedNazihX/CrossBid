"""S3.1.1 — the `requirements` projection: extraction's rows, written once per node run.

Written by the graph the moment `extract_reqs` returns and read by `GET /bids/{id}`, so the
poller shows the list the instant the bid parks at `awaiting_review`. The insert is an
**upsert on `id`**: a requirement's id is a `uuid5` over bid, document, page and quote
(`extract_reqs.REQUIREMENT_ID_NAMESPACE`), so a run that resumes after a crash and re-runs
extraction updates the same rows instead of doubling them. That is the property the
"restart mid-run resumes" criterion depends on at this table.

Every statement carries `company_id` in its text (ADR-0011); `SCOPED_STATEMENTS` lets a test
assert it. The connection protocol is `readmodel.bids.ConnectionSource`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final, LiteralString

from psycopg.types.json import Jsonb

from crossbid.models.requirement import Requirement, Threshold
from crossbid.readmodel.bids import ConnectionSource

UPSERT_REQUIREMENT: Final[LiteralString] = """
insert into requirements (
    id, bid_id, company_id, category, kind, stage, checkable, source_text, source_lang,
    document_name, page, translation, ecertis_criterion_id, threshold, deadline
) values (
    %(id)s, %(bid_id)s, %(company_id)s, %(category)s, %(kind)s, %(stage)s, %(checkable)s,
    %(source_text)s, %(source_lang)s, %(document_name)s, %(page)s, %(translation)s,
    %(ecertis_criterion_id)s, %(threshold)s, %(deadline)s
)
on conflict (id) do update set
    category = excluded.category,
    kind = excluded.kind,
    stage = excluded.stage,
    checkable = excluded.checkable,
    source_text = excluded.source_text,
    source_lang = excluded.source_lang,
    document_name = excluded.document_name,
    page = excluded.page,
    translation = excluded.translation,
    ecertis_criterion_id = excluded.ecertis_criterion_id,
    threshold = excluded.threshold,
    deadline = excluded.deadline
where requirements.company_id = %(company_id)s
"""

SELECT_REQUIREMENTS: Final[LiteralString] = """
select id, bid_id, category, kind, stage, checkable, source_text, source_lang, document_name,
       page, translation, ecertis_criterion_id, threshold, deadline
from requirements
where company_id = %(company_id)s and bid_id = %(bid_id)s
order by document_name, page, created_at
"""

SCOPED_STATEMENTS: Final[tuple[LiteralString, ...]] = (UPSERT_REQUIREMENT, SELECT_REQUIREMENTS)


async def write_requirements(
    db: ConnectionSource, *, company_id: str, rows: Sequence[Requirement]
) -> int:
    """Upsert `rows` for `company_id` and return how many were sent.

    One `executemany` rather than a statement per row: 238 rows (ADR-0003) against a
    Frankfurt database is 238 round trips otherwise, on the critical path to
    `awaiting_review`.
    """
    if not rows:
        return 0
    params = [_params(row, company_id) for row in rows]
    async with db.connection() as conn, conn.cursor() as cursor:
        await cursor.executemany(UPSERT_REQUIREMENT, params)
    return len(params)


async def fetch_requirements(
    db: ConnectionSource, *, company_id: str, bid_id: str
) -> list[Requirement]:
    """The bid's requirements in document-and-page order, re-validated on the way out."""
    async with db.connection() as conn:
        records = await (
            await conn.execute(
                SELECT_REQUIREMENTS, {"company_id": company_id, "bid_id": bid_id}
            )
        ).fetchall()
    return [_requirement(record) for record in records]


def _params(row: Requirement, company_id: str) -> dict[str, Any]:
    threshold = None if row.threshold is None else Jsonb(row.threshold.model_dump(mode="json"))
    return {
        "id": row.id,
        "bid_id": row.bid_id,
        "company_id": company_id,
        "category": row.category.value,
        "kind": row.kind.value,
        "stage": row.stage.value,
        "checkable": row.checkable.value,
        "source_text": row.source_text,
        "source_lang": row.source_lang,
        "document_name": row.document_name,
        "page": row.page,
        "translation": row.translation,
        "ecertis_criterion_id": row.ecertis_criterion_id,
        "threshold": threshold,
        "deadline": row.deadline,
    }


def _requirement(record: Mapping[str, Any]) -> Requirement:
    """A row back into the contract. `Requirement` re-validates: the table is external data."""
    threshold = record.get("threshold")
    criterion = record.get("ecertis_criterion_id")
    return Requirement.model_validate(
        {
            "id": str(record["id"]),
            "bid_id": str(record["bid_id"]),
            "category": record["category"],
            "kind": record["kind"],
            "stage": record["stage"],
            "checkable": record["checkable"],
            "source_text": record["source_text"],
            "source_lang": record["source_lang"],
            "document_name": record["document_name"],
            "page": record["page"],
            "translation": record.get("translation"),
            "ecertis_criterion_id": None if criterion is None else str(criterion),
            "threshold": None if threshold is None else Threshold.model_validate(threshold),
            "deadline": record.get("deadline"),
        }
    )
