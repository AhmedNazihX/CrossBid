"""S2.4.3 — one command puts the demo GmbH in a database, ready for the walkthrough.

    make seed-demo                                          # company + profile + 10 documents
    uv run python scripts/seed_demo_company.py --dry-run     # print the plan, touch nothing

**This is a second script beside `seed_dev_company.py`, not an extension of it**, because the
two run at different moments and can afford different things. `seed_dev_company.py` inserts a
placeholder row with psycopg alone and imports nothing from `crossbid`, which is what lets it
run before the package is importable and with no application secret present. This one needs
the whole ingestion stack — Settings, a pool, Supabase Storage and OpenRouter embeddings —
because "all documents exist and are `ready`" cannot be faked with an insert. Folding it in
would have cost the older script the one property that makes it safe to run casually.

It supersedes the other for a walkthrough rather than depending on it: the company row is
created here too (`CompaniesReadModel.create`), with the pack's real facts instead of
placeholders, so `make seed-dev` is not a prerequisite. Both derive the same company id, and
a test pins them together — that id is in everyone's `.env` as `NEXT_PUBLIC_DEV_COMPANY_ID`.

Everything this file does beyond argument parsing is assembly: the seeding logic lives in
`crossbid/demo/seed.py` (covered by tests), the pack in `crossbid/demo/company.py`, and the
pipeline wiring is `ingestion.pipeline.build_pipeline` — the same factory `POST /documents`
uses, called rather than copied, so a seeded document goes through what an uploaded one does.

Costs money: embedding the pack is one OpenRouter request per batch of chunks, a fraction of
a cent for ten short PDFs. A second run spends nothing at all — see `crossbid/demo/seed.py`.

Exit codes: 0 seeded (or already seeded), 1 refused, misconfigured, or some document is not
`ready` and the printed repair is needed.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    # `[tool.uv] package = false`, so `crossbid` is importable only via the project root.
    sys.path.insert(0, str(BACKEND_DIR))

from crossbid.db import Database, DatabaseError  # noqa: E402  (after the sys.path fix)
from crossbid.demo.company import DemoPack, PackError, load_pack  # noqa: E402
from crossbid.demo.seed import (  # noqa: E402
    SeedError,
    SeedReport,
    refuse_in_production,
    render_plan,
    render_report,
    seed_demo_company,
)
from crossbid.ingestion.pipeline import build_pipeline  # noqa: E402
from crossbid.ingestion.storage import StorageError, company_document_store  # noqa: E402
from crossbid.readmodel.companies import CompaniesReadModel  # noqa: E402
from crossbid.readmodel.documents import DocumentsReadModel, ReadModelError  # noqa: E402
from crossbid.settings import Settings, SettingsError, load_settings  # noqa: E402

NO_DSN_MESSAGE = (
    "DATABASE_URL is not set, so there is nothing to seed. Copy infra/.env.example to .env "
    "at the repository root and point it at your development database."
)


async def seed(settings: Settings, pack: DemoPack) -> SeedReport:
    """Open the pool, build the production collaborators, run the seed, put it all back."""
    dsn = settings.env.database_url
    if dsn is None:
        raise SeedError(NO_DSN_MESSAGE)

    database = await Database.connect(dsn.get_secret_value())
    try:
        documents = DocumentsReadModel(database)
        pipeline = build_pipeline(
            settings,
            source=database,
            store=company_document_store(settings),
            records=documents,
        )
        try:
            return await seed_demo_company(
                companies=CompaniesReadModel(database),
                memory=database.store,
                documents=documents,
                pipeline=pipeline,
                pack=pack,
            )
        finally:
            # The embeddings client owns an HTTP pool; the API closes it in its background
            # task and this script is that task's equivalent.
            await pipeline.aclose()
    finally:
        await database.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the company, memory namespace and document ids; connect to nothing",
    )
    args = parser.parse_args(argv)

    try:
        settings = load_settings()
        refuse_in_production(settings)
        pack = load_pack()
        if args.dry_run:
            _print(render_plan(pack))
            return 0
        report = asyncio.run(seed(settings, pack))
    except (SeedError, PackError, SettingsError, StorageError, DatabaseError) as error:
        print(f"seed error: {error}", file=sys.stderr)
        return 1
    except ReadModelError as error:
        print(
            f"database error: {error}. Is the database migrated (`make migrate`)?",
            file=sys.stderr,
        )
        return 1

    _print(render_report(report))
    return 0 if report.is_complete else 1


def _print(lines: Sequence[str]) -> None:
    for line in lines:
        print(line)


if __name__ == "__main__":
    sys.exit(main())
