# Ingestion fixtures — provenance

Both PDFs here were **built by hand with pymupdf**, not downloaded. They exist because the
real tender fixtures cannot exercise S2.1.1's second acceptance criterion: ADR-0001,
ADR-0003 and ADR-0006 all record **zero text-free pages** across the DE (191 pages), EN
(138) and FR (25) packs, which is exactly why the "no extractable text" path needs a
constructed case (the lesson of ADR-0007: real data is accidentally well-behaved).

Neither file contains a single glyph of text on its image-only pages. Each such page carries
a stroked-and-filled rectangle plus an inserted RGB pixmap, so the page has real drawing and
raster content and is not merely blank — `pymupdf4llm` returns `"\n\n\n\n"` for it and
`page.get_text()` returns `""`.

| File | Pages | Shape | Used by |
|---|---|---|---|
| `image_only_page.pdf` | 1 | image only | every page unread, no chunks produced |
| `text_image_text.pdf` | 3 | text · image only · text | `unread_pages == (2,)`, parsing continues |

Page size is A4; text is set in Helvetica at 11pt and is deliberately German
("Der Umsatz muss mindestens 3.000.000,00 EUR pro Jahr betragen", "Mindestens 29 VZAE"), so
the fixtures echo the real thresholds of ADR-0002 rather than lorem ipsum.

To rebuild: create a document with `pymupdf.open()`, add A4 pages, call
`page.draw_rect(...)` and `page.insert_image(..., pixmap=pymupdf.Pixmap(...))` for an
image-only page and `page.insert_textbox(...)` for a text page, then
`doc.set_metadata({})` and `doc.save(path, garbage=4, deflate=True)`. Metadata is cleared so
the committed bytes carry no build timestamp. Note that pymupdf refuses to *save* a
zero-page document, so the zero-page case is assembled as a literal PDF byte string inside
`tests/unit/test_pymupdf_parser.py` instead of being committed here.
