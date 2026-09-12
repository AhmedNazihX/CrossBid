"""A saved extraction result: what `scripts/recall.py` scores, and where it came from.

Extraction costs money. One DE-pack run is 49 model calls, $1.38 and five minutes
(ADR-0012), so the recall script cannot run one itself — it reads the rows a run already
produced. This module is that artefact's shape.

**Provenance is a field, not a filename convention.** `source` says whether the rows came
from a real model run or were built by hand, and the report prints a warning across the top
of every synthetic one. A recall figure scored against a hand-built file is not a
measurement of anything; it exercises the script. Losing that distinction is exactly how a
demonstration figure ends up quoted as a result.

**The result names its own tender.** `fixture_dir` is repo-relative from `backend/`, the same
convention `GoldenMeta` uses, and `golden_path` resolves the answer key from it. So a result
file and a golden file cannot be paired up wrongly on a command line — there is only one
path to pass.

`problems` is carried because a `NO_VERBATIM_QUOTE` problem is a row the extractor *dropped*,
which is a recall miss with a cause. A reviewer reading a miss list wants to know whether
the count of problems is 0 or 13.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from crossbid.agent.state import ExtractionProblem
from crossbid.models.requirement import Requirement

NonEmptyStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]

GOLDEN_FILENAME: Final = "golden.yaml"
JSON_INDENT: Final = 2


class ExtractionSource(StrEnum):
    """How the rows in a result file were produced.

    `LIVE_RUN` is the graph against OpenRouter on the real pack — the only kind of file whose
    recall figure is a measurement. `SYNTHETIC` is hand-built from the golden labels to
    exercise the script offline, and says so on every report it appears in.
    """

    LIVE_RUN = "live_run"
    SYNTHETIC = "synthetic"


class ExtractionMeta(BaseModel):
    """Which tender was extracted, by what, and at what cost."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fixture_dir: NonEmptyStr = Field(description="Repo-relative, from `backend/`")
    source: ExtractionSource
    produced_on: date
    method: NonEmptyStr = Field(
        description="Prose: how these rows were produced, honestly and specifically"
    )
    models: Mapping[str, str] = Field(
        default_factory=dict, description="Role -> slug, for a run that used models"
    )
    cost_usd: float | None = Field(default=None, ge=0.0, description="What OpenRouter reported")
    elapsed_seconds: float | None = Field(default=None, ge=0.0)


class ExtractionResult(BaseModel):
    """One tender's extraction output, as the recall script reads it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    meta: ExtractionMeta
    requirements: tuple[Requirement, ...]
    problems: tuple[ExtractionProblem, ...] = ()

    @property
    def fixture_name(self) -> str:
        """`de`, `fr`, `en` — the last segment of the fixture directory."""
        return PurePosixPath(self.meta.fixture_dir).name

    def golden_path(self, backend_dir: Path) -> Path:
        """The answer key for this tender, resolved from the result's own `fixture_dir`."""
        return backend_dir / self.meta.fixture_dir / GOLDEN_FILENAME


def load_extraction(path: Path) -> ExtractionResult:
    """Read one saved result, or raise `ValidationError` naming what is wrong with it."""
    return ExtractionResult.model_validate(json.loads(path.read_text(encoding="utf-8")))


def dump_extraction(result: ExtractionResult, path: Path) -> None:
    """Write a result where the recall script can read it.

    Committed as a fixture and diffed like source, so the indent is fixed and the file ends
    in exactly one newline. `mode="json"` so the dates and enums are strings rather than
    Python objects.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(result.model_dump(mode="json"), indent=JSON_INDENT, ensure_ascii=False)
    path.write_text(f"{body}\n", encoding="utf-8")
