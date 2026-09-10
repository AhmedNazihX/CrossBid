"""S1.1.1 + S1.1.3 — build the committed eCertis cache and the criterion enum.

Fetches the EU criterion list and the German and French evidence lists from eCertis, writes
them under `crossbid/reference/data/ecertis/`, and regenerates
`crossbid/models/ecertis_criteria.py` from the criterion list.

    uv run python scripts/build_ecertis_cache.py                 # fetch, write, verify
    uv run python scripts/build_ecertis_cache.py --countries de,fr,nl
    uv run python scripts/build_ecertis_cache.py --check          # verify only, no network

**A second run must change nothing.** Everything that could differ between two runs is
pinned: keys are sorted, every list has an explicit sort key, the indent is fixed, the
file ends in one newline, `lang=en` is sent rather than trusting a server default, and
`source_date` is derived from a SHA-256 of the content instead of from the clock — it only
advances when eCertis actually says something new. Prove it with

    uv run python scripts/build_ecertis_cache.py && shasum crossbid/reference/data/ecertis/*
    uv run python scripts/build_ecertis_cache.py && shasum crossbid/reference/data/ecertis/*

eCertis answers `200` with an empty body now and then. That is retried hard, and a
criterion that stays silent is recorded as "no evidence for this country" — a normal
outcome, not a failure. What is *not* tolerated is a country losing evidence it had in the
committed file: the script refuses to write and asks for `--allow-shrink`, so a bad
afternoon at the Commission cannot quietly empty the cache.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import textwrap
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    # `[tool.uv] package = false`, so `crossbid` is importable only via the project root.
    sys.path.insert(0, str(BACKEND_DIR))

from pydantic import (  # noqa: E402  (after the sys.path fix)
    BaseModel,
    ValidationError,
    create_model,
)

from crossbid.reference.ecertis_client import (  # noqa: E402  (after the sys.path fix)
    ECERTIS_BASE_URL,
    EcertisRestClient,
    EcertisUnavailableError,
    canonical_json,
    content_hash,
    criteria_path,
    evidence_path,
)
from crossbid.reference.ecertis_schema import (  # noqa: E402  (after the sys.path fix)
    CACHE_SCHEMA_VERSION,
    ECERTIS_SPEC_VERSION,
    CachedCriterion,
    CachedCriterionEvidence,
    CriteriaCache,
    EvidenceCache,
)

GENERATED_ENUM_PATH = BACKEND_DIR / "crossbid" / "models" / "ecertis_criteria.py"
GENERATOR_NAME = "scripts/build_ecertis_cache.py"
DEFAULT_COUNTRIES = ("de", "fr")

MIN_ANSWERING_FRACTION = 0.5
"""Fewer answering criteria than this and the country is a failed fetch, not a sparse one.

Measured on 2026-09-10: DE answers for 55 of 56 criteria, FR for 39 — genuinely sparse, not
broken, since the silence is reproducible. Half is comfortably below FR's 0.70 while still
catching a service-wide outage on a country that has no committed file to compare against.
"""

MAX_LINE_LENGTH = 96  # ruff's line-length; the generated file has to pass `ruff format`.
INDENT_STEP = 4
NAMES_INDENT = 8  # the dict literal sits inside `MappingProxyType(` inside the module.
UNKNOWN_ID_PROBE = "iso-27001"
"""Not an eCertis criterion, and deliberately the kind of thing an LLM would invent."""


@dataclass(frozen=True)
class WriteOutcome:
    """What one cache or generated file did. Nothing here mutates its inputs."""

    path: Path
    source_date: str
    changed: bool
    size_bytes: int


def _today() -> str:
    return datetime.now(tz=UTC).date().isoformat()


def _read_existing(path: Path) -> dict[str, Any] | None:
    """The committed file as-is, or `None` if it is absent or no longer valid JSON."""
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_cache(path: Path, body: Mapping[str, Any], model: type[BaseModel]) -> WriteOutcome:
    """Add provenance, validate, and write canonically.

    `source_date` is carried over untouched when the content hashes the same as the file
    already on disk. That is the whole idempotence trick.
    """
    digest = content_hash(body)
    previous = _read_existing(path)
    unchanged = previous is not None and content_hash(previous) == digest
    # `source_date` is outside the hash, so a hash match does not guarantee it is present.
    carried = str(previous.get("source_date") or "") if unchanged and previous else ""
    source_date = carried or _today()

    payload = {**body, "source_date": source_date, "content_sha256": digest}
    try:
        model.model_validate(payload)
    except ValidationError as err:
        raise SystemExit(
            f"refusing to write {path}: it does not match {model.__name__}: {err}"
        ) from err

    text = canonical_json(payload)
    changed = not path.is_file() or path.read_text(encoding="utf-8") != text
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return WriteOutcome(path, source_date, changed, len(text.encode("utf-8")))


# ------------------------------------------------------------------------------ fetching


def _fetch_criteria(client: EcertisRestClient) -> tuple[CachedCriterion, ...]:
    criteria = client.fetch_criteria()
    print(f"  criteria           {len(criteria)} EU-level criteria")
    return criteria


def _fetch_country(
    client: EcertisRestClient, criteria: Sequence[CachedCriterion], country: str
) -> tuple[CachedCriterionEvidence, ...]:
    """One request per criterion. Silent criteria are counted, not raised."""
    rows: list[CachedCriterionEvidence] = []
    silent: list[str] = []
    for index, criterion in enumerate(criteria, start=1):
        row, answered = client.fetch_evidence(criterion, country)
        if not answered:
            silent.append(criterion.name)
        rows.append(row)
        print(f"\r  evidence_{country}        {index}/{len(criteria)}", end="", flush=True)
    print()

    answered = len(criteria) - len(silent)
    if criteria and answered < MIN_ANSWERING_FRACTION * len(criteria):
        raise EcertisUnavailableError(
            f"only {answered} of {len(criteria)} criteria answered for {country!r}; "
            f"that is below {MIN_ANSWERING_FRACTION:.0%}, so the fetch failed rather than "
            f"the country being sparse"
        )
    if silent:
        print(f"    {len(silent)} criteria returned an empty body after retries:")
        for name in sorted(silent):
            print(f"      - {name}")
    return tuple(sorted(rows, key=lambda r: r.criterion_id))


def _evidence_count(rows: Iterable[Mapping[str, Any]]) -> int:
    return sum(
        len(sub.get("evidences", [])) for row in rows for sub in row.get("sub_criteria", [])
    )


def _shrunk_criteria(path: Path, fresh: Sequence[CachedCriterionEvidence]) -> list[str]:
    """Criterion names that had evidence in the committed file and have none now."""
    previous = _read_existing(path)
    if previous is None:
        return []
    before = {
        str(row.get("criterion_id")): _evidence_count([row])
        for row in previous.get("criteria", [])
        if isinstance(row, dict)
    }
    return sorted(
        row.criterion_name
        for row in fresh
        if before.get(row.criterion_id, 0) > 0
        and not any(sub.evidences for sub in row.sub_criteria)
    )


# ---------------------------------------------------------------------------- code gen


def _dict_entry(key: str, value: str, indent: int) -> list[str]:
    """One `"id": "name",` entry, parenthesised across lines only when it is too long.

    Emitted in the exact layout ruff-format would choose, so `ruff format --check` passes
    on the generated file without the generator having to shell out to ruff.
    """
    pad = " " * indent
    single = f"{pad}{json.dumps(key)}: {json.dumps(value)},"
    if len(single) <= MAX_LINE_LENGTH:
        return [single]
    inner = " " * (indent + INDENT_STEP)
    # Room for the two quotes, the continuation space, and the indent itself.
    parts = textwrap.wrap(value, width=MAX_LINE_LENGTH - len(inner) - 3)
    body = [
        f"{inner}{json.dumps(part if i == len(parts) - 1 else part + ' ')}"
        for i, part in enumerate(parts)
    ]
    return [f"{pad}{json.dumps(key)}: (", *body, f"{pad}),"]


def _render_enum(criteria: Sequence[CachedCriterion], source_date: str) -> str:
    ids = [criterion.id for criterion in criteria]
    literal = "\n".join(f"    {json.dumps(criterion_id)}," for criterion_id in ids)
    names = "\n".join(
        line
        for criterion in criteria
        for line in _dict_entry(criterion.id, criterion.name, NAMES_INDENT)
    )
    return f'''"""GENERATED FILE — do not hand-edit.

Written by `{GENERATOR_NAME}` from `crossbid/reference/data/ecertis/criteria.json`
(eCertis REST, spec v{ECERTIS_SPEC_VERSION}). Regenerate with

    uv run python {GENERATOR_NAME}

Any manual change is lost on the next run, and `--check` fails in the meantime.

These are the **EU-level** ESPD criterion ids. eCertis also issues a separate UUID per
country for the same criterion (`criteria?nationalEntity=de` returns those), but those ids
mean nothing outside their own country, so they are useless as an extraction enum for a
cross-border tool. The national ids and their evidence live in
`crossbid/reference/data/ecertis/evidence_*.json`, keyed on the ids below.

`models/` imports nothing else from `crossbid`, which is why this enum is generated into
the contract layer rather than read out of `reference/` at import time.

Source date: {source_date} · {len(ids)} criteria
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, Literal

EcertisCriterionId = Literal[
{literal}
]
"""Every criterion eCertis knows. An extraction schema typed on this rejects anything else."""

CRITERION_NAMES: Final[Mapping[EcertisCriterionId, str]] = MappingProxyType(
    {{
{names}
    }}
)
"""Criterion id to its English ESPD name, for prompts and for the requirement table."""

CRITERION_IDS: Final[tuple[EcertisCriterionId, ...]] = tuple(CRITERION_NAMES)
"""The same ids as a tuple, in the order they appear above (sorted by id)."""
'''


def _write_enum(criteria: Sequence[CachedCriterion], source_date: str) -> WriteOutcome:
    text = _render_enum(criteria, source_date)
    path = GENERATED_ENUM_PATH
    changed = not path.is_file() or path.read_text(encoding="utf-8") != text
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return WriteOutcome(path, source_date, changed, len(text.encode("utf-8")))


# ---------------------------------------------------------------------------- verifying


def _row_evidence_count(row: CachedCriterionEvidence) -> int:
    return sum(len(sub.evidences) for sub in row.sub_criteria)


def _first_evidence_name(row: CachedCriterionEvidence) -> str:
    for sub in row.sub_criteria:
        for evidence in sub.evidences:
            return evidence.name
    return ""


def _verify(countries: Sequence[str]) -> None:
    """S1.1.3's acceptance criterion, asserted rather than assumed. No network.

    The cache loader is imported fresh so the hash check in it runs against what was just
    written, and the generated module is reloaded in case this process imported an older
    copy.
    """
    from crossbid.reference import ecertis_client

    ecertis_client.clear_caches()
    importlib.invalidate_caches()
    try:
        enum_module = importlib.import_module("crossbid.models.ecertis_criteria")
    except ModuleNotFoundError as err:
        raise SystemExit(
            f"{GENERATED_ENUM_PATH} has not been generated yet. "
            f"Run `uv run python {GENERATOR_NAME}` without --check first."
        ) from err
    enum_module = importlib.reload(enum_module)

    cached = ecertis_client.load_criteria()
    cached_ids = {criterion.id for criterion in cached.criteria}
    if set(enum_module.CRITERION_IDS) != cached_ids:
        raise SystemExit("the generated Literal does not match criteria.json")
    if dict(enum_module.CRITERION_NAMES) != {c.id: c.name for c in cached.criteria}:
        raise SystemExit("CRITERION_NAMES does not match criteria.json")

    # `create_model` rather than a nested `class`: `from __future__ import annotations`
    # would turn the annotation into a string pydantic cannot resolve from a local name.
    probe = create_model(
        "ExtractionProbe",  # stand-in for Requirement.ecertis_criterion_id (S0.4.1)
        ecertis_criterion_id=(enum_module.EcertisCriterionId, ...),
    )

    known = sorted(cached_ids)[0]
    accepted = probe(ecertis_criterion_id=known)
    try:
        probe(ecertis_criterion_id=UNKNOWN_ID_PROBE)
    except ValidationError as err:
        rejected = err.errors()[0]["msg"]
    else:
        raise SystemExit(f"the Literal accepted {UNKNOWN_ID_PROBE!r}; it must not")

    print(f"\n  enum matches cache   {len(cached_ids)} ids, {len(cached.criteria)} names")
    print(
        f"  accepts real id      {accepted.ecertis_criterion_id} "
        f"({enum_module.CRITERION_NAMES[known]})"
    )
    print(f"  rejects {UNKNOWN_ID_PROBE!r:<12} ValidationError: {rejected[:88]}")

    for country in countries:
        evidence = ecertis_client.load_evidence(country)
        if {row.criterion_id for row in evidence.criteria} != cached_ids:
            raise SystemExit(f"evidence_{country}.json is not keyed on the criterion list")
        if ecertis_client.find_evidence(known, country) is None:
            raise SystemExit(f"evidence_{country}.json has no row for criterion {known}")
        if ecertis_client.find_evidence(UNKNOWN_ID_PROBE, country) is not None:
            raise SystemExit(f"evidence_{country}.json answered for {UNKNOWN_ID_PROBE!r}")

        subs = sum(len(row.sub_criteria) for row in evidence.criteria)
        docs = sum(len(sub.evidences) for row in evidence.criteria for sub in row.sub_criteria)
        silent = sum(1 for row in evidence.criteria if not row.sub_criteria)
        richest = max(evidence.criteria, key=lambda row: _row_evidence_count(row))
        print(
            f"  evidence_{country}          {len(evidence.criteria)} criteria "
            f"({silent} with no national entry), {subs} sub-criteria, {docs} evidences"
        )
        print(
            f"    e.g. {richest.criterion_name!r} -> "
            f"{_row_evidence_count(richest)} evidences, first is "
            f"{_first_evidence_name(richest)!r}"
        )


# --------------------------------------------------------------------------------- main


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--countries",
        default=",".join(DEFAULT_COUNTRIES),
        help=f"comma-separated ISO-3166 alpha-2 codes (default: {','.join(DEFAULT_COUNTRIES)})",
    )
    parser.add_argument(
        "--check", action="store_true", help="verify the committed cache and enum; no network"
    )
    parser.add_argument(
        "--allow-shrink",
        action="store_true",
        help="write even if a criterion lost all its evidence since the last build",
    )
    return parser.parse_args(argv)


def _build(countries: Sequence[str], *, allow_shrink: bool) -> list[WriteOutcome]:
    header = {
        "source": ECERTIS_BASE_URL,
        "ecertis_spec_version": ECERTIS_SPEC_VERSION,
        "schema_version": CACHE_SCHEMA_VERSION,
    }
    outcomes: list[WriteOutcome] = []
    with EcertisRestClient() as client:
        criteria = _fetch_criteria(client)
        outcomes.append(
            _write_cache(
                criteria_path(),
                {**header, "criteria": [c.model_dump(mode="json") for c in criteria]},
                CriteriaCache,
            )
        )
        for country in countries:
            rows = _fetch_country(client, criteria, country)
            path = evidence_path(country)
            if (shrunk := _shrunk_criteria(path, rows)) and not allow_shrink:
                raise SystemExit(
                    f"refusing to write {path}: {len(shrunk)} criteria lost all their "
                    f"evidence ({', '.join(shrunk[:3])}...). eCertis is probably flaky — "
                    f"re-run, or pass --allow-shrink if the loss is real."
                )
            outcomes.append(
                _write_cache(
                    path,
                    {
                        **header,
                        "country": country,
                        "criteria": [row.model_dump(mode="json") for row in rows],
                    },
                    EvidenceCache,
                )
            )
    criteria_source_date = outcomes[0].source_date
    outcomes.append(_write_enum(criteria, criteria_source_date))
    return outcomes


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    requested = (code.strip().lower() for code in args.countries.split(","))
    countries = tuple(code for code in requested if code)
    if not countries:
        raise SystemExit("--countries needs at least one code")

    print(f"eCertis cache · {ECERTIS_BASE_URL} · spec v{ECERTIS_SPEC_VERSION}")
    if args.check:
        print("  --check: no network, verifying the committed files")
    else:
        print(f"  countries: {', '.join(countries)}")
        try:
            outcomes = _build(countries, allow_shrink=args.allow_shrink)
        except EcertisUnavailableError as err:
            print(f"\neCertis is not usable right now: {err}", file=sys.stderr)
            return 1
        print()
        for outcome in outcomes:
            state = "written" if outcome.changed else "unchanged"
            rel = str(outcome.path.relative_to(BACKEND_DIR))
            print(f"  {state:<9} {rel:<52} {outcome.size_bytes:>8,} B  {outcome.source_date}")

    _verify(countries)
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
