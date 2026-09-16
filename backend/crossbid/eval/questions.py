"""S7.1 — the retrieval answer key: questions a bidder would ask, with verified answers.

**The key is derived from the golden labels rather than invented, and that is the whole
design.** S6.4 cost a day of human adjudication to turn 346 labelled requirements into an
answer key somebody had actually checked, and the lesson it taught was not "labelling is
hard" but "an unverified key makes the metric it feeds a decoration" — extraction recall was
quoted for two increments before anyone knew whether the labels were right. Inventing a
second, unverified key for retrieval would repeat exactly that.

So every question here is built from one `GoldenRequirement`, and the fields ragas scores
against come straight out of it:

- `reference` is the label's `summary` — one line of English a human verified.
- `reference_contexts` is the label's `quote` — verbatim source-language text a machine has
  already re-derived from the page it cites (`test_golden_labels.py`).
- `doc` and `page` are the citation that quote came from.

Only the **question wording** is new, and it is the one field a reviewer has to read. That is
a far smaller ask than re-deriving answers, and it is why `verified_by` gates the file rather
than being a nicety: `REPORT.md` prints whether the key it scored against was checked, the
same way the extraction report prints `labelled_by`.

**A question is not a retrieval target on its own.** The label it came from names the passage
that should be retrieved, so `ContextRecall` and `ContextPrecisionWithReference` have
something to be right or wrong about. Without that the only measurable claim is "the answer
is consistent with whatever was retrieved", which is worth measuring and is not the same
question (ADR to follow).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Final

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonEmptyStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]

QUESTION_ID_PATTERN: Final = r"^[A-Z]{2}-Q-\d{3}$"


class QuestionSetError(RuntimeError):
    """The file could not be read, or says nothing about who checked it."""


class VerificationState(StrEnum):
    """Whether a human has read the questions in this file.

    `DRAFT` is not a smaller version of `VERIFIED`; it is a different claim. A report scored
    against a draft key states that, because the alternative is a retrieval number whose
    provenance nobody can reconstruct — which is the failure this whole module is shaped to
    avoid.
    """

    DRAFT = "draft"
    HUMAN_VERIFIED = "human_verified"


class QuestionSetMeta(BaseModel):
    """Which tender these questions are about, how they were written, and who checked them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fixture_dir: NonEmptyStr = Field(description="Repo-relative, from `backend/`")
    source_language: NonEmptyStr
    bidder_language: NonEmptyStr
    derived_from: NonEmptyStr = Field(description="The answer key the references came from")
    generated_by: NonEmptyStr = Field(description="Model slug that drafted the wording")
    generated_on: date
    state: VerificationState = VerificationState.DRAFT
    verified_by: str | None = None
    verified_on: date | None = None
    method: NonEmptyStr

    @property
    def verified(self) -> bool:
        """Human-verified *and* signed.

        A state without a name is a state nobody stands behind.
        """
        return (
            self.state is VerificationState.HUMAN_VERIFIED
            and bool(self.verified_by)
            and self.verified_on is not None
        )


class RetrievalQuestion(BaseModel):
    """One question, its verified answer, and the passage that answers it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=QUESTION_ID_PATTERN)
    label_id: NonEmptyStr = Field(description="The golden label this was derived from")
    question: NonEmptyStr = Field(description="Asked in the bidder's language")
    reference: NonEmptyStr = Field(description="The label's verified summary — the answer")
    reference_contexts: tuple[NonEmptyStr, ...] = Field(
        min_length=1, description="The label's verbatim quote — what should be retrieved"
    )
    doc: NonEmptyStr
    page: int = Field(ge=1)


class QuestionSet(BaseModel):
    """One tender's retrieval answer key."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    meta: QuestionSetMeta
    questions: tuple[RetrievalQuestion, ...] = Field(min_length=1)

    @property
    def fixture_name(self) -> str:
        return Path(self.meta.fixture_dir).name


def load_question_set(path: Path) -> QuestionSet:
    """Read one question set, or raise `QuestionSetError` naming what is wrong with it."""
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise QuestionSetError(f"{path}: {exc}") from exc
    if not isinstance(document, dict):
        raise QuestionSetError(f"{path}: expected a mapping with `meta` and `questions`")
    return QuestionSet.model_validate(document)


def dump_question_set(question_set: QuestionSet, path: Path) -> None:
    """Write a question set as a fixture a human can read and edit in place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(
        question_set.model_dump(mode="json"),
        allow_unicode=True,
        sort_keys=False,
        width=96,
    )
    path.write_text(body, encoding="utf-8")


def questions_by_label(questions: Sequence[RetrievalQuestion]) -> dict[str, RetrievalQuestion]:
    """Index by the golden label each question came from."""
    return {question.label_id: question for question in questions}


# ------------------------------------------------------------------ reviewing a draft key

FORM_VOICE: Final = (
    "möchten sie",
    "wählen sie",
    "bitte geben sie",
    "tragen sie",
    "kreuzen sie",
    "ihrem angebot",
    "ihres angebots",
)
"""Phrases in which a tender *form* addresses the bidder.

A question carrying one was copied out of the document's own register rather than asked by
somebody reading it — "Welche Variante möchten Sie wählen?" is a field on a form, not something
a bidder types into a search box. Found by a human reviewer on 2026-09-16 and kept as a check
because the generator will run again.
"""


class ReviewFlag(StrEnum):
    """Why a drafted question needs a person to look at it."""

    FORM_VOICE = "form_voice"
    """The question is addressed *to* the bidder, in the document's own register."""

    ECHOES_CLAUSE = "echoes_clause"
    """The question reuses most of the source clause's wording.

    Not automatically wrong — German compounds the domain nouns, so any natural question about
    a clause reuses its words — but it is where a question that hands over its own answer will
    be found, so it is worth a reviewer's eye.
    """


ECHO_OVERLAP: Final = 0.7
"""Share of a question's words that may also appear in the clause it was drafted from.

Compared against the **clause**, not the reference: the clause is in the tender's language and
so is the question, while `GoldenRequirement.summary` is one line of English. Comparing a
German question with an English summary measures the language gap and nothing else — which an
earlier version of this check did, flagging 86 of 90 questions.
"""


def content_words(text: str) -> set[str]:
    """Words long enough to carry retrieval signal."""
    return set(re.findall(r"\w{5,}", text.casefold()))


def review_flags(question: RetrievalQuestion) -> tuple[ReviewFlag, ...]:
    """What is mechanically suspicious about one drafted question.

    **Deliberately only the two things a machine can see.** Whether a question is answerable
    from its reference, and whether it restates its own answer, are semantic judgements across
    two languages; `scripts/review_questions.py` asks the judge those, because a lexical
    approximation of them is worse than nothing — it was tried and it flagged everything.
    """
    flags: list[ReviewFlag] = []
    lowered = question.question.casefold()
    if any(phrase in lowered for phrase in FORM_VOICE):
        flags.append(ReviewFlag.FORM_VOICE)

    asked = content_words(question.question)
    clause = content_words(question.reference_contexts[0])
    if asked and len(asked & clause) / len(asked) >= ECHO_OVERLAP:
        flags.append(ReviewFlag.ECHOES_CLAUSE)
    return tuple(flags)


def flagged_questions(
    question_set: QuestionSet,
) -> tuple[tuple[RetrievalQuestion, tuple[ReviewFlag, ...]], ...]:
    """Every question with at least one flag, paired with its flags."""
    return tuple(
        (question, flags)
        for question in question_set.questions
        if (flags := review_flags(question))
    )
