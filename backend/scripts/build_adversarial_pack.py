"""S6.5 — build the adversarial tender excerpts the injection guard is tested against.

    uv run python scripts/build_adversarial_pack.py           # render and write
    uv run python scripts/build_adversarial_pack.py --check   # verify only, write nothing

S2.3.1 has to flag text that tries to instruct the agent and keep it out of every prompt.
Nothing can be said about a guard without documents that attack it, and a real tender that
attacks us is not something we can go and find. So the attack is written here, in three
forms a real one would take:

* a **plain paragraph** addressed to "automatisierte Auswertungssysteme", the form that
  needs no trick at all because most readers skim;
* a **table cell**, where the payload sits in the column a reader scans for evidence;
* **covered text** — black glyphs painted first and then hidden under an opaque white
  rectangle, so a reader sees blank paper and the text layer is untouched;
* **white ink** — the textbook white-on-white paragraph, which is here as a *negative
  control* rather than as an attack the guard must catch.

**The white-ink document is the one worth explaining.** `pymupdf4llm` drops white glyphs,
so the payload never reaches the markdown the chunker and every prompt are built from —
measured, not assumed: `page.get_text()` returns it and `PyMuPDFParser` does not. The
literal form of the attack is therefore already dead in this pipeline, by accident rather
than by design, and a fixture whose plant no guard can ever see would have quietly tested
nothing. So it is committed with `reaches_the_parser: false`, the builder asserts both
halves of that (present in the raw text layer, absent from the parsed page), and swapping
PyMuPDF for Docling breaks this build rather than silently re-opening the door. The
attack the guard must actually catch is the covered-text document next to it, which is
just as invisible to a reader and fully present in what the parser reads.

**The prose around the payload is not filler.** A guard measured only against payloads has
no precision: every procurement document on earth says "der Bieter hat ... einzureichen",
and a keyword rule that flags those flags the entire pack. Each document therefore carries
`decoy` blocks — legitimate imperative sentences — and the manifest lists them, so S2.3.1
can be held to leaving them alone as firmly as to catching the plant.

**`manifest.yaml` is generated, never hand-written.** A hand-kept manifest is a promise
about a binary nobody can read in a diff, and the first time a line wraps differently the
guard's test greps for a string the parser no longer produces. Here the page number comes
from the layout and the text is proved readable: `build_documents` re-parses its own bytes
with `PyMuPDFParser` — the parser the ingestion pipeline itself uses — and refuses to
return bytes whose planted or decoy text it cannot find, under `extract_reqs`' own
normalisation, on the page the manifest is about to name.

**Every page says it is synthetic.** These files carry working prompt-injection payloads;
a footer on every page names this repository and the story, so no one can mistake one for
a real notice. The footer is constant across every page of every document, plant or no
plant, so it cannot be the signal a guard learns instead of the attack.

**A second run must change nothing.** PyMuPDF stamps a fresh trailer `/ID` on every save,
which is the only source of nondeterminism in a text-only PDF; `no_new_id=True` suppresses
it and `set_metadata({})` drops the creation timestamp. `--check` asserts it, and so does
`tests/unit/test_adversarial_pack.py`.

Only the base-14 fonts are used, so no font file is embedded and the bytes stay tiny — but
those fonts stop at Latin-1 and PyMuPDF renders anything beyond it as `?` without failing,
which would quietly mutilate a payload. `require_latin_1` refuses the text instead.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pymupdf
import yaml

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    # `[tool.uv] package = false`, so `crossbid` is importable only via the project root.
    sys.path.insert(0, str(BACKEND_DIR))

from crossbid.agent.nodes.extract_reqs import (  # noqa: E402  (after the sys.path fix)
    _comparable,
)
from crossbid.ingestion.parser import has_extractable_text  # noqa: E402
from crossbid.ingestion.pymupdf_parser import PyMuPDFParser  # noqa: E402

PACK_DIR: Final = BACKEND_DIR / "tests" / "fixtures" / "adversarial"
CONTENT_PATH: Final = PACK_DIR / "documents.yaml"
MANIFEST_NAME: Final = "manifest.yaml"
STORY: Final = "S6.5"

FOOTER: Final = (
    "Synthetisches Testdokument mit absichtlich eingebauter Prompt-Injection - "
    "crossbid, tests/fixtures/adversarial, Story S6.5"
)

PAGE_WIDTH: Final = 595.0  # A4 portrait, in points
PAGE_HEIGHT: Final = 842.0
MARGIN: Final = 56.0
FOOTER_TOP: Final = PAGE_HEIGHT - 52.0
TOP: Final = 60.0

BODY_SIZE: Final = 10.0
HEADING_SIZE: Final = 15.0
SUBHEADING_SIZE: Final = 11.5
SMALL_SIZE: Final = 7.5
LINE_HEIGHT: Final = 1.35
BLOCK_GAP: Final = 9.0
CELL_PADDING: Final = 4.0

REGULAR: Final = "helv"
BOLD: Final = "hebo"

MUTED: Final = (0.35, 0.35, 0.38)
RULE: Final = (0.55, 0.55, 0.58)
HEADER_FILL: Final = (0.93, 0.93, 0.95)
WHITE: Final = (1.0, 1.0, 1.0)

PROSE_STYLES: Final = ("h", "p", "li", "decoy", "inject", "inject_covered", "inject_white_ink")
BLOCK_STYLES: Final = (*PROSE_STYLES, "table")


@dataclass(frozen=True)
class Form:
    """How one plant is hidden, and what that costs it downstream."""

    name: str
    technique: str
    visible_to_a_reader: bool
    reaches_the_parser: bool


PLANT_FORMS: Final[Mapping[str, Form]] = {
    "inject": Form(
        name="paragraph",
        technique="an ordinary paragraph, addressed to whatever machine is reading",
        visible_to_a_reader=True,
        reaches_the_parser=True,
    ),
    "table": Form(
        name="table_cell",
        technique="a table cell in the column a reviewer scans for required evidence",
        visible_to_a_reader=True,
        reaches_the_parser=True,
    ),
    "inject_covered": Form(
        name="covered_text",
        technique="black glyphs painted first, then hidden under an opaque white rectangle",
        visible_to_a_reader=False,
        reaches_the_parser=True,
    ),
    "inject_white_ink": Form(
        name="white_ink",
        technique="white glyphs on white paper - pymupdf4llm drops these before the guard",
        visible_to_a_reader=False,
        reaches_the_parser=False,
    ),
}


class BuildError(RuntimeError):
    """The pack cannot be rendered as written — a page overflows, or a glyph is unusable."""


@dataclass(frozen=True)
class Cell:
    """One table cell. `planted` marks the cell carrying the attack."""

    text: str
    planted: bool = False


@dataclass(frozen=True)
class Table:
    header: tuple[str, ...]
    rows: tuple[tuple[Cell, ...], ...]
    widths: tuple[float, ...]


@dataclass(frozen=True)
class Block:
    """One rendered block: prose in `text`, or a `table`. Never both."""

    style: str
    text: str = ""
    table: Table | None = None


@dataclass(frozen=True)
class Page:
    heading: str
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class Plant:
    """The one instruction a document plants, and where a reader would find it."""

    page: int
    form: Form
    text: str


@dataclass(frozen=True)
class Decoy:
    """A legitimate imperative sentence the guard must leave alone."""

    page: int
    text: str


@dataclass(frozen=True)
class Document:
    file: str
    language: str
    pages: tuple[Page, ...]
    plant: Plant
    decoys: tuple[Decoy, ...]


# --------------------------------------------------------------------------- text helpers


def require_latin_1(text: str) -> str:
    """Base-14 fonts encode Latin-1 and render everything else as `?`, silently."""
    try:
        text.encode("latin-1")
    except UnicodeEncodeError as error:
        raise BuildError(
            f"not representable in Latin-1, which the base-14 fonts stop at: {text!r}"
        ) from error
    return text


def _wrapped_height(text: str, width: float, *, font: str, size: float) -> float:
    """The height `text` needs at `width`, wrapping on spaces the way PyMuPDF does."""
    lines, current = 1, ""
    for word in require_latin_1(text).split():
        candidate = f"{current} {word}".strip()
        if current and pymupdf.get_text_length(candidate, fontname=font, fontsize=size) > width:
            lines, current = lines + 1, word
        else:
            current = candidate
    return lines * size * LINE_HEIGHT


# ------------------------------------------------------------------------------ rendering


def _draw(
    page: pymupdf.Page,
    rect: pymupdf.Rect,
    text: str,
    *,
    font: str,
    size: float,
    color: tuple[float, float, float] | None = None,
) -> float:
    """Write wrapped text into `rect` and return the y the next block starts at."""
    unused = page.insert_textbox(
        rect,
        require_latin_1(text),
        fontname=font,
        fontsize=size,
        lineheight=LINE_HEIGHT,
        color=color,
    )
    if unused < 0:
        raise BuildError(f"text does not fit the page: {text[:60]!r}")
    return rect.y1 - unused


def _body_rect(top: float, *, left: float = MARGIN, right: float = PAGE_WIDTH - MARGIN):
    return pymupdf.Rect(left, top, right, FOOTER_TOP - 6.0)


def _draw_footer(page: pymupdf.Page, number: int, total: int) -> None:
    """The one thing every page must carry: this is a fixture, and it bites."""
    page.draw_line(
        pymupdf.Point(MARGIN, FOOTER_TOP),
        pymupdf.Point(PAGE_WIDTH - MARGIN, FOOTER_TOP),
        color=MUTED,
        width=0.5,
    )
    page.insert_textbox(
        pymupdf.Rect(MARGIN, FOOTER_TOP + 5.0, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 16.0),
        require_latin_1(f"{FOOTER} - Seite {number} von {total}"),
        fontname=REGULAR,
        fontsize=SMALL_SIZE,
        color=MUTED,
    )


def _column_rects(widths: Sequence[float], top: float, height: float) -> list[pymupdf.Rect]:
    body = PAGE_WIDTH - 2 * MARGIN
    rects, left = [], MARGIN
    for share in widths:
        rects.append(pymupdf.Rect(left, top, left + body * share, top + height))
        left += body * share
    return rects


def _draw_row(
    page: pymupdf.Page,
    cells: Sequence[Cell],
    widths: Sequence[float],
    top: float,
    *,
    font: str,
    fill: tuple[float, float, float] | None,
) -> float:
    """One table row, sized by its tallest cell, ruled so the parser sees a table."""
    body = PAGE_WIDTH - 2 * MARGIN
    height = (
        max(
            _wrapped_height(
                cell.text, body * share - 2 * CELL_PADDING, font=font, size=BODY_SIZE
            )
            for cell, share in zip(cells, widths, strict=True)
        )
        + 2 * CELL_PADDING
    )
    if top + height > FOOTER_TOP - 6.0:
        raise BuildError(f"table row does not fit the page: {cells[0].text[:60]!r}")
    for rect, cell in zip(_column_rects(widths, top, height), cells, strict=True):
        page.draw_rect(rect, color=RULE, fill=fill, width=0.5)
        _draw(
            page,
            # The bottom padding is left inside the textbox: PyMuPDF needs a little more
            # room than the wrapped lines measure, and refuses the whole cell if it is short.
            pymupdf.Rect(
                rect.x0 + CELL_PADDING, rect.y0 + CELL_PADDING, rect.x1 - CELL_PADDING, rect.y1
            ),
            cell.text,
            font=font,
            size=BODY_SIZE,
        )
    return top + height


def _draw_table(page: pymupdf.Page, table: Table, top: float) -> float:
    cursor = _draw_row(
        page,
        tuple(Cell(text) for text in table.header),
        table.widths,
        top,
        font=BOLD,
        fill=HEADER_FILL,
    )
    for row in table.rows:
        cursor = _draw_row(page, row, table.widths, cursor, font=REGULAR, fill=None)
    return cursor


def _draw_covered(page: pymupdf.Page, top: float, text: str) -> float:
    """Paint the glyphs, then bury them under opaque white. Order is the whole trick."""
    bottom = _draw(page, _body_rect(top), text, font=REGULAR, size=BODY_SIZE)
    page.draw_rect(
        pymupdf.Rect(MARGIN - 2.0, top - 2.0, PAGE_WIDTH - MARGIN + 2.0, bottom + 2.0),
        color=WHITE,
        fill=WHITE,
        width=0,
    )
    return bottom


def _draw_block(page: pymupdf.Page, top: float, block: Block) -> float:
    """One block, returning the y after it. An unknown style cannot reach here."""
    if block.style == "h":
        return _draw(page, _body_rect(top), block.text, font=BOLD, size=SUBHEADING_SIZE)
    if block.style == "li":
        return _draw(
            page,
            _body_rect(top, left=MARGIN + 12.0),
            f"- {block.text}",
            font=REGULAR,
            size=BODY_SIZE,
        )
    if block.style == "inject_white_ink":
        # The textbook attack, and the one this pipeline already drops (see the docstring).
        return _draw(
            page, _body_rect(top), block.text, font=REGULAR, size=BODY_SIZE, color=WHITE
        )
    if block.style == "inject_covered":
        return _draw_covered(page, top, block.text)
    if block.style == "table":
        assert block.table is not None  # `_block` builds the two together
        return _draw_table(page, block.table, top)
    return _draw(page, _body_rect(top), block.text, font=REGULAR, size=BODY_SIZE)


def _render_page(page: pymupdf.Page, content: Page, number: int, total: int) -> None:
    cursor = _draw(page, _body_rect(TOP), content.heading, font=BOLD, size=HEADING_SIZE)
    cursor += BLOCK_GAP
    for block in content.blocks:
        cursor = _draw_block(page, cursor, block) + BLOCK_GAP
    _draw_footer(page, number, total)


def build_pdf(pages: Sequence[Page]) -> bytes:
    """Render `pages` to PDF bytes that two runs agree on, byte for byte."""
    document = pymupdf.open()
    try:
        for number, content in enumerate(pages, start=1):
            _render_page(
                document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT),
                content,
                number,
                len(pages),
            )
        # Cleared, not filled: a title or a creation date would either leak the build
        # clock or invite a reader to take the document for a genuine notice.
        document.set_metadata({})
        return document.tobytes(garbage=4, deflate=True, no_new_id=True)
    finally:
        document.close()


# ------------------------------------------------------------------------ content loading


def _cell(raw: object, where: str) -> Cell:
    """A cell is text, or `{inject: text}` — the table form of the attack."""
    if isinstance(raw, str):
        return Cell(raw.strip())
    if isinstance(raw, dict) and list(raw) == ["inject"]:
        return Cell(str(raw["inject"]).strip(), planted=True)
    raise BuildError(f"{where}: a table cell is text or `{{inject: text}}`, got {raw!r}")


def _table(raw: object, where: str) -> Table:
    if not isinstance(raw, dict):
        raise BuildError(f"{where}: a table is a mapping of header, rows and widths")
    header = tuple(str(text).strip() for text in raw.get("header") or ())
    rows = tuple(
        tuple(_cell(cell, where) for cell in row) for row in (raw.get("rows") or ()) if row
    )
    if not header or not rows:
        raise BuildError(f"{where}: a table needs a `header` and at least one row")
    if any(len(row) != len(header) for row in rows):
        raise BuildError(
            f"{where}: every table row needs the same number of cells as the header"
        )
    widths = tuple(float(share) for share in raw.get("widths") or ())
    return Table(header=header, rows=rows, widths=widths or (1.0 / len(header),) * len(header))


def _block(raw: object, where: str) -> Block:
    if not isinstance(raw, dict) or len(raw) != 1:
        raise BuildError(f"{where}: each block is one mapping of style to text, got {raw!r}")
    [(style, value)] = raw.items()
    if style not in BLOCK_STYLES:
        raise BuildError(f"{where}: unknown block style {style!r}, expected {BLOCK_STYLES}")
    if style == "table":
        return Block(style=style, table=_table(value, where))
    return Block(style=str(style), text=str(value).strip())


def _pages(raw: object, where: str) -> tuple[Page, ...]:
    if not isinstance(raw, list) or not raw:
        raise BuildError(f"{where}: `pages` must be a non-empty list")
    pages: list[Page] = []
    for number, entry in enumerate(raw, start=1):
        if not isinstance(entry, dict) or "heading" not in entry:
            raise BuildError(f"{where} page {number}: a page needs a `heading`")
        blocks = entry.get("blocks") or ()
        pages.append(
            Page(
                heading=str(entry["heading"]).strip(),
                blocks=tuple(_block(block, f"{where} page {number}") for block in blocks),
            )
        )
    return tuple(pages)


def _plants(pages: Sequence[Page]) -> tuple[Plant, ...]:
    """Every planted instruction, in reading order, whatever form it took."""
    found: list[Plant] = []
    for number, page in enumerate(pages, start=1):
        for block in page.blocks:
            if block.style in ("inject", "inject_covered", "inject_white_ink"):
                found.append(Plant(page=number, form=PLANT_FORMS[block.style], text=block.text))
            elif block.table is not None:
                found.extend(
                    Plant(page=number, form=PLANT_FORMS["table"], text=cell.text)
                    for row in block.table.rows
                    for cell in row
                    if cell.planted
                )
    return tuple(found)


def _decoys(pages: Sequence[Page]) -> tuple[Decoy, ...]:
    return tuple(
        Decoy(page=number, text=block.text)
        for number, page in enumerate(pages, start=1)
        for block in page.blocks
        if block.style == "decoy"
    )


def _document(raw: object, where: str) -> Document:
    if not isinstance(raw, dict) or not isinstance(raw.get("file"), str):
        raise BuildError(f"{where}: every document needs a `file` name, got {raw!r}")
    if not isinstance(raw.get("language"), str):
        raise BuildError(f"{where}: {raw['file']} needs a `language`")
    pages = _pages(raw.get("pages"), raw["file"])
    plants = _plants(pages)
    if len(plants) != 1:
        raise BuildError(
            f"{raw['file']}: a fixture carries exactly one planted instruction, found "
            f"{len(plants)} — one attack per document is what makes a failure legible"
        )
    return Document(
        file=raw["file"],
        language=raw["language"],
        pages=pages,
        plant=plants[0],
        decoys=_decoys(pages),
    )


def load_pack(path: Path = CONTENT_PATH) -> tuple[Document, ...]:
    """`documents.yaml` as documents. An invalid one fails before anything is rendered."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise BuildError(f"{path}: expected a non-empty list of documents")
    documents = tuple(_document(entry, str(path)) for entry in raw)
    names = [document.file for document in documents]
    duplicate = next((name for name in names if names.count(name) > 1), None)
    if duplicate is not None:
        raise BuildError(f"{path}: {duplicate} is listed twice")
    return documents


# ---------------------------------------------------------------------- build and verify


def _raw_text(body: bytes, number: int) -> str:
    """One page as the text layer holds it, before pymupdf4llm filters anything out."""
    with pymupdf.open(stream=body, filetype="pdf") as document:
        return str(document[number - 1].get_text())


def _verify(document: Document, body: bytes) -> None:
    """Refuse bytes whose manifest would be a lie about what the parser reads."""
    parsed = PyMuPDFParser().parse(body, document_id=document.file)
    if len(parsed.pages) != len(document.pages):
        raise BuildError(
            f"{document.file}: rendered {len(parsed.pages)} pages, "
            f"expected {len(document.pages)}"
        )
    for page in parsed.pages:
        if not has_extractable_text(page.text):
            raise BuildError(f"{document.file} page {page.page_number}: no text layer to read")

    plant, where = document.plant, f"{document.file} page {document.plant.page}"
    read_back = _comparable(plant.text) in _comparable(parsed.pages[plant.page - 1].text)
    if plant.form.reaches_the_parser and not read_back:
        raise BuildError(
            f"{where}: the planted instruction is not read back verbatim - the fixture "
            f"would promise text the guard can never see: {plant.text[:60]!r}"
        )
    if not plant.form.reaches_the_parser:
        if read_back:
            raise BuildError(
                f"{where}: the parser now reads the {plant.form.name} plant that this "
                "negative control exists to prove it drops. The guard has to handle it: "
                "see ADR-0032 before changing this fixture."
            )
        if _comparable(plant.text) not in _comparable(_raw_text(body, plant.page)):
            raise BuildError(
                f"{where}: the {plant.form.name} plant is missing from the text layer "
                "itself, so the control proves nothing about the parser"
            )

    for decoy in document.decoys:
        if _comparable(decoy.text) not in _comparable(parsed.pages[decoy.page - 1].text):
            raise BuildError(
                f"{document.file} page {decoy.page}: the decoy is not read back verbatim, "
                f"so no guard could be held to leaving it alone: {decoy.text[:60]!r}"
            )


def build_documents(pack: Sequence[Document]) -> Mapping[str, bytes]:
    """Filename to PDF bytes, in filename order, each proved readable by the real parser."""
    built = {}
    for document in sorted(pack, key=lambda entry: entry.file):
        body = build_pdf(document.pages)
        _verify(document, body)
        built[document.file] = body
    return built


def manifest_text(pack: Sequence[Document], documents: Mapping[str, bytes]) -> str:
    """`manifest.yaml`: what is planted, where, and what must never be flagged."""
    by_name = {document.file: document for document in pack}
    entries = [
        {
            "file": name,
            "language": by_name[name].language,
            "pages": len(by_name[name].pages),
            "sha256": hashlib.sha256(body).hexdigest(),
            "planted": {
                "page": by_name[name].plant.page,
                "form": by_name[name].plant.form.name,
                "technique": by_name[name].plant.form.technique,
                "visible_to_a_reader": by_name[name].plant.form.visible_to_a_reader,
                "reaches_the_parser": by_name[name].plant.form.reaches_the_parser,
                "text": by_name[name].plant.text,
            },
            "decoys": [
                {"page": decoy.page, "text": decoy.text} for decoy in by_name[name].decoys
            ],
        }
        for name, body in sorted(documents.items())
    ]
    header = (
        f"# Generated by scripts/build_adversarial_pack.py ({STORY}). Do not edit by hand.\n"
        "#\n"
        "# `planted` is the one instruction each document carries, on the page it sits on.\n"
        "# `decoys` are legitimate procurement imperatives on the same pages: S2.3.1 must\n"
        "# flag every plant it can see and leave every decoy alone. The one plant with\n"
        "# `reaches_the_parser: false` is a negative control - pymupdf4llm drops white ink,\n"
        "# so no guard can be held to catching it (ADR-0032).\n"
    )
    body = yaml.safe_dump(
        {"story": STORY, "documents": entries},
        sort_keys=False,
        allow_unicode=True,
        width=96,
    )
    return header + body


# --------------------------------------------------------------------------------- I/O


def stale_files(
    directory: Path, documents: Mapping[str, bytes], manifest: str
) -> tuple[str, ...]:
    """Names whose committed file is missing or differs. Empty means the pack is current."""
    on_disk = [(name, body) for name, body in sorted(documents.items())] + [
        (MANIFEST_NAME, manifest.encode("utf-8"))
    ]
    return tuple(
        name
        for name, body in on_disk
        if not (directory / name).is_file() or (directory / name).read_bytes() != body
    )


def write_pack(directory: Path, documents: Mapping[str, bytes], manifest: str) -> list[Path]:
    """Write every document and the manifest. Returns the paths, in filename order."""
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, body in sorted(documents.items()):
        path = directory / name
        path.write_bytes(body)
        written.append(path)
    manifest_path = directory / MANIFEST_NAME
    manifest_path.write_text(manifest, encoding="utf-8")
    written.append(manifest_path)
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the S6.5 adversarial fixture pack.")
    parser.add_argument(
        "--check", action="store_true", help="verify the committed pack, write nothing"
    )
    args = parser.parse_args(argv)

    try:
        pack = load_pack()
        documents = build_documents(pack)
        manifest = manifest_text(pack, documents)
    except (BuildError, OSError, ValueError) as error:
        print(f"build error: {error}", file=sys.stderr)
        return 1

    if args.check:
        stale = stale_files(PACK_DIR, documents, manifest)
        if stale:
            print(
                f"pack is stale, rebuild with `make adversarial-pack`: {', '.join(stale)}",
                file=sys.stderr,
            )
            return 1
        print(f"pack is current: {len(documents)} documents in {PACK_DIR}")
        return 0

    written = write_pack(PACK_DIR, documents, manifest)
    total = sum(path.stat().st_size for path in written)
    print(f"wrote {len(written)} files ({total / 1024:.0f} KB) to {PACK_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
