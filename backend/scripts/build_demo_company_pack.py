"""S6.3 — build the demo GmbH's document pack from `profile.yaml` and `documents.yaml`.

    uv run python scripts/build_demo_company_pack.py           # render and write
    uv run python scripts/build_demo_company_pack.py --check   # verify only, write nothing

The walkthrough needs a bidder with evidence: a register extract to prove the company
exists, tax and insurance papers, an ISO 27001 certificate a French tender's
information-security question can retrieve, and references carrying real Personentage. None
of that can be downloaded — the demo GmbH is invented — so it is generated here rather than
hand-placed as opaque binaries, which makes every word of it reviewable in a diff.

**Everything in the pack is fabricated, and says so on every page.** A banner reads
"MUSTERDOKUMENT - Demodaten, kein amtliches Dokument" at the top of every page and a footer
names this repository and the story at the bottom. The registrar, the tax office, the
certification body and the insurer are invented names carrying "(fiktiv...)", and every
number — register sheet, tax number, certificate number, policy number — is invented. No
real seal, logo, layout or accreditation mark is reproduced.

Both YAML files are *inputs*, not outputs. `documents.yaml` holds the page content, so that
a reviewer reads German prose as prose and this file stays an engine; `profile.yaml` holds
the structured facts, and every number on a page reaches it through a `{placeholder}` filled
by `fields()`. That is the anti-drift mechanism: the profile S2.4.1 renders and the evidence
`company_rag_search` retrieves are the same numbers by construction. `profile.yaml` stays
hand-edited because its comments explain which certificate is deliberately expired.

**A second run must change nothing.** PyMuPDF stamps a fresh trailer `/ID` on every save,
which is the only source of nondeterminism in a text-only PDF; `no_new_id=True` suppresses
it and `set_metadata({})` drops the creation timestamp. Prove it with

    uv run python scripts/build_demo_company_pack.py && shasum …/documents/*

twice, or with `--check`, which is what `tests/unit/test_demo_company_pack.py` asserts.

Only the base-14 fonts are used, so no font file is embedded and the bytes stay tiny — but
those fonts stop at Latin-1, and PyMuPDF silently renders anything beyond it as `?`. An em
dash would therefore eat the demo marker without failing anything, so `require_latin_1`
refuses the text instead.
"""

from __future__ import annotations

import argparse
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

from crossbid.models.company import (  # noqa: E402  (after the sys.path fix)
    CertificateHeld,
    CompanyProfile,
)

PACK_DIR: Final = BACKEND_DIR / "tests" / "fixtures" / "company"
DOCUMENTS_DIR: Final = PACK_DIR / "documents"
PROFILE_PATH: Final = PACK_DIR / "profile.yaml"
CONTENT_PATH: Final = PACK_DIR / "documents.yaml"

COMPANY_ADDRESS: Final = "Beispielallee 14, 12345 Musterstadt"  # invented, like every fact here
FICTION_NOTE: Final = (
    "Musterdokument mit fiktiven Angaben. Die Beispiel IT Services GmbH ist ein erfundenes "
    "Unternehmen, die ausstellende Stelle existiert nicht, und sämtliche Nummern sind frei "
    "erfunden. Erzeugt von scripts/build_demo_company_pack.py für Story S6.3."
)

MARKER: Final = "MUSTERDOKUMENT - Demodaten, kein amtliches Dokument"
FOOTER: Final = "Synthetisches Demodokument - crossbid, tests/fixtures/company, Story S6.3"

PAGE_WIDTH: Final = 595.0  # A4 portrait, in points
PAGE_HEIGHT: Final = 842.0
MARGIN: Final = 56.0
BANNER_HEIGHT: Final = 34.0
FOOTER_TOP: Final = PAGE_HEIGHT - 52.0
LABEL_WIDTH: Final = 170.0

BODY_SIZE: Final = 10.0
HEADING_SIZE: Final = 15.0
SUBHEADING_SIZE: Final = 11.5
SMALL_SIZE: Final = 7.5
LINE_HEIGHT: Final = 1.35
BLOCK_GAP: Final = 9.0

REGULAR: Final = "helv"
BOLD: Final = "hebo"

BANNER_FILL: Final = (0.94, 0.91, 0.80)
BANNER_STROKE: Final = (0.62, 0.52, 0.18)
BANNER_TEXT: Final = (0.30, 0.24, 0.02)
MUTED: Final = (0.35, 0.35, 0.38)


class BuildError(RuntimeError):
    """The pack cannot be rendered as written — a page overflows, or a glyph is unusable."""


Block = tuple[str, str]
"""`(style, text)`. `documents.yaml` writes one of these as a single-key mapping per block."""

BLOCK_STYLES: Final = ("h", "p", "li", "kv")
"""`h` subheading, `p` paragraph, `li` bullet, `kv` label and value separated by a tab."""


@dataclass(frozen=True)
class Page:
    """One rendered page: a heading and the blocks under it, in order."""

    heading: str
    blocks: tuple[Block, ...]


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


def euro(amount: float) -> str:
    """German thousands and decimal separators, the way a German document writes money."""
    return f"{amount:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".") + " EUR"


def fte(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def german_date(iso: str) -> str:
    year, month, day = iso.split("-")
    return f"{day}.{month}.{year}"


# ------------------------------------------------------------------------------ rendering


def _draw(
    page: pymupdf.Page, rect: pymupdf.Rect, text: str, *, font: str, size: float
) -> float:
    """Write wrapped text into `rect` and return the y the next block starts at."""
    unused = page.insert_textbox(
        rect, require_latin_1(text), fontname=font, fontsize=size, lineheight=LINE_HEIGHT
    )
    if unused < 0:
        raise BuildError(f"text does not fit the page: {text[:60]!r}")
    return rect.y1 - unused


def _body_rect(top: float, *, left: float = MARGIN, right: float = PAGE_WIDTH - MARGIN):
    return pymupdf.Rect(left, top, right, FOOTER_TOP - 6.0)


def _draw_banner(page: pymupdf.Page) -> None:
    """The one thing every page must carry: this is not a real document."""
    band = pymupdf.Rect(MARGIN, 24.0, PAGE_WIDTH - MARGIN, 24.0 + BANNER_HEIGHT)
    page.draw_rect(band, color=BANNER_STROKE, fill=BANNER_FILL, width=0.8)
    page.insert_textbox(
        pymupdf.Rect(band.x0, band.y0 + 10.0, band.x1, band.y1),  # vertical centring
        require_latin_1(MARKER),
        fontname=BOLD,
        fontsize=9.5,
        color=BANNER_TEXT,
        align=pymupdf.TEXT_ALIGN_CENTER,
    )


def _draw_footer(page: pymupdf.Page, number: int, total: int) -> None:
    page.draw_line(
        pymupdf.Point(MARGIN, FOOTER_TOP),
        pymupdf.Point(PAGE_WIDTH - MARGIN, FOOTER_TOP),
        color=MUTED,
        width=0.5,
    )
    page.insert_textbox(
        pymupdf.Rect(MARGIN, FOOTER_TOP + 5.0, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 20.0),
        require_latin_1(f"{FOOTER} - Seite {number} von {total}"),
        fontname=REGULAR,
        fontsize=SMALL_SIZE,
        color=MUTED,
    )


def _draw_block(page: pymupdf.Page, top: float, style: str, text: str) -> float:
    """One block, returning the y after it. Unknown styles are a programming error."""
    if style == "h":
        return _draw(page, _body_rect(top), text, font=BOLD, size=SUBHEADING_SIZE)
    if style == "p":
        return _draw(page, _body_rect(top), text, font=REGULAR, size=BODY_SIZE)
    if style == "li":
        return _draw(
            page, _body_rect(top, left=MARGIN + 12.0), f"- {text}", font=REGULAR, size=BODY_SIZE
        )
    if style == "kv":
        label, _, value = text.partition("\t")
        split = MARGIN + LABEL_WIDTH
        bottom = _draw(
            page, _body_rect(top, right=split - 8.0), label, font=BOLD, size=BODY_SIZE
        )
        return max(
            bottom,
            _draw(page, _body_rect(top, left=split), value, font=REGULAR, size=BODY_SIZE),
        )
    raise BuildError(f"unknown block style {style!r}")


def _render_page(page: pymupdf.Page, content: Page, number: int, total: int) -> None:
    _draw_banner(page)
    cursor = (
        _draw(
            page,
            _body_rect(24.0 + BANNER_HEIGHT + 22.0),
            content.heading,
            font=BOLD,
            size=HEADING_SIZE,
        )
        + BLOCK_GAP
    )
    for style, text in content.blocks:
        cursor = _draw_block(page, cursor, style, text) + BLOCK_GAP
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
        # Cleared, not filled: a title or a creation date in the info dict would either
        # leak the build clock or invite a reader to take the document for genuine.
        document.set_metadata({})
        return document.tobytes(garbage=4, deflate=True, no_new_id=True)
    finally:
        document.close()


# ------------------------------------------------------------------- facts into the pages


def _held(profile: CompanyProfile, prefix: str) -> CertificateHeld:
    """The profile entry a document is the paper for. Missing is a build error, not a skip."""
    for certificate in profile.certificates:
        if certificate.name.startswith(prefix):
            return certificate
    raise BuildError(f"profile.yaml has no certificate starting with {prefix!r}")


def _paper(profile: CompanyProfile, prefix: str, key: str) -> dict[str, str]:
    """The four placeholders every certificate document prints: issuer, number, dates."""
    held = _held(profile, prefix)
    if held.issuer is None or held.number is None:
        raise BuildError(f"{held.name}: issuer and number are both required on paper")
    if held.issued_on is None or held.expires_on is None:
        raise BuildError(f"{held.name}: issue and expiry dates are both required on paper")
    return {
        f"{key}_issuer": held.issuer,
        f"{key}_number": held.number,
        f"{key}_issued": german_date(held.issued_on.isoformat()),
        f"{key}_expires": german_date(held.expires_on.isoformat()),
    }


def fields(profile: CompanyProfile) -> dict[str, str]:
    """Every `{placeholder}` `documents.yaml` may use, filled from `profile.yaml`.

    This mapping is the whole anti-drift mechanism: no number appears on a page unless it
    came through here, so the profile S2.4.1 renders and the evidence `company_rag_search`
    retrieves are the same numbers by construction.
    """
    if profile.staff_fte is None or profile.staff_fte_relevant is None:
        raise BuildError("profile.yaml must state staff_fte and staff_fte_relevant")
    values = {
        "fiction_note": FICTION_NOTE,
        "name": profile.name,
        "address": COMPANY_ADDRESS,
        "registration_court": str(profile.registration_court),
        "registration_number": str(profile.registration_number),
        "staff_total_line": (
            f"Gesamtbelegschaft\t{fte(profile.staff_fte)} VZÄ im Jahresdurchschnitt"
        ),
        "staff_relevant_line": (
            f"Davon im einschlägigen Geschäftsbereich\t{fte(profile.staff_fte_relevant)} VZÄ"
        ),
        **_paper(profile, "ISO/IEC 27001", "iso"),
        **_paper(profile, "Unbedenklichkeitsbescheinigung", "tax"),
        **_paper(profile, "Freistellungsbescheinigung", "exemption"),
        **_paper(profile, "Betriebs- und Berufshaftpflicht", "policy"),
    }
    # The insurer is the certificate's issuer; `documents.yaml` names it on the letterhead.
    values["insurer"] = values["policy_issuer"]
    for index, entry in enumerate(profile.turnover, start=1):
        values[f"turnover_{index}"] = (
            f"Geschäftsjahr {entry.year}\t{euro(entry.amount)} ({entry.field_of_activity})"
        )
    return values


# ------------------------------------------------------------------------ content loading


def _fill(text: str, values: Mapping[str, str], where: str) -> str:
    """Substitute the placeholders. An unknown one is a build error, never a blank."""
    try:
        return text.format_map(values)
    except (KeyError, IndexError, ValueError) as error:
        raise BuildError(f"{where}: unusable placeholder in {text[:60]!r} ({error})") from error


def _blocks(raw: object, where: str, values: Mapping[str, str]) -> tuple[Block, ...]:
    """One page's blocks. Each is a single-key mapping whose key names the style."""
    if not isinstance(raw, list) or not raw:
        raise BuildError(f"{where}: `blocks` must be a non-empty list")
    blocks: list[Block] = []
    for entry in raw:
        if not isinstance(entry, dict) or len(entry) != 1:
            raise BuildError(
                f"{where}: each block is one mapping of style to text, got {entry!r}"
            )
        [(style, text)] = entry.items()
        if style not in BLOCK_STYLES:
            raise BuildError(f"{where}: unknown block style {style!r}, expected {BLOCK_STYLES}")
        blocks.append((str(style), _fill(str(text), values, where)))
    return tuple(blocks)


def _pages(raw: object, where: str, values: Mapping[str, str]) -> tuple[Page, ...]:
    if not isinstance(raw, list) or not raw:
        raise BuildError(f"{where}: `pages` must be a non-empty list")
    pages: list[Page] = []
    for number, entry in enumerate(raw, start=1):
        if not isinstance(entry, dict) or "heading" not in entry:
            raise BuildError(f"{where} page {number}: a page needs a `heading`")
        pages.append(
            Page(
                heading=_fill(str(entry["heading"]), values, f"{where} page {number}"),
                blocks=_blocks(entry.get("blocks"), f"{where} page {number}", values),
            )
        )
    return tuple(pages)


def load_content(
    profile: CompanyProfile, path: Path = CONTENT_PATH
) -> dict[str, tuple[Page, ...]]:
    """`documents.yaml` with every placeholder filled, keyed by the filename to write."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise BuildError(f"{path}: expected a non-empty list of documents")
    values = fields(profile)
    content: dict[str, tuple[Page, ...]] = {}
    for entry in raw:
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str):
            raise BuildError(f"{path}: every document needs a `file` name, got {entry!r}")
        name = entry["file"]
        if name in content:
            raise BuildError(f"{path}: {name} is listed twice")
        content[name] = _pages(entry.get("pages"), name, values)
    return content


# -------------------------------------------------------------------------- build and I/O


def load_profile(path: Path = PROFILE_PATH) -> CompanyProfile:
    """`profile.yaml` is an input; an invalid one must fail before anything is written."""
    return CompanyProfile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def build_documents(profile: CompanyProfile) -> Mapping[str, bytes]:
    """Filename to PDF bytes, in filename order. Two calls return the same bytes."""
    return {name: build_pdf(pages) for name, pages in sorted(load_content(profile).items())}


def stale_documents(directory: Path, documents: Mapping[str, bytes]) -> tuple[str, ...]:
    """Names whose committed file is missing or differs. Empty means the pack is current."""
    return tuple(
        name
        for name, body in sorted(documents.items())
        if not (directory / name).is_file() or (directory / name).read_bytes() != body
    )


def write_pack(directory: Path, documents: Mapping[str, bytes]) -> list[Path]:
    """Write every document, creating the directory. Returns the paths, in filename order."""
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, body in sorted(documents.items()):
        path = directory / name
        path.write_bytes(body)
        written.append(path)
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the S6.3 demo company document pack.")
    parser.add_argument(
        "--check", action="store_true", help="verify the committed pack, write nothing"
    )
    args = parser.parse_args(argv)

    try:
        documents = build_documents(load_profile())
    except (BuildError, OSError, ValueError) as error:
        print(f"build error: {error}", file=sys.stderr)
        return 1

    if args.check:
        stale = stale_documents(DOCUMENTS_DIR, documents)
        if stale:
            print(
                f"pack is stale, rebuild with `make demo-pack`: {', '.join(stale)}",
                file=sys.stderr,
            )
            return 1
        print(f"pack is current: {len(documents)} documents in {DOCUMENTS_DIR}")
        return 0

    written = write_pack(DOCUMENTS_DIR, documents)
    total = sum(path.stat().st_size for path in written)
    print(f"wrote {len(written)} documents ({total / 1024:.0f} KB) to {DOCUMENTS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
