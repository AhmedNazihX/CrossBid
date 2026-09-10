"""S0.4.1 — the contract layer.

Two acceptance criteria, verbatim:
- Given the models in the layout, then each exports a JSON schema without error and every
  enum is closed.
- Given `Requirement.ecertis_criterion_id`, then it is typed against the criterion list.

Plus the architectural rule the whole layering depends on: `crossbid.models` imports nothing
else from `crossbid`. That one is asserted here because nothing else can catch it — a stray
import would compile, pass every other test, and quietly invert the dependency graph.
"""

from __future__ import annotations

import ast
import enum
import inspect
import pkgutil
from datetime import date, datetime
from pathlib import Path
from typing import Any, get_args, get_origin

import pytest
from pydantic import BaseModel, ValidationError

from crossbid import models
from crossbid.models import (
    CRITERION_IDS,
    Checkability,
    CompanyProfile,
    Decision,
    EcertisEvidence,
    Evidence,
    Gap,
    GapSeverity,
    LegalForm,
    MatrixRow,
    Requirement,
    RequirementCategory,
    RequirementKind,
    RequirementStage,
    ReviewerStatus,
    RowStatus,
    Threshold,
    ThresholdComparator,
    ThresholdUnit,
    Verdict,
    WeightedScore,
)

MODELS_DIR = Path(models.__file__).parent


def _exported_models() -> list[type[BaseModel]]:
    """Every Pydantic model re-exported by the package."""
    return [
        obj
        for name in models.__all__
        if inspect.isclass(obj := getattr(models, name)) and issubclass(obj, BaseModel)
    ]


def _exported_enums() -> list[type[enum.Enum]]:
    return [
        obj
        for name in models.__all__
        if inspect.isclass(obj := getattr(models, name)) and issubclass(obj, enum.Enum)
    ]


# --------------------------------------------------------------- acceptance criterion 1


def test_every_model_exports_a_json_schema() -> None:
    """The schema generates frontend/lib/api.ts, so a failure here breaks the frontend."""
    # Arrange
    exported = _exported_models()
    assert exported, "no models were exported; __all__ is probably wrong"

    # Act / Assert
    for model in exported:
        schema = model.model_json_schema()
        assert schema["title"] == model.__name__
        assert "properties" in schema or "$ref" in schema


def test_every_exported_enum_is_closed() -> None:
    """A closed enum is the point: an open string field cannot be compared or validated."""
    # Arrange
    exported = _exported_enums()
    assert exported

    # Act / Assert
    for enum_type in exported:
        assert issubclass(enum_type, enum.Enum)
        assert len(list(enum_type)) > 0
        with pytest.raises(ValueError, match="is not a valid"):
            enum_type("definitely-not-a-member")


def test_enum_values_are_stable_snake_case() -> None:
    """These values reach the database, the API and the UI, so a rename is a breaking change."""
    for enum_type in _exported_enums():
        for member in enum_type:
            assert isinstance(member.value, str)
            assert member.value == member.value.lower()
            assert " " not in member.value


def test_every_module_in_the_layout_exists() -> None:
    """The plan names seven modules; a missing one means a contract with no single home."""
    # Arrange
    expected = {
        "company",
        "ecertis_criteria",
        "matrix",
        "provider",
        "requirement",
        "review",
        "tender",
        "verdict",
    }

    # Act
    found = {module.name for module in pkgutil.iter_modules([str(MODELS_DIR)])}

    # Assert
    assert expected <= found, f"missing model modules: {sorted(expected - found)}"


# --------------------------------------------------------------- acceptance criterion 2


def test_requirement_accepts_a_real_criterion_id() -> None:
    # Arrange
    real_id = CRITERION_IDS[0]

    # Act
    requirement = _requirement(ecertis_criterion_id=real_id)

    # Assert
    assert requirement.ecertis_criterion_id == real_id


def test_requirement_rejects_an_invented_criterion_id() -> None:
    """The extractor must not be able to invent a criterion (S0.4.1's second criterion)."""
    # Act / Assert
    with pytest.raises(ValidationError):
        _requirement(ecertis_criterion_id="iso-27001")


def test_requirement_criterion_id_is_optional() -> None:
    """Most requirements map to no ESPD criterion, so None has to be a first-class answer."""
    assert _requirement().ecertis_criterion_id is None


def test_criterion_id_field_is_typed_against_the_generated_literal() -> None:
    """Guards against the annotation silently degrading to `str | None` in a refactor."""
    # Act
    annotation = Requirement.model_fields["ecertis_criterion_id"].annotation
    literal_values = {v for arg in get_args(annotation) for v in get_args(arg)}

    # Assert
    assert literal_values == set(CRITERION_IDS)


# --------------------------------------------------------------- the layering rule


def test_models_package_imports_nothing_from_crossbid() -> None:
    """`models/` is the bottom of the dependency graph and must import only stdlib and pydantic.

    Importing `crossbid.models.*` is fine — that is inside the package. Anything else under
    `crossbid` would invert the layering the whole architecture rests on.
    """
    # Arrange
    offenders: list[str] = []

    # Act
    for path in sorted(MODELS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                target = node.module
            elif isinstance(node, ast.Import):
                target = node.names[0].name
            else:
                continue
            if target.startswith("crossbid") and not target.startswith("crossbid.models"):
                offenders.append(f"{path.name}: {target}")

    # Assert
    assert not offenders, f"models/ must not import from crossbid: {offenders}"


# --------------------------------------------------------------- invariants that carry weight


def test_a_met_row_cannot_be_uncited() -> None:
    """The product's central promise: every cell carries a citation or is marked unclear."""
    with pytest.raises(ValidationError, match="citation"):
        MatrixRow(
            id="row-1",
            requirement_id="req-1",
            status=RowStatus.MET,
            agent_rationale="the company looks fine",
        )


def test_a_met_row_is_accepted_with_evidence() -> None:
    # Arrange
    evidence = Evidence(
        document_id="doc-1",
        document_name="ISO_27001.pdf",
        page=1,
        quote="Zertifizierung nach ISO/IEC 27001:2022",
    )

    # Act
    row = MatrixRow(
        id="row-1",
        requirement_id="req-1",
        status=RowStatus.MET,
        evidence=(evidence,),
        agent_rationale="Certificate on page 1 covers the required scope.",
    )

    # Assert
    assert row.status is RowStatus.MET
    assert row.evidence[0].page == 1


def test_an_unclear_row_needs_no_evidence() -> None:
    """`unclear` is the honest answer when nothing can be cited, so it stays cheap to use."""
    row = MatrixRow(
        id="row-1",
        requirement_id="req-1",
        status=RowStatus.UNCLEAR,
        agent_rationale="No document addresses the required staff count.",
    )
    assert not row.evidence


def test_an_overridden_row_must_record_a_reason() -> None:
    with pytest.raises(ValidationError, match="override_reason"):
        MatrixRow(
            id="row-1",
            requirement_id="req-1",
            status=RowStatus.UNMET,
            agent_rationale="x",
            reviewer_status=ReviewerStatus.OVERRIDDEN,
        )


def test_models_are_immutable() -> None:
    """The coding style forbids mutation; frozen models make a violation fail loudly."""
    row = MatrixRow(
        id="row-1", requirement_id="req-1", status=RowStatus.UNCLEAR, agent_rationale="x"
    )
    with pytest.raises(ValidationError):
        row.status = RowStatus.MET  # type: ignore[misc]


def test_unknown_fields_are_rejected() -> None:
    """`extra="forbid"` turns a typo in a graph node into an error instead of a silent no-op."""
    with pytest.raises(ValidationError):
        Evidence(
            document_id="d",
            document_name="n",
            page=1,
            quote="q",
            pge=2,  # type: ignore[call-arg]
        )


# --------------------------------------------------------------- verdict rules


def test_no_go_requires_a_blocking_gap() -> None:
    with pytest.raises(ValidationError, match="no blocking gap"):
        Verdict(
            decision=Decision.NO_GO,
            rationale="x",
            mandatory_total=1,
            mandatory_met=1,
            unclear_rows=0,
        )


def test_a_blocking_gap_forces_no_go() -> None:
    """A `go` that lists a blocking gap contradicts itself, and the reviewer would be misled."""
    # Arrange
    gap = Gap(requirement_id="TECH-06", severity=GapSeverity.BLOCKING, summary="too few staff")

    # Act / Assert
    with pytest.raises(ValidationError, match="blocking gap means no_go"):
        Verdict(
            decision=Decision.GO,
            gaps=(gap,),
            rationale="x",
            mandatory_total=1,
            mandatory_met=0,
            unclear_rows=0,
        )


def test_the_german_fixtures_real_outcome_is_expressible() -> None:
    """25 staff against a 29 VZAE minimum, EUR 2.8m against EUR 3m (ADR-0002)."""
    # Arrange / Act
    verdict = Verdict(
        decision=Decision.NO_GO,
        gaps=(
            Gap(
                requirement_id="TECH-06",
                severity=GapSeverity.BLOCKING,
                summary="Zu wenige Fachkraefte im einschlaegigen Geschaeftsbereich",
                required="29 FTE",
                actual="21 FTE",
            ),
            Gap(
                requirement_id="FIN-01",
                severity=GapSeverity.BLOCKING,
                summary="Mindestumsatz nicht erreicht",
                required="EUR 3,000,000 per year",
                actual="EUR 2,800,000",
            ),
        ),
        rationale="Zwei Mindestanforderungen sind nicht erfuellt.",
        mandatory_total=21,
        mandatory_met=19,
        unclear_rows=0,
    )

    # Assert
    assert verdict.decision is Decision.NO_GO
    assert len(verdict.gaps) == 2


def test_go_must_be_clean() -> None:
    """`go` means nothing outstanding; anything else is `go_with_open_items`."""
    with pytest.raises(ValidationError, match="go_with_open_items"):
        Verdict(
            decision=Decision.GO,
            rationale="x",
            mandatory_total=2,
            mandatory_met=2,
            unclear_rows=1,
        )


def test_mandatory_met_cannot_exceed_the_total() -> None:
    with pytest.raises(ValidationError, match="cannot exceed"):
        Verdict(
            decision=Decision.GO,
            rationale="x",
            mandatory_total=1,
            mandatory_met=2,
            unclear_rows=0,
        )


# --------------------------------------------------------------- weighted scoring (ADR-0006)


def test_the_french_fixtures_weighted_score_clears_its_threshold() -> None:
    """The FR ministry tender scores selection out of 10 and eliminates below 5."""
    # Arrange / Act
    score = WeightedScore(points=6, points_available=10, threshold=5)

    # Assert
    assert score.clears_threshold


def test_a_weighted_score_below_the_threshold_does_not_clear() -> None:
    assert not WeightedScore(points=4, points_available=10, threshold=5).clears_threshold


def test_a_score_exactly_at_the_threshold_clears() -> None:
    """The buyer eliminates *below* the cut-off, so the boundary itself passes."""
    assert WeightedScore(points=5, points_available=10, threshold=5).clears_threshold


def test_points_cannot_exceed_the_scale() -> None:
    with pytest.raises(ValidationError, match="points_available"):
        WeightedScore(points=11, points_available=10, threshold=5)


def test_a_failing_score_must_be_recorded_as_a_blocking_gap() -> None:
    """Otherwise a bid could be recommended while sitting below the buyer's own cut-off."""
    with pytest.raises(ValidationError, match="below the buyer's threshold"):
        Verdict(
            decision=Decision.GO_WITH_OPEN_ITEMS,
            score=WeightedScore(points=4, points_available=10, threshold=5),
            rationale="x",
            mandatory_total=1,
            mandatory_met=1,
            unclear_rows=0,
        )


# --------------------------------------------------------------- eCertis evidence


def test_a_country_with_no_national_entry_is_normal() -> None:
    """France records no evidence for 17 of the 56 criteria, so this is the common case."""
    # Arrange / Act
    evidence = EcertisEvidence(
        criterion_id=CRITERION_IDS[0],
        criterion_name="Participation in a criminal organisation",
        country="fr",
        found=False,
    )

    # Assert
    assert not evidence.found
    assert evidence.evidence_names == ()


def test_ecertis_evidence_rejects_an_unknown_criterion() -> None:
    with pytest.raises(ValidationError):
        EcertisEvidence(
            criterion_id="not-a-criterion",  # type: ignore[arg-type]
            criterion_name="x",
            country="de",
            found=True,
        )


# --------------------------------------------------------------- thresholds


def test_a_currency_threshold_carries_its_currency() -> None:
    # Arrange / Act
    threshold = Threshold(
        comparator=ThresholdComparator.AT_LEAST,
        value=3_000_000,
        unit=ThresholdUnit.CURRENCY,
        currency="EUR",
        period="per_year",
    )

    # Assert
    assert threshold.value == 3_000_000
    assert threshold.currency == "EUR"


def test_a_currency_code_must_be_three_letters() -> None:
    with pytest.raises(ValidationError):
        Threshold(
            comparator=ThresholdComparator.AT_LEAST,
            value=1,
            unit=ThresholdUnit.CURRENCY,
            currency="EUROS",
        )


# --------------------------------------------------------------- company facts


def test_a_certificate_without_an_expiry_cannot_be_claimed_valid() -> None:
    """Refusing to guess is the point: an unknown expiry is not a valid certificate."""
    from crossbid.models import CertificateHeld

    assert not CertificateHeld(name="ISO/IEC 27001").is_valid_on(date(2026, 9, 10))


def test_an_expired_certificate_is_not_valid() -> None:
    from crossbid.models import CertificateHeld

    certificate = CertificateHeld(name="ISO/IEC 27001", expires_on=date(2026, 1, 1))
    assert not certificate.is_valid_on(date(2026, 9, 10))


def test_a_current_certificate_is_valid() -> None:
    from crossbid.models import CertificateHeld

    certificate = CertificateHeld(name="ISO/IEC 27001", expires_on=date(2027, 3, 13))
    assert certificate.is_valid_on(date(2026, 9, 10))


def test_the_demo_company_profile_round_trips() -> None:
    """The fictional German IT GmbH from the plan, so the shape is exercised end to end."""
    # Arrange
    from crossbid.models import CertificateHeld, TurnoverYear

    profile = CompanyProfile(
        name="Musterdaten IT-Services GmbH",
        country="de",
        legal_form=LegalForm.GMBH,
        registration_number="HRB 84512",
        registration_court="Amtsgericht Koeln",
        staff_fte=25,
        staff_fte_relevant=21,
        turnover=(TurnoverYear(year=2025, amount=2_800_000, currency="EUR"),),
        certificates=(
            CertificateHeld(name="ISO/IEC 27001:2022", expires_on=date(2027, 3, 13)),
        ),
    )

    # Act
    restored = CompanyProfile.model_validate_json(profile.model_dump_json())

    # Assert
    assert restored == profile
    assert restored.staff_fte_relevant == 21


# --------------------------------------------------------------- requirement helpers


def _requirement(**overrides: Any) -> Requirement:
    """A minimal valid requirement, so each test varies exactly one thing."""
    defaults: dict[str, Any] = {
        "id": "req-1",
        "bid_id": "bid-1",
        "category": RequirementCategory.ECONOMIC_FINANCIAL,
        "kind": RequirementKind.MANDATORY,
        "stage": RequirementStage.BID_ELIGIBILITY,
        "checkable": Checkability.COMPANY_PROPERTY,
        "source_text": "Der Umsatz muss mindestens 3.000.000,00 EUR pro Jahr betragen.",
        "source_lang": "de",
        "document_name": "Kriterienkatalog_Eignung_VV2_V1.pdf",
        "page": 1,
    }
    return Requirement(**(defaults | overrides))


def test_a_requirement_quotes_its_source_verbatim() -> None:
    """Paraphrasing would break the citation promise, so the field holds the original text."""
    requirement = _requirement()
    assert "3.000.000,00 EUR" in requirement.source_text
    assert requirement.source_lang == "de"


def test_pages_are_one_indexed() -> None:
    """Page 0 would not match what the reviewer's PDF viewer shows."""
    with pytest.raises(ValidationError):
        _requirement(page=0)


def test_a_contract_performance_requirement_is_expressible() -> None:
    """SP.1's key discriminator: these exist, and are filtered out of the matrix (ADR-0003)."""
    requirement = _requirement(
        stage=RequirementStage.CONTRACT_PERFORMANCE,
        checkable=Checkability.NEITHER,
        category=RequirementCategory.OTHER,
    )
    assert requirement.stage is RequirementStage.CONTRACT_PERFORMANCE


def test_a_document_submission_requirement_cannot_be_settled_by_evidence() -> None:
    """These returned `unclear` for every row in SP.1 run 1; they go to the reviewer instead."""
    requirement = _requirement(
        category=RequirementCategory.FORMAL,
        checkable=Checkability.DOCUMENT_SUBMISSION,
        source_text="Mit dem Angebot sind folgende Dokumente einzureichen: Angebotsformular",
    )
    assert requirement.checkable is Checkability.DOCUMENT_SUBMISSION


def test_a_requirement_round_trips_through_json() -> None:
    """The frontend receives these as JSON, so the round trip is the real contract."""
    # Arrange
    requirement = _requirement(
        threshold=Threshold(
            comparator=ThresholdComparator.AT_LEAST,
            value=29,
            unit=ThresholdUnit.FTE,
            period="per_fiscal_year",
        ),
        deadline=date(2026, 10, 6),
        translation="Annual turnover must be at least EUR 3,000,000.",
    )

    # Act
    restored = Requirement.model_validate_json(requirement.model_dump_json())

    # Assert
    assert restored == requirement
    assert restored.threshold is not None
    assert restored.threshold.unit is ThresholdUnit.FTE


def test_datetime_fields_serialise_to_iso_8601() -> None:
    """The frontend parses these directly, so the wire format has to be predictable."""
    from crossbid.models import BidStatus, BidSummary

    summary = BidSummary(
        id="bid-1",
        company_id="co-1",
        title="IPv6-Experten Los 2",
        status=BidStatus.AWAITING_REVIEW,
        deadline=datetime(2026, 10, 6, 12, 0),
    )
    assert '"2026-10-06T12:00:00"' in summary.model_dump_json()


def test_optional_annotations_are_genuinely_optional() -> None:
    """A field typed `X | None` with no default would be a required field wearing a disguise."""
    for model in _exported_models():
        for name, field in model.model_fields.items():
            annotation = field.annotation
            is_optional = get_origin(annotation) is not None and type(None) in get_args(
                annotation
            )
            if is_optional:
                assert not field.is_required(), (
                    f"{model.__name__}.{name} is typed as optional but has no default"
                )


# --------------------------------------------------------------- review submissions


def test_changing_a_row_status_requires_a_reason() -> None:
    """A reviewer overruling the agent must say why, or the override is unauditable."""
    from crossbid.models import RowEdit

    with pytest.raises(ValidationError, match="override_reason"):
        RowEdit(matrix_row_id="row-1", status=RowStatus.MET)


def test_a_row_edit_must_change_something() -> None:
    """An empty edit is a silent no-op, which would look like a successful review."""
    from crossbid.models import RowEdit

    with pytest.raises(ValidationError, match="must change a status"):
        RowEdit(matrix_row_id="row-1")


def test_a_row_edit_may_only_attach_a_document() -> None:
    """Attaching the missing paper is a legitimate edit that changes no status."""
    from crossbid.models import RowEdit

    edit = RowEdit(matrix_row_id="row-1", attached_doc_ids=("doc-9",))
    assert edit.status is None
    assert edit.attached_doc_ids == ("doc-9",)


def test_a_row_edit_with_a_status_and_a_reason_is_accepted() -> None:
    from crossbid.models import RowEdit

    edit = RowEdit(
        matrix_row_id="row-1",
        status=RowStatus.MET,
        override_reason="Certificate attached; the agent missed page 4.",
    )
    assert edit.status is RowStatus.MET


def test_duplicate_row_edits_are_rejected() -> None:
    """Two edits to one row would make the outcome depend on application order."""
    from crossbid.models import ReviewSubmission, RowEdit

    with pytest.raises(ValidationError, match="duplicate row edits"):
        ReviewSubmission(
            decision=Decision.GO,
            row_edits=(
                RowEdit(matrix_row_id="row-1", override_reason="first"),
                RowEdit(matrix_row_id="row-1", override_reason="second"),
            ),
        )


def test_a_review_submission_round_trips() -> None:
    """This shape crosses the interrupt as `Command(resume=...)`, so the round trip matters."""
    from crossbid.models import ReviewSubmission, RowEdit

    submission = ReviewSubmission(
        decision=Decision.NO_GO,
        row_edits=(
            RowEdit(
                matrix_row_id="row-1",
                status=RowStatus.UNMET,
                override_reason="Wir haben nur 21 VZAE.",
            ),
        ),
        override_reason="Mindestanforderung an die Beschaeftigtenzahl nicht erfuellt.",
    )

    restored = ReviewSubmission.model_validate_json(submission.model_dump_json())
    assert restored == submission


def test_a_chat_turn_carries_its_citations() -> None:
    """Chat answers cite pages too — the no-uncited-claims rule is not matrix-only."""
    from crossbid.models import ChatRole, ChatTurn, Citation

    turn = ChatTurn(
        role=ChatRole.ASSISTANT,
        content="Der Mindestumsatz betraegt 3.000.000 EUR pro Jahr.",
        citations=(
            Citation(
                document_id="doc-1",
                document_name="Kriterienkatalog_Eignung_VV2_V1.pdf",
                page=1,
                quote="Der Umsatz muss mindestens 3.000.000,00 EUR pro Jahr betragen.",
            ),
        ),
    )
    assert turn.citations[0].page == 1


def test_a_weighted_score_threshold_cannot_exceed_the_scale() -> None:
    """A cut-off above the maximum would fail every bid, which is never the buyer's rule."""
    with pytest.raises(ValidationError, match="threshold cannot exceed"):
        WeightedScore(points=1, points_available=10, threshold=11)
