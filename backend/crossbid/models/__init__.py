"""Domain contracts. The single schema source for the whole system.

Routers, graph nodes, structured LLM outputs and the generated TypeScript types all speak
these shapes, which is why one architectural rule applies here above all others:

    `crossbid.models` imports NOTHING else from `crossbid`.

It sits at the bottom of the dependency graph. `reference/`, `ingestion/`, `agent/`,
`readmodel/` and `routers/` all depend on it; it depends on none of them. `ecertis_criteria.py`
lives here rather than in `reference/` for exactly that reason — the criterion Literal is part
of the contract, and `models/` may not import from `reference/` to get it.

A test asserts this rule (`test_models.py::test_models_package_imports_nothing_from_crossbid`).
"""

from __future__ import annotations

from crossbid.models.company import (
    CertificateHeld,
    CompanyProfile,
    LegalForm,
    Tone,
    TurnoverYear,
)
from crossbid.models.ecertis_criteria import CRITERION_IDS, CRITERION_NAMES, EcertisCriterionId
from crossbid.models.matrix import (
    EcertisEvidence,
    Evidence,
    MatrixRow,
    ReviewerStatus,
    RowStatus,
)
from crossbid.models.provider import (
    ModelRole,
    Provider,
    ProviderKeyStatus,
    ProviderSelection,
)
from crossbid.models.requirement import (
    Checkability,
    Requirement,
    RequirementCategory,
    RequirementKind,
    RequirementStage,
    Threshold,
    ThresholdComparator,
    ThresholdUnit,
)
from crossbid.models.review import ChatRole, ChatTurn, Citation, ReviewSubmission, RowEdit
from crossbid.models.tender import BidStatus, BidSummary, TedNotice
from crossbid.models.verdict import Decision, Gap, GapSeverity, Verdict, WeightedScore

__all__ = [
    "CRITERION_IDS",
    "CRITERION_NAMES",
    "BidStatus",
    "BidSummary",
    "CertificateHeld",
    "ChatRole",
    "ChatTurn",
    "Checkability",
    "Citation",
    "CompanyProfile",
    "Decision",
    "EcertisCriterionId",
    "EcertisEvidence",
    "Evidence",
    "Gap",
    "GapSeverity",
    "LegalForm",
    "MatrixRow",
    "ModelRole",
    "Provider",
    "ProviderKeyStatus",
    "ProviderSelection",
    "Requirement",
    "RequirementCategory",
    "RequirementKind",
    "RequirementStage",
    "ReviewSubmission",
    "ReviewerStatus",
    "RowEdit",
    "RowStatus",
    "TedNotice",
    "Threshold",
    "ThresholdComparator",
    "ThresholdUnit",
    "Tone",
    "TurnoverYear",
    "Verdict",
    "WeightedScore",
]
