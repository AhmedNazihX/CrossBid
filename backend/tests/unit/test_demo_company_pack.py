"""S6.3 — the synthetic document pack for the demo GmbH, and its generator.

The pack is committed binary, which is exactly the kind of fixture that rots silently: a
number moves in `profile.yaml`, nobody rebuilds the PDFs, and the walkthrough starts citing
evidence that contradicts the profile. Two tests make that impossible — the committed bytes
must equal a fresh build, and the numbers the PDFs print are read out of `profile.yaml`
rather than typed twice.

Everything here is offline. The generator is loaded by path, as `test_seed_dev_company.py`
loads the seed, because `scripts/` is not a package.

The pack's consumers are the reason for the rest of the assertions:

* **S2.4.3** seeds these documents through the real ingestion pipeline, so every page must
  carry a text layer `has_extractable_text` accepts — an unread page would be an unciteable
  page.
* **`company_rag_search`** has to answer a French tender's information-security question
  with the German ISO 27001 page, so the German wording is pinned, not left to taste.
* **S2.4.1** flags an expired certificate, which needs a fixture that actually has one.
* The DE tender fixture (ADR-0002) demands >= 3 000 000 EUR turnover and >= 29 VZAE. The
  demo company clears the first and misses the second, which is what makes the no-go
  walkthrough a real no-go with a concrete gap; both are pinned here.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from collections.abc import Iterator, Mapping
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest
import yaml

from crossbid.ingestion.parser import has_extractable_text
from crossbid.ingestion.pymupdf_parser import PyMuPDFParser
from crossbid.models.company import CompanyProfile

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = BACKEND_DIR / "scripts"
SCRIPT_PATH = SCRIPTS_DIR / "build_demo_company_pack.py"
PACK_DIR = BACKEND_DIR / "tests" / "fixtures" / "company"
DOCUMENTS_DIR = PACK_DIR / "documents"
PROFILE_PATH = PACK_DIR / "profile.yaml"
SOURCES_PATH = PACK_DIR / "SOURCES.md"

# The story's list, one file each, plus the Eigenerklaerung the DE tender asks for by name.
EXPECTED_DOCUMENTS = (
    "Angebotszusammenfassung_2023_ISMS_Beratung.pdf",
    "Angebotszusammenfassung_2024_IPv6_Migration.pdf",
    "Angebotszusammenfassung_2025_Netzwerkbetrieb.pdf",
    "Betriebshaftpflichtversicherung_Bestaetigung.pdf",
    "Eigenerklaerung_Umsatz_und_Beschaeftigte.pdf",
    "Handelsregisterauszug.pdf",
    "Referenzschreiben_Landesamt_Musterland.pdf",
    "Referenzschreiben_Stadtwerke_Musterstadt.pdf",
    "Unbedenklichkeitsbescheinigung_Finanzamt.pdf",
    "Zertifikat_ISO_IEC_27001_2022.pdf",
)

DEMO_MARKER = "MUSTERDOKUMENT"
STORY = "S6.3"
FIXTURE_SIZE_CEILING_BYTES = 15 * 1024 * 1024  # S6.1's ceiling, applied to this pack too.

# ADR-0002's measured thresholds from tests/fixtures/tenders/de/.
DE_MIN_TURNOVER_EUR = 3_000_000.0
DE_MIN_STAFF_FTE = 29.0

# The day the pack was built. `is_valid_on` is a pure function of this, so the expiry test
# says what it means instead of drifting with the clock.
PACK_BUILD_DATE = date(2026, 9, 11)


@pytest.fixture(scope="module")
def generator() -> Iterator[ModuleType]:
    """`scripts/build_demo_company_pack.py` as a module, imported by path."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec = importlib.util.spec_from_file_location("build_demo_company_pack", SCRIPT_PATH)
        assert spec is not None and spec.loader is not None, SCRIPT_PATH
        module = importlib.util.module_from_spec(spec)
        sys.modules["build_demo_company_pack"] = module
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.path.remove(str(SCRIPTS_DIR))
        sys.modules.pop("build_demo_company_pack", None)


@pytest.fixture(scope="module")
def profile() -> CompanyProfile:
    return CompanyProfile.model_validate(
        yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    )


@pytest.fixture(scope="module")
def built(generator: ModuleType) -> Mapping[str, bytes]:
    """One build, shared: rendering ten PDFs per test would be the slowest unit test here."""
    return generator.build_documents(generator.load_profile())


@pytest.fixture(scope="module")
def page_text() -> Mapping[str, tuple[str, ...]]:
    """Every committed PDF read back through the repo's own parser, page by page."""
    parser = PyMuPDFParser()
    return {
        name: tuple(
            page.text for page in parser.parse(DOCUMENTS_DIR / name, document_id=name).pages
        )
        for name in EXPECTED_DOCUMENTS
    }


# ------------------------------------------------------------------------------- profile


def test_profile_yaml_parses_into_a_company_profile(profile: CompanyProfile) -> None:
    assert profile.name == "Beispiel IT Services GmbH"
    assert profile.country == "de"
    assert profile.legal_form == "gmbh"
    assert profile.language == "de"


def test_profile_records_three_years_of_turnover(profile: CompanyProfile) -> None:
    years = [entry.year for entry in profile.turnover]

    assert len(years) == 3
    assert years == sorted(years), "oldest first, so a reader sees the trend"
    assert {entry.currency for entry in profile.turnover} == {"EUR"}


def test_turnover_clears_the_de_tender_threshold(profile: CompanyProfile) -> None:
    # Supported, so the no-go below has exactly one cause and the walkthrough is legible.
    assert all(entry.amount >= DE_MIN_TURNOVER_EUR for entry in profile.turnover)


def test_staff_misses_the_de_tender_minimum(profile: CompanyProfile) -> None:
    # The single genuine gap the S7.4 no-go walkthrough is built on.
    assert profile.staff_fte is not None
    assert profile.staff_fte < DE_MIN_STAFF_FTE


def test_exactly_one_certificate_is_expired(profile: CompanyProfile) -> None:
    expired = [held for held in profile.certificates if not held.is_valid_on(PACK_BUILD_DATE)]

    assert [held.name for held in expired] == ["Freistellungsbescheinigung nach § 48b EStG"]


def test_the_information_security_certificate_is_valid(profile: CompanyProfile) -> None:
    iso = next(held for held in profile.certificates if held.name.startswith("ISO/IEC 27001"))

    assert iso.is_valid_on(PACK_BUILD_DATE)


def test_every_certificate_names_an_invented_issuer(profile: CompanyProfile) -> None:
    # No real registrar, tax office, certification body or insurer may appear anywhere.
    for held in profile.certificates:
        assert held.issuer is not None
        assert "fiktiv" in held.issuer.lower(), held.name


# ----------------------------------------------------------------------------- the files


def test_pack_holds_every_document_the_story_names() -> None:
    assert sorted(path.name for path in DOCUMENTS_DIR.glob("*.pdf")) == list(EXPECTED_DOCUMENTS)


def test_pack_stays_well_under_the_fixture_ceiling() -> None:
    total = sum(path.stat().st_size for path in PACK_DIR.rglob("*") if path.is_file())

    assert total < FIXTURE_SIZE_CEILING_BYTES


def test_committed_pack_matches_a_fresh_build(built: Mapping[str, bytes]) -> None:
    """A stale fixture fails here rather than in a demo. Rebuild with `make demo-pack`."""
    on_disk = {
        name: hashlib.sha256((DOCUMENTS_DIR / name).read_bytes()).hexdigest()
        for name in EXPECTED_DOCUMENTS
    }
    rebuilt = {name: hashlib.sha256(body).hexdigest() for name, body in built.items()}

    assert rebuilt == on_disk


def test_two_builds_are_byte_identical(
    generator: ModuleType, built: Mapping[str, bytes]
) -> None:
    """PyMuPDF stamps a fresh trailer /ID per save; the generator has to suppress it."""
    again = generator.build_documents(generator.load_profile())

    assert dict(again) == dict(built)


def test_documents_are_multi_page_where_a_real_one_would_be(
    page_text: Mapping[str, tuple[str, ...]],
) -> None:
    for name, pages in page_text.items():
        assert len(pages) >= 2, name
    assert len(page_text["Handelsregisterauszug.pdf"]) >= 3


# -------------------------------------------------------------------- what is on the page


def test_every_page_has_a_text_layer(page_text: Mapping[str, tuple[str, ...]]) -> None:
    for name, pages in page_text.items():
        assert all(has_extractable_text(text) for text in pages), name


def test_every_page_carries_the_demo_marker(page_text: Mapping[str, tuple[str, ...]]) -> None:
    for name, pages in page_text.items():
        for number, text in enumerate(pages, start=1):
            assert DEMO_MARKER in text, f"{name} page {number}"
            assert "kein amtliches Dokument" in text, f"{name} page {number}"


def test_every_page_names_the_repository_and_the_story(
    page_text: Mapping[str, tuple[str, ...]],
) -> None:
    for name, pages in page_text.items():
        for number, text in enumerate(pages, start=1):
            assert STORY in text, f"{name} page {number}"
            assert "tests/fixtures/company" in text, f"{name} page {number}"


@pytest.mark.parametrize(
    "term",
    [
        "ISO/IEC 27001:2022",
        "Informationssicherheits-Managementsystem",
        "Vertraulichkeit, Integrität und Verfügbarkeit",
    ],
)
def test_iso_certificate_uses_the_wording_a_cross_border_query_must_match(
    page_text: Mapping[str, tuple[str, ...]], term: str
) -> None:
    """A French tender asks for information-security certification; this is what it finds."""
    assert term in "\n".join(page_text["Zertifikat_ISO_IEC_27001_2022.pdf"])


@pytest.mark.parametrize(
    ("document", "term"),
    [
        ("Handelsregisterauszug.pdf", "Handelsregisterauszug"),
        ("Unbedenklichkeitsbescheinigung_Finanzamt.pdf", "Unbedenklichkeitsbescheinigung"),
        (
            "Unbedenklichkeitsbescheinigung_Finanzamt.pdf",
            "Freistellungsbescheinigung nach § 48b EStG",
        ),
        ("Betriebshaftpflichtversicherung_Bestaetigung.pdf", "Betriebshaftpflichtversicherung"),
        ("Referenzschreiben_Landesamt_Musterland.pdf", "Referenzschreiben"),
        ("Referenzschreiben_Stadtwerke_Musterstadt.pdf", "Referenzschreiben"),
        ("Eigenerklaerung_Umsatz_und_Beschaeftigte.pdf", "Eigenerklärung"),
        ("Eigenerklaerung_Umsatz_und_Beschaeftigte.pdf", "Personentage"),
    ],
)
def test_documents_use_the_term_a_procurement_officer_would_write(
    page_text: Mapping[str, tuple[str, ...]], document: str, term: str
) -> None:
    assert term in "\n".join(page_text[document])


def test_every_document_marks_its_issuer_as_invented(
    page_text: Mapping[str, tuple[str, ...]],
) -> None:
    for name, pages in page_text.items():
        assert "fiktiv" in "\n".join(pages).lower(), name


def test_turnover_figures_on_the_page_come_from_the_profile(
    profile: CompanyProfile, page_text: Mapping[str, tuple[str, ...]]
) -> None:
    """The one place profile and evidence could contradict each other."""
    body = "\n".join(page_text["Eigenerklaerung_Umsatz_und_Beschaeftigte.pdf"])

    for entry in profile.turnover:
        assert f"{entry.year}" in body
        assert (
            f"{entry.amount:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".") in body
        )


def test_staff_figures_on_the_page_come_from_the_profile(
    profile: CompanyProfile, page_text: Mapping[str, tuple[str, ...]]
) -> None:
    body = "\n".join(page_text["Eigenerklaerung_Umsatz_und_Beschaeftigte.pdf"])
    assert profile.staff_fte is not None and profile.staff_fte_relevant is not None

    assert f"{profile.staff_fte:.1f}".replace(".", ",") in body
    assert f"{profile.staff_fte_relevant:.1f}".replace(".", ",") in body


def test_each_reference_states_a_volume_the_de_tender_would_accept(
    page_text: Mapping[str, tuple[str, ...]],
) -> None:
    """>= 25 abgerechnete Personentage is the DE fixture's per-reference minimum."""
    for name in EXPECTED_DOCUMENTS:
        if not name.startswith(("Referenzschreiben", "Angebotszusammenfassung")):
            continue
        assert "Personentage" in "\n".join(page_text[name]), name


# ------------------------------------------------------------------------------ SOURCES


def test_sources_declares_the_pack_synthetic_in_its_first_line() -> None:
    lines = [line for line in SOURCES_PATH.read_text(encoding="utf-8").splitlines() if line]

    assert "synthetisch" in lines[1].lower() or "synthetic" in lines[1].lower()


def test_sources_names_the_generator_and_every_document() -> None:
    text = SOURCES_PATH.read_text(encoding="utf-8")

    assert "scripts/build_demo_company_pack.py" in text
    for name in EXPECTED_DOCUMENTS:
        assert name in text


# ----------------------------------------------------------------------------- generator


def test_check_mode_is_quiet_on_a_current_pack(generator: ModuleType) -> None:
    assert (
        generator.stale_documents(
            DOCUMENTS_DIR, generator.build_documents(generator.load_profile())
        )
        == ()
    )


def test_check_mode_names_a_stale_file(
    generator: ModuleType, built: Mapping[str, bytes], tmp_path: Path
) -> None:
    name = EXPECTED_DOCUMENTS[0]
    (tmp_path / name).write_bytes(b"%PDF-1.7 not what the generator produces")

    stale = generator.stale_documents(tmp_path, built)

    assert name in stale
    assert len(stale) == len(EXPECTED_DOCUMENTS)  # the other nine are missing entirely


def test_write_pack_round_trips(
    generator: ModuleType, built: Mapping[str, bytes], tmp_path: Path
) -> None:
    written = generator.write_pack(tmp_path, built)

    assert sorted(path.name for path in written) == list(EXPECTED_DOCUMENTS)
    assert generator.stale_documents(tmp_path, built) == ()


def test_latin_1_is_enforced_because_the_base_14_fonts_stop_there(
    generator: ModuleType,
) -> None:
    """An em dash silently renders as `?`, which would break the marker test at a distance."""
    with pytest.raises(generator.BuildError, match="Latin-1"):
        generator.require_latin_1("MUSTERDOKUMENT — Demodaten")


def test_overflowing_a_page_is_a_build_error_not_a_lost_paragraph(
    generator: ModuleType,
) -> None:
    with pytest.raises(generator.BuildError, match="does not fit"):
        generator.build_pdf(
            (generator.Page(heading="Zu lang", blocks=(("p", "Wort " * 4000),)),)
        )


def test_content_yaml_lists_exactly_the_committed_documents(
    generator: ModuleType, profile: CompanyProfile
) -> None:
    assert sorted(generator.load_content(profile)) == list(EXPECTED_DOCUMENTS)


def test_every_placeholder_the_content_uses_is_filled(
    generator: ModuleType, profile: CompanyProfile
) -> None:
    """`load_content` raises on an unknown one, so a clean load is the assertion."""
    rendered = generator.load_content(profile)

    for name, pages in rendered.items():
        for page in pages:
            for _, text in page.blocks:
                assert "{" not in text and "}" not in text, name


def _content_file(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "documents.yaml"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("[]", "non-empty list"),
        ("- pages: []\n", "needs a `file` name"),
        ("- file: a.pdf\n  pages: []\n", "non-empty list"),
        ("- file: a.pdf\n  pages:\n  - blocks: [{p: x}]\n", "needs a `heading`"),
        ("- file: a.pdf\n  pages:\n  - heading: H\n    blocks: []\n", "non-empty list"),
        (
            "- file: a.pdf\n  pages:\n  - heading: H\n    blocks: [{q: x}]\n",
            "unknown block style",
        ),
        (
            "- file: a.pdf\n  pages:\n  - heading: H\n    blocks: [{p: '{nope}'}]\n",
            "placeholder",
        ),
        (
            "- file: a.pdf\n  pages:\n  - heading: H\n    blocks: [{p: x}]\n"
            "- file: a.pdf\n  pages:\n  - heading: H\n    blocks: [{p: x}]\n",
            "listed twice",
        ),
    ],
)
def test_malformed_content_is_a_build_error(
    generator: ModuleType, profile: CompanyProfile, tmp_path: Path, body: str, message: str
) -> None:
    """A silently dropped page would be a silently missing piece of evidence."""
    with pytest.raises(generator.BuildError, match=message):
        generator.load_content(profile, _content_file(tmp_path, body))


def test_a_profile_without_headcount_cannot_be_rendered(
    generator: ModuleType, profile: CompanyProfile
) -> None:
    without = profile.model_copy(update={"staff_fte": None})

    with pytest.raises(generator.BuildError, match="staff_fte"):
        generator.fields(without)


def test_a_profile_missing_a_certificate_cannot_be_rendered(
    generator: ModuleType, profile: CompanyProfile
) -> None:
    without = profile.model_copy(update={"certificates": ()})

    with pytest.raises(generator.BuildError, match="ISO/IEC 27001"):
        generator.fields(without)


def test_main_check_reports_the_committed_pack_as_current(
    generator: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    assert generator.main(["--check"]) == 0
    assert "current" in capsys.readouterr().out
