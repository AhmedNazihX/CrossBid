"""S3.3.1 — the `matrix_rows` projection: what checking found, written lane by lane.

Written by the graph as each checking lane returns and read by `GET /bids/{id}`, so the
workspace fills in while the rest of the fan-out is still working rather than all at once at
the interrupt. The insert is an **upsert on `id`**, and the id is a `uuid5` over the
requirement id (`check_loop.MATRIX_ROW_ID_NAMESPACE`): a run that resumes after a crash and
re-checks a requirement updates its row instead of adding a second one. That matters more
here than in `requirements`, because `matrix_rows` carries a unique index on
`requirement_id` — a random id would not conflict on `id` and would then be refused by that
index, turning a resume into a failed run.

**The reviewer's columns are never written by the agent.** `reviewer_status`,
`override_reason`, `attached_doc_ids` and `reviewed_at` are left to their defaults on insert
and are *not* in the `do update set` list, so a re-check of a row a human has already
confirmed refreshes the agent's finding and leaves the human's disposition alone. S3.4.x
writes them from the review, through its own statement.

Every statement carries `company_id` in its text (ADR-0011); `SCOPED_STATEMENTS` lets a test
assert it. The connection protocol is `readmodel.bids.ConnectionSource`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final, LiteralString

from psycopg.types.json import Jsonb

from crossbid.models.matrix import MatrixRow
from crossbid.readmodel.bids import ConnectionSource

UPSERT_MATRIX_ROW: Final[LiteralString] = """
insert into matrix_rows (
    id, requirement_id, bid_id, company_id, status, evidence, ecertis_evidence,
    agent_rationale
) values (
    %(id)s, %(requirement_id)s, %(bid_id)s, %(company_id)s, %(status)s, %(evidence)s,
    %(ecertis_evidence)s, %(agent_rationale)s
)
on conflict (id) do update set
    status = excluded.status,
    evidence = excluded.evidence,
    ecertis_evidence = excluded.ecertis_evidence,
    agent_rationale = excluded.agent_rationale
where matrix_rows.company_id = %(company_id)s
"""

SELECT_MATRIX_ROWS: Final[LiteralString] = """
select m.id, m.requirement_id, m.status, m.evidence, m.ecertis_evidence, m.agent_rationale,
       m.reviewer_status, m.override_reason, m.attached_doc_ids, m.reviewed_at
from matrix_rows m
join requirements r on r.id = m.requirement_id and r.company_id = m.company_id
where m.company_id = %(company_id)s and m.bid_id = %(bid_id)s
order by r.document_name, r.page, r.created_at
"""
"""Joined to `requirements` for the ordering only: the matrix and the requirement list in the
same response then run in the same order, which is what lets the workspace put them side by
side without sorting either of them in the browser."""

SCOPED_STATEMENTS: Final[tuple[LiteralString, ...]] = (UPSERT_MATRIX_ROW, SELECT_MATRIX_ROWS)


async def write_matrix_rows(
    db: ConnectionSource, *, company_id: str, bid_id: str, rows: Sequence[MatrixRow]
) -> int:
    """Upsert `rows` for one bid of one company and return how many were sent.

    One `executemany`, as `write_requirements` is, and for the same reason: a lane holds
    dozens of rows and a statement each would be dozens of round trips to Frankfurt on the
    way to `awaiting_review`. `bid_id` is a parameter rather than a field because a
    `MatrixRow` does not carry one — it is identified by its requirement, and the bid is the
    scope the caller is writing in.
    """
    if not rows:
        return 0
    params = [_params(row, company_id=company_id, bid_id=bid_id) for row in rows]
    async with db.connection() as conn, conn.cursor() as cursor:
        await cursor.executemany(UPSERT_MATRIX_ROW, params)
    return len(params)


async def fetch_matrix_rows(
    db: ConnectionSource, *, company_id: str, bid_id: str
) -> list[MatrixRow]:
    """The bid's matrix in requirement order, re-validated on the way out."""
    async with db.connection() as conn:
        records = await (
            await conn.execute(SELECT_MATRIX_ROWS, {"company_id": company_id, "bid_id": bid_id})
        ).fetchall()
    return [_matrix_row(record) for record in records]


def _params(row: MatrixRow, *, company_id: str, bid_id: str) -> dict[str, Any]:
    ecertis = row.ecertis_evidence
    return {
        "id": row.id,
        "requirement_id": row.requirement_id,
        "bid_id": bid_id,
        "company_id": company_id,
        "status": row.status.value,
        "evidence": Jsonb([item.model_dump(mode="json") for item in row.evidence]),
        "ecertis_evidence": None if ecertis is None else Jsonb(ecertis.model_dump(mode="json")),
        "agent_rationale": row.agent_rationale,
    }


def _matrix_row(record: Mapping[str, Any]) -> MatrixRow:
    """A row back into the contract. `MatrixRow` re-validates: the table is external data,
    and its `supported` invariant is worth checking on the way out as well as in."""
    ecertis = record.get("ecertis_evidence")
    return MatrixRow.model_validate(
        {
            "id": str(record["id"]),
            "requirement_id": str(record["requirement_id"]),
            "status": record["status"],
            "evidence": list(record.get("evidence") or []),
            "ecertis_evidence": ecertis,
            "agent_rationale": record["agent_rationale"],
            "reviewer_status": record["reviewer_status"],
            "override_reason": record.get("override_reason"),
            "attached_doc_ids": [
                str(identifier) for identifier in record.get("attached_doc_ids") or ()
            ],
            "reviewed_at": record.get("reviewed_at"),
        }
    )
