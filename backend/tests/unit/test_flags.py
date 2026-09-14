"""S3.4.4 — the reviewer notices: what gets flagged, and what deliberately does not.

Pure and offline, like `agent/flags.py` itself. The certificate matcher is a *heuristic*
(there is no join between a held certificate and a stored document), so the tests below are
written as its specification: the pairings it must make, and the ones it must refuse. A
matcher that warned about the wrong certificate would be worse than one that warned about
none — the reviewer would go looking for a paper that is not the problem.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest

from crossbid.agent.flags import (
    ECERTIS_NOT_FOUND_NOTICE,
    EXPIRED_CERTIFICATE_NOTICE,
    MAX_FLAGGED_RATIONALE_CHARS,
    MIN_SHARED_TOKENS,
    flag_rows,
)
from crossbid.models.company import CertificateHeld, CompanyProfile, LegalForm
from crossbid.models.ecertis_criteria import CRITERION_IDS
from crossbid.models.matrix import EcertisEvidence, Evidence, MatrixRow, RowStatus

TODAY = date(2026, 9, 14)
LAPSED = date(2026, 3, 31)
CURRENT = date(2027, 6, 30)
RATIONALE = "Belegt durch das beigefügte Zertifikat."


# ------------------------------------------------------------------------ hand-built input


def certificate(
    name: str = "ISO/IEC 27001:2022", expires_on: date | None = LAPSED
) -> CertificateHeld:
    return CertificateHeld(name=name, issuer="DEKRA", expires_on=expires_on)


def profile(*certificates: CertificateHeld) -> CompanyProfile:
    return CompanyProfile(
        name="Musterfirma IT-Dienstleistungen GmbH",
        country="de",
        legal_form=LegalForm.GMBH,
        certificates=certificates,
    )


def evidence(document_name: str = "ISO_27001_Zertifikat.pdf") -> Evidence:
    return Evidence(
        document_id=str(uuid.uuid4()),
        document_name=document_name,
        page=1,
        quote="Gültig bis 31.03.2026",
    )


def row(**overrides: Any) -> MatrixRow:
    values: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "requirement_id": str(uuid.uuid4()),
        "status": RowStatus.SUPPORTED,
        "evidence": (evidence(),),
        "agent_rationale": RATIONALE,
    }
    return MatrixRow(**(values | overrides))


def ecertis(*, found: bool, country: str = "de") -> EcertisEvidence:
    return EcertisEvidence(
        criterion_id=CRITERION_IDS[0],
        criterion_name="Teilnahme an einer kriminellen Vereinigung",
        country=country,
        found=found,
        evidence_names=("Führungszeugnis",) if found else (),
    )


# ------------------------------------------------------------------------------- eCertis


def test_a_criterion_ecertis_has_no_national_entry_for_is_flagged() -> None:
    # Arrange
    rows = [row(ecertis_evidence=ecertis(found=False, country="fr"))]

    # Act
    flagged = flag_rows(rows, profile=None, today=TODAY)

    # Assert
    assert ECERTIS_NOT_FOUND_NOTICE.format(country="FR") in flagged[0].agent_rationale
    assert flagged[0].agent_rationale.startswith(RATIONALE)


def test_a_criterion_with_a_national_entry_is_not_flagged() -> None:
    rows = [row(ecertis_evidence=ecertis(found=True))]

    assert flag_rows(rows, profile=None, today=TODAY)[0].agent_rationale == RATIONALE


def test_a_row_with_no_criterion_at_all_is_not_flagged() -> None:
    """Most requirements map to no ESPD criterion; a notice on all of them says nothing."""
    assert flag_rows([row()], profile=None, today=TODAY)[0].agent_rationale == RATIONALE


# -------------------------------------------------------------------------- certificates


def test_a_row_citing_an_expired_certificate_is_warned_with_its_date() -> None:
    # Arrange
    held = certificate()

    # Act
    flagged = flag_rows([row()], profile=profile(held), today=TODAY)

    # Assert
    expected = EXPIRED_CERTIFICATE_NOTICE.format(name=held.name, expires_on=LAPSED)
    assert expected in flagged[0].agent_rationale
    assert "2026-03-31" in flagged[0].agent_rationale


def test_a_certificate_that_is_still_current_raises_no_warning() -> None:
    rows = flag_rows([row()], profile=profile(certificate(expires_on=CURRENT)), today=TODAY)

    assert rows[0].agent_rationale == RATIONALE


def test_a_certificate_with_no_recorded_expiry_raises_no_warning() -> None:
    """`is_expired_on` is not the negation of `is_valid_on`: undated is neither."""
    rows = flag_rows([row()], profile=profile(certificate(expires_on=None)), today=TODAY)

    assert rows[0].agent_rationale == RATIONALE


def test_a_certificate_expiring_today_is_still_current() -> None:
    rows = flag_rows([row()], profile=profile(certificate(expires_on=TODAY)), today=TODAY)

    assert rows[0].agent_rationale == RATIONALE


def test_the_status_is_never_changed_by_a_warning() -> None:
    """Decision 2: the product is advisory and the reviewer decides. A silent downgrade
    would also move the verdict on a fact the scorer never saw."""
    # Arrange
    original = row()

    # Act
    flagged = flag_rows([original], profile=profile(certificate()), today=TODAY)

    # Assert -- only the rationale moved
    assert flagged[0].status is RowStatus.SUPPORTED
    assert flagged[0].evidence == original.evidence
    assert flagged[0].model_dump(exclude={"agent_rationale"}) == original.model_dump(
        exclude={"agent_rationale"}
    )


def test_flagging_returns_new_rows_and_leaves_the_originals_alone() -> None:
    # Arrange
    original = row()

    # Act
    flagged = flag_rows([original], profile=profile(certificate()), today=TODAY)

    # Assert
    assert original.agent_rationale == RATIONALE
    assert flagged[0] is not original


def test_a_row_with_nothing_to_flag_is_returned_unchanged() -> None:
    """The common case: the caller writes the rows back either way, so identity matters."""
    original = row()

    assert flag_rows([original], profile=profile(), today=TODAY)[0] is original


# ----------------------------------------------------------------- the matcher, as a spec


@pytest.mark.parametrize(
    ("certificate_name", "document_name"),
    [
        ("ISO/IEC 27001:2022", "ISO_27001_Zertifikat.pdf"),
        ("ISO 9001:2015", "ISO_9001.pdf"),
        ("ISO 14001", "Umweltmanagement_ISO_14001_2024.pdf"),
        ("Präqualifikation PQ-VOB 12345", "PQ_VOB_Bescheinigung_12345.pdf"),
    ],
)
def test_the_matcher_pairs_a_certificate_with_the_document_that_is_it(
    certificate_name: str, document_name: str
) -> None:
    # Act
    flagged = flag_rows(
        [row(evidence=(evidence(document_name),))],
        profile=profile(certificate(certificate_name)),
        today=TODAY,
    )

    # Assert
    assert certificate_name in flagged[0].agent_rationale


@pytest.mark.parametrize(
    ("certificate_name", "document_name"),
    [
        # One shared token is the family prefix, not the certificate — naming the wrong
        # paper sends the reviewer looking for something that is not the problem.
        ("ISO 9001", "ISO_27001_Zertifikat.pdf"),
        ("ISO/IEC 27001:2022", "Jahresabschluss_2025.pdf"),
        ("ISO/IEC 27001:2022", "Handelsregisterauszug.pdf"),
    ],
)
def test_the_matcher_refuses_a_document_that_is_a_different_paper(
    certificate_name: str, document_name: str
) -> None:
    # Act
    flagged = flag_rows(
        [row(evidence=(evidence(document_name),))],
        profile=profile(certificate(certificate_name)),
        today=TODAY,
    )

    # Assert
    assert flagged[0].agent_rationale == RATIONALE


def test_the_threshold_is_two_shared_tokens_and_the_constant_says_so() -> None:
    """Pinned, because lowering it to one is the tempting "fix" when a pairing is missed and
    it is what makes the matcher name the wrong certificate."""
    assert MIN_SHARED_TOKENS == 2


def test_a_row_citing_nothing_is_never_matched_to_a_certificate() -> None:
    rows = flag_rows(
        [row(status=RowStatus.UNSUPPORTED, evidence=())],
        profile=profile(certificate()),
        today=TODAY,
    )

    assert rows[0].agent_rationale == RATIONALE


# ------------------------------------------------------------------------------- together


def test_both_notices_can_land_on_one_row() -> None:
    # Arrange
    rows = [row(ecertis_evidence=ecertis(found=False))]

    # Act
    flagged = flag_rows(rows, profile=profile(certificate()), today=TODAY)

    # Assert
    assert "eCertis records no national document" in flagged[0].agent_rationale
    assert "expired on 2026-03-31" in flagged[0].agent_rationale


def test_a_row_matching_many_expired_certificates_stays_inside_the_cell() -> None:
    """A document whose name matches several lapsed certificates must not grow the cell
    without bound — `agent_rationale` has no length check in the column."""
    # Arrange
    held = tuple(certificate(f"ISO 27001 Teil {n}") for n in range(40))

    # Act
    flagged = flag_rows(
        [row(evidence=(evidence("ISO_27001_Teil_Zertifikate.pdf"),))],
        profile=profile(*held),
        today=TODAY,
    )

    # Assert
    assert len(flagged[0].agent_rationale) <= MAX_FLAGGED_RATIONALE_CHARS


def test_a_profile_that_could_not_be_read_costs_the_certificate_warning_only() -> None:
    """Same choice `plan_checks` and `score_verdict` make: the run survives the gap."""
    # Act
    flagged = flag_rows([row(ecertis_evidence=ecertis(found=False))], profile=None, today=TODAY)

    # Assert
    assert "eCertis records no national document" in flagged[0].agent_rationale
    assert "expired on" not in flagged[0].agent_rationale


def test_every_row_is_returned_in_order() -> None:
    rows = [row(), row(), row()]

    assert [r.id for r in flag_rows(rows, profile=profile(), today=TODAY)] == [
        r.id for r in rows
    ]
