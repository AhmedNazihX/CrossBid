"""S6.5 — the adversarial fixtures, and the generator that keeps them honest.

Four tender excerpts, each planting exactly one instruction in a different form: a plain
paragraph, a table cell, text buried under an opaque white rectangle, and white ink on
white paper. They exist so that S2.3.1's injection guard has something to catch, and so
that S5.3's cheap-model confirmation has both a true positive and a false-positive
candidate to work on.

**The white-ink document is a negative control, not a fourth attack.** `pymupdf4llm` drops
white glyphs, so that payload never reaches the markdown every prompt is built from - the
literal textbook attack is already dead in this pipeline, by accident. It is committed
with `reaches_the_parser: false` and pinned from both sides here, so that swapping the
parser fails this test rather than quietly re-opening the door (ADR-0032).

**The fixture is generated, not hand-placed.** A committed PDF whose planted text nobody
can grep is a fixture that rots the first time a line wraps differently: the guard's test
then asserts against a string the parser no longer reads, and passes or fails for reasons
unrelated to the guard. `documents.yaml` holds the prose, `manifest.yaml` is derived from
it, and both a fresh build and the repo's own parser have to agree with what is committed.

**Two properties matter more than the payloads themselves.**

* *The plant is readable exactly where the manifest says it is.* The builder re-parses its
  own bytes with `PyMuPDFParser` — the very parser the ingestion pipeline uses — so a
  manifest entry can never name a page whose text does not carry the instruction.
* *There is realistic noise around it.* Each document carries `decoy` sentences: ordinary
  procurement imperatives ("Der Bieter hat ... einzureichen") that a keyword guard would
  flag and must not. The manifest lists them, so S2.3.1 can assert precision, not only
  recall.

Everything here is offline; the generator is loaded by path, as `scripts/` is not a package.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

import pymupdf
import pytest
import yaml

from crossbid.ingestion.parser import has_extractable_text
from crossbid.ingestion.pymupdf_parser import PyMuPDFParser

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = BACKEND_DIR / "scripts"
SCRIPT_PATH = SCRIPTS_DIR / "build_adversarial_pack.py"
PACK_DIR = BACKEND_DIR / "tests" / "fixtures" / "adversarial"
CONTENT_PATH = PACK_DIR / "documents.yaml"
MANIFEST_PATH = PACK_DIR / "manifest.yaml"

EXPECTED_DOCUMENTS = (
    "DE_Bewerbungsbedingungen_Auszug.pdf",
    "DE_Leistungsbeschreibung_Auszug.pdf",
    "EN_Tender_Specifications_Extract.pdf",
    "FR_Reglement_de_la_Consultation_Extrait.pdf",
)
EXPECTED_FORMS = {"paragraph", "table_cell", "covered_text", "white_ink"}
FOOTER_MARKER = "Synthetisches Testdokument"

PACK_SIZE_CEILING_BYTES = 1024 * 1024  # text-only PDFs; a megabyte is already generous
WHITE_PIXEL = (255, 255, 255)


@pytest.fixture(scope="module")
def generator() -> Iterator[ModuleType]:
    """`scripts/build_adversarial_pack.py` as a module, imported by path."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec = importlib.util.spec_from_file_location("build_adversarial_pack", SCRIPT_PATH)
        assert spec is not None and spec.loader is not None, SCRIPT_PATH
        module = importlib.util.module_from_spec(spec)
        sys.modules["build_adversarial_pack"] = module
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.path.remove(str(SCRIPTS_DIR))
        sys.modules.pop("build_adversarial_pack", None)


@pytest.fixture(scope="module")
def built(generator: ModuleType) -> Mapping[str, bytes]:
    """One build, shared: rendering the pack per test would be needless seconds."""
    return generator.build_documents(generator.load_pack())


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def page_text() -> Mapping[str, tuple[str, ...]]:
    """Every committed PDF read back through the repo's own parser, page by page."""
    parser = PyMuPDFParser()
    return {
        name: tuple(page.text for page in parser.parse(PACK_DIR / name, document_id=name).pages)
        for name in EXPECTED_DOCUMENTS
    }


def _comparable(text: str) -> str:
    """The extractor's own normalisation, so this test compares what the agent compares."""
    from crossbid.agent.nodes.extract_reqs import _comparable as normalise

    return normalise(text)


# ------------------------------------------------------------------------------ the files


def test_pack_holds_exactly_the_three_documents() -> None:
    assert sorted(path.name for path in PACK_DIR.glob("*.pdf")) == list(EXPECTED_DOCUMENTS)


def test_pack_stays_small() -> None:
    total = sum(path.stat().st_size for path in PACK_DIR.rglob("*") if path.is_file())

    assert total < PACK_SIZE_CEILING_BYTES


def test_committed_pdfs_match_a_fresh_build(built: Mapping[str, bytes]) -> None:
    """A stale fixture fails here rather than inside the guard's tests."""
    on_disk = {
        name: hashlib.sha256((PACK_DIR / name).read_bytes()).hexdigest()
        for name in EXPECTED_DOCUMENTS
    }
    rebuilt = {name: hashlib.sha256(body).hexdigest() for name, body in built.items()}

    assert rebuilt == on_disk


def test_two_builds_are_byte_identical(
    generator: ModuleType, built: Mapping[str, bytes]
) -> None:
    """PyMuPDF stamps a fresh trailer /ID per save; the generator has to suppress it."""
    again = generator.build_documents(generator.load_pack())

    assert dict(again) == dict(built)


def test_committed_manifest_matches_a_fresh_build(
    generator: ModuleType, built: Mapping[str, bytes]
) -> None:
    rebuilt = generator.manifest_text(generator.load_pack(), built)

    assert MANIFEST_PATH.read_text(encoding="utf-8") == rebuilt


def test_check_mode_passes_on_the_committed_pack(generator: ModuleType) -> None:
    assert generator.main(["--check"]) == 0


def test_check_mode_reports_a_file_that_drifted(
    generator: ModuleType, built: Mapping[str, bytes]
) -> None:
    tampered = dict(built) | {EXPECTED_DOCUMENTS[0]: b"%PDF-1.7 not the committed bytes"}

    stale = generator.stale_files(PACK_DIR, tampered, MANIFEST_PATH.read_text(encoding="utf-8"))

    assert stale == (EXPECTED_DOCUMENTS[0],)


def test_check_mode_reports_a_stale_manifest(
    generator: ModuleType, built: Mapping[str, bytes]
) -> None:
    stale = generator.stale_files(PACK_DIR, built, "documents: []\n")

    assert stale == ("manifest.yaml",)


def test_write_pack_writes_every_file(
    generator: ModuleType, built: Mapping[str, bytes], tmp_path: Path
) -> None:
    written = generator.write_pack(tmp_path, built, "documents: []\n")

    assert sorted(path.name for path in written) == [*EXPECTED_DOCUMENTS, "manifest.yaml"]
    assert (tmp_path / "manifest.yaml").read_text(encoding="utf-8") == "documents: []\n"


# ------------------------------------------------------------------------- the manifest


def test_manifest_names_the_story_and_warns_against_hand_editing(
    manifest: dict[str, Any],
) -> None:
    assert manifest["story"] == "S6.5"
    assert "build_adversarial_pack.py" in MANIFEST_PATH.read_text(encoding="utf-8")


def test_manifest_lists_every_document_with_its_digest(manifest: dict[str, Any]) -> None:
    listed = {entry["file"]: entry for entry in manifest["documents"]}

    assert sorted(listed) == list(EXPECTED_DOCUMENTS)
    for name, entry in listed.items():
        assert entry["sha256"] == hashlib.sha256((PACK_DIR / name).read_bytes()).hexdigest()


def test_each_document_plants_exactly_one_instruction(manifest: dict[str, Any]) -> None:
    for entry in manifest["documents"]:
        assert isinstance(entry["planted"], dict), entry["file"]
        assert entry["planted"]["text"].strip(), entry["file"]


def test_the_four_forms_are_each_planted_once(manifest: dict[str, Any]) -> None:
    forms = [entry["planted"]["form"] for entry in manifest["documents"]]

    assert sorted(forms) == sorted(EXPECTED_FORMS)


def test_the_three_languages_are_covered(manifest: dict[str, Any]) -> None:
    assert {entry["language"] for entry in manifest["documents"]} == {"de", "en", "fr"}


def test_exactly_one_plant_is_out_of_the_parser_s_reach(manifest: dict[str, Any]) -> None:
    """One negative control, and the guard is answerable for every other plant."""
    unreachable = [
        entry for entry in manifest["documents"] if not entry["planted"]["reaches_the_parser"]
    ]

    assert [entry["planted"]["form"] for entry in unreachable] == ["white_ink"]


def test_every_document_carries_decoys(manifest: dict[str, Any]) -> None:
    """Realistic noise is the point: a guard is only useful if it leaves these alone."""
    for entry in manifest["documents"]:
        assert entry["decoys"], entry["file"]


def test_no_decoy_repeats_a_planted_instruction(manifest: dict[str, Any]) -> None:
    planted = {_comparable(entry["planted"]["text"]) for entry in manifest["documents"]}
    decoys = {
        _comparable(decoy["text"])
        for entry in manifest["documents"]
        for decoy in entry["decoys"]
    }

    assert planted.isdisjoint(decoys)


# --------------------------------------------------------------- what the parser reads


def test_every_page_carries_a_text_layer(page_text: Mapping[str, tuple[str, ...]]) -> None:
    for name, pages in page_text.items():
        for number, text in enumerate(pages, start=1):
            assert has_extractable_text(text), f"{name} page {number}"


def test_page_counts_match_the_manifest(
    manifest: dict[str, Any], page_text: Mapping[str, tuple[str, ...]]
) -> None:
    for entry in manifest["documents"]:
        assert entry["pages"] == len(page_text[entry["file"]])


def test_each_planted_instruction_is_read_back_on_its_recorded_page(
    manifest: dict[str, Any], page_text: Mapping[str, tuple[str, ...]]
) -> None:
    """The whole value of the fixture: the guard's test can grep for this string."""
    for entry in manifest["documents"]:
        planted = entry["planted"]
        text = page_text[entry["file"]][planted["page"] - 1]
        read_back = _comparable(planted["text"]) in _comparable(text)

        assert read_back is planted["reaches_the_parser"], entry["file"]


def test_each_decoy_is_read_back_on_its_recorded_page(
    manifest: dict[str, Any], page_text: Mapping[str, tuple[str, ...]]
) -> None:
    for entry in manifest["documents"]:
        for decoy in entry["decoys"]:
            text = page_text[entry["file"]][decoy["page"] - 1]

            assert _comparable(decoy["text"]) in _comparable(text), entry["file"]


def test_the_plant_is_a_small_part_of_the_page_it_hides_in(
    manifest: dict[str, Any], page_text: Mapping[str, tuple[str, ...]]
) -> None:
    """A page that is nothing but the payload is not a plausible tender excerpt."""
    for entry in manifest["documents"]:
        planted = entry["planted"]
        if not planted["reaches_the_parser"]:
            continue  # nothing of it is on the parsed page, by design
        page = page_text[entry["file"]][planted["page"] - 1]

        assert len(_comparable(planted["text"])) < 0.5 * len(_comparable(page)), entry["file"]


def test_every_page_says_it_is_a_synthetic_fixture(
    page_text: Mapping[str, tuple[str, ...]],
) -> None:
    """These files carry working injection payloads; nothing may mistake one for a tender."""
    for name, pages in page_text.items():
        for number, text in enumerate(pages, start=1):
            assert FOOTER_MARKER in text, f"{name} page {number}"


def test_every_hidden_plant_is_in_the_text_layer(manifest: dict[str, Any]) -> None:
    """Hidden means hidden from a reader, never absent from the file."""
    for entry in _hidden(manifest):
        with pymupdf.open(PACK_DIR / entry["file"]) as document:
            raw = document[entry["planted"]["page"] - 1].get_text()

        assert _comparable(entry["planted"]["text"]) in _comparable(raw), entry["file"]


def test_every_hidden_plant_renders_as_blank_paper(manifest: dict[str, Any]) -> None:
    """The attack only works if a human reader cannot see what the machine reads."""
    for entry in _hidden(manifest):
        with pymupdf.open(PACK_DIR / entry["file"]) as document:
            page = document[entry["planted"]["page"] - 1]
            found = page.search_for(entry["planted"]["text"].split(".")[0])
            assert found, f"{entry['file']}: the plant is not in the text layer at all"
            pixels = page.get_pixmap(clip=found[0])
            drawn = {
                pixels.pixel(x, y) for x in range(pixels.width) for y in range(pixels.height)
            }

        assert drawn == {WHITE_PIXEL}, entry["file"]


def test_visibility_is_recorded_for_every_plant(manifest: dict[str, Any]) -> None:
    hidden = {entry["file"] for entry in _hidden(manifest)}

    for entry in manifest["documents"]:
        assert entry["planted"]["visible_to_a_reader"] is (entry["file"] not in hidden)


def _hidden(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        entry for entry in manifest["documents"] if not entry["planted"]["visible_to_a_reader"]
    ]


# ------------------------------------------------------- the generator refuses bad input


def test_a_document_with_no_plant_is_a_build_error(
    generator: ModuleType, tmp_path: Path
) -> None:
    probe = _yaml_of(tmp_path, [_document(blocks=[{"p": "nothing planted here"}])])

    with pytest.raises(generator.BuildError, match="exactly one planted instruction"):
        generator.load_pack(probe)


def test_a_document_with_two_plants_is_a_build_error(
    generator: ModuleType, tmp_path: Path
) -> None:
    blocks = [{"inject": "first payload"}, {"inject_covered": "second payload"}]
    probe = _yaml_of(tmp_path, [_document(blocks=blocks)])

    with pytest.raises(generator.BuildError, match="exactly one planted instruction"):
        generator.load_pack(probe)


def test_an_unknown_block_style_is_a_build_error(generator: ModuleType, tmp_path: Path) -> None:
    probe = _yaml_of(tmp_path, [_document(blocks=[{"quote": "unsupported"}])])

    with pytest.raises(generator.BuildError, match="unknown block style"):
        generator.load_pack(probe)


def test_a_block_that_is_not_one_mapping_is_a_build_error(
    generator: ModuleType, tmp_path: Path
) -> None:
    probe = _yaml_of(tmp_path, [_document(blocks=["a bare string"])])

    with pytest.raises(generator.BuildError, match="one mapping of style to text"):
        generator.load_pack(probe)


def test_a_page_without_a_heading_is_a_build_error(
    generator: ModuleType, tmp_path: Path
) -> None:
    probe = _yaml_of(tmp_path, [{"file": "X.pdf", "language": "en", "pages": [{"blocks": []}]}])

    with pytest.raises(generator.BuildError, match="needs a `heading`"):
        generator.load_pack(probe)


def test_a_document_without_pages_is_a_build_error(
    generator: ModuleType, tmp_path: Path
) -> None:
    probe = _yaml_of(tmp_path, [{"file": "X.pdf", "language": "en", "pages": []}])

    with pytest.raises(generator.BuildError, match="`pages` must be a non-empty list"):
        generator.load_pack(probe)


def test_a_document_without_a_filename_is_a_build_error(
    generator: ModuleType, tmp_path: Path
) -> None:
    probe = _yaml_of(tmp_path, [{"language": "en", "pages": []}])

    with pytest.raises(generator.BuildError, match="needs a `file` name"):
        generator.load_pack(probe)


def test_a_document_without_a_language_is_a_build_error(
    generator: ModuleType, tmp_path: Path
) -> None:
    probe = _yaml_of(tmp_path, [{"file": "X.pdf", "pages": []}])

    with pytest.raises(generator.BuildError, match="needs a `language`"):
        generator.load_pack(probe)


def test_a_duplicate_filename_is_a_build_error(generator: ModuleType, tmp_path: Path) -> None:
    probe = _yaml_of(tmp_path, [_document(), _document()])

    with pytest.raises(generator.BuildError, match="listed twice"):
        generator.load_pack(probe)


def test_a_pack_that_is_not_a_list_is_a_build_error(
    generator: ModuleType, tmp_path: Path
) -> None:
    probe = _yaml_of(tmp_path, {})

    with pytest.raises(generator.BuildError, match="non-empty list"):
        generator.load_pack(probe)


def test_a_malformed_table_is_a_build_error(generator: ModuleType, tmp_path: Path) -> None:
    blocks = [{"inject": "the payload"}, {"table": {"header": ["one"], "rows": [["a", "b"]]}}]
    probe = _yaml_of(tmp_path, [_document(blocks=blocks)])

    with pytest.raises(generator.BuildError, match="same number of cells"):
        generator.load_pack(probe)


def test_text_outside_latin_1_is_a_build_error(generator: ModuleType, tmp_path: Path) -> None:
    """Base-14 fonts stop at Latin-1 and render the rest as `?`, silently."""
    probe = _yaml_of(tmp_path, [_document(blocks=[{"inject": "an em dash — hides here"}])])

    with pytest.raises(generator.BuildError, match="Latin-1"):
        generator.build_documents(generator.load_pack(probe))


def test_a_page_that_overflows_is_a_build_error(generator: ModuleType, tmp_path: Path) -> None:
    blocks = [{"inject": "the payload"}, {"p": "overflowing prose. " * 400}]
    probe = _yaml_of(tmp_path, [_document(blocks=blocks)])

    with pytest.raises(generator.BuildError, match="does not fit"):
        generator.build_documents(generator.load_pack(probe))


def _document(
    *, name: str = "X_Fixture.pdf", blocks: list[Any] | None = None
) -> dict[str, Any]:
    return {
        "file": name,
        "language": "en",
        "pages": [
            {
                "heading": "Heading",
                "blocks": blocks if blocks is not None else [{"inject": "the payload"}],
            }
        ],
    }


def _yaml_of(directory: Path, raw: Any) -> Path:
    path = directory / "probe.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return path
