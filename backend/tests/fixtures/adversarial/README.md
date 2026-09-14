# Adversarial fixtures (S6.5)

**These four PDFs contain working prompt-injection payloads.** They exist to be caught. Do
not upload one to a real assistant, do not paste their text into a prompt outside the
guard's tests, and do not copy one into another fixture directory where it would be read
as an ordinary tender. Every page carries a footer saying what it is.

Everything in them is invented: the authorities, the reference numbers, the deadlines and
the criteria. Nothing was copied from a real notice.

## What is here

| File | Language | Form of the attack | Reaches the parser |
|---|---|---|---|
| `DE_Bewerbungsbedingungen_Auszug.pdf` | de | plain paragraph | yes |
| `FR_Reglement_de_la_Consultation_Extrait.pdf` | fr | table cell | yes |
| `EN_Tender_Specifications_Extract.pdf` | en | text buried under an opaque white rectangle | yes |
| `DE_Leistungsbeschreibung_Auszug.pdf` | de | white ink on white paper | **no** |

`manifest.yaml` records, per document, the planted instruction and the page it sits on,
plus the **decoys**: legitimate procurement imperatives ("Der Bieter hat ... einzureichen")
on the same pages, which S2.3.1 must leave alone. A guard measured only against payloads
has no precision.

## The last row is a negative control

`pymupdf4llm` drops white glyphs, so that payload never reaches the markdown the chunker
and every prompt are built from — measured, not assumed. The textbook white-on-white attack
is therefore already dead in this pipeline, by accident rather than by design. It is
committed so that swapping the parser (for Docling, say) fails a test instead of quietly
re-opening the door. See ADR-0032.

## Rebuilding

`documents.yaml` is the input; the PDFs and `manifest.yaml` are generated.

```bash
make adversarial-pack                                          # rebuild
uv run python scripts/build_adversarial_pack.py --check        # verify, write nothing
```

The builder re-parses its own bytes with the repo's own parser and refuses to write a
manifest that names a page whose text does not carry the instruction.
