# Demo company pack — sources

Story: **S6.3**. **The entire pack is synthetic.** Nothing here was downloaded, scanned or
adapted from a real document: every page is rendered by
`backend/scripts/build_demo_company_pack.py` from the facts in `profile.yaml`, on 2026-09-11.

## The company

| Field | Value |
|---|---|
| Name | Beispiel IT Services GmbH — **a fictional company; it does not exist** |
| Country / legal form | `de` / `gmbh` |
| Registration | HRB 214877, Amtsgericht Musterstadt (**invented registry court and number**) |
| Address | Beispielallee 14, 12345 Musterstadt (**invented**) |
| Turnover (IT-Beratungsleistungen) | 3 420 000 / 3 985 000 / 4 310 000 EUR for 2023–2025 |
| Staff | 25,0 VZÄ, of which 21,5 VZÄ in the field of the contract |

The name is the one `scripts/seed_dev_company.py` already writes into the `companies` row, so
the seed (S2.4.3) and this pack describe the same tenant.

## Why it is generated, not hand-placed

The demo GmbH is invented, so its papers cannot be downloaded the way the tender fixtures in
`tests/fixtures/tenders/` were. Generating them from a committed script keeps every word of
them reviewable in a diff and regenerable; committing ten opaque PDFs would not.

The generator has two **inputs**, both committed beside the PDFs. `documents.yaml` holds the
page content, so the German prose is reviewed as prose rather than as string literals inside a
script. `profile.yaml` holds the structured facts, and every number on a page reaches it through
a `{placeholder}` — so the profile S2.4.1 renders and the evidence `company_rag_search` retrieves
are the same numbers by construction, and an unknown placeholder is a build error, never a blank.
`tests/unit/test_demo_company_pack.py` fails when the committed bytes differ from a fresh
build, so a stale fixture is caught in CI rather than in a demo.

Rebuild with `make demo-pack`; verify without writing with
`uv run python scripts/build_demo_company_pack.py --check`. **A second run changes no file**:
`Document.set_metadata({})` drops the creation timestamp and `save(..., no_new_id=True)`
suppresses the fresh trailer `/ID` MuPDF would otherwise stamp on every save, which is the
only source of nondeterminism in a text-only PDF.

## How it is marked as fabricated

Every page of every document carries, in this order:

1. a banner across the top reading **"MUSTERDOKUMENT - Demodaten, kein amtliches Dokument"**;
2. a footer reading "Synthetisches Demodokument - crossbid, tests/fixtures/company, Story S6.3
   - Seite *n* von *m*".

Every issuing body is invented and named as such on the page — "Amtsgericht Musterstadt
(fiktives Registergericht)", "Finanzamt Musterstadt-Mitte (fiktive Finanzbehörde)", "Musterzert
Zertifizierungsgesellschaft mbH (fiktive Zertifizierungsstelle)", "Musterland Versicherung AG
(fiktives Versicherungsunternehmen)", and four fictional public clients. Every register sheet,
tax number, certificate number and policy number is invented, e-mail addresses use the reserved
`.example` TLD, and telephone numbers are `+49 000 000000-nn`. **No real certificate's layout,
seal, logo or accreditation mark is reproduced** — the pages are plain typeset text.

## The documents

| File | Pages | Size | What it evidences |
|---|---|---|---|
| `Handelsregisterauszug.pdf` | 3 | 10 KB | Existence, legal form, capital, representation, entry history |
| `Unbedenklichkeitsbescheinigung_Finanzamt.pdf` | 2 | 7 KB | No tax arrears (§ 123 Abs. 4 GWB); p. 2 is the **expired** Freistellungsbescheinigung nach § 48b EStG |
| `Zertifikat_ISO_IEC_27001_2022.pdf` | 2 | 8 KB | ISO/IEC 27001:2022 ISMS certificate; p. 2 is the Geltungsbereich |
| `Betriebshaftpflichtversicherung_Bestaetigung.pdf` | 2 | 7 KB | Betriebs-, Berufs- and Vermögensschadenhaftpflicht cover |
| `Angebotszusammenfassung_2023_ISMS_Beratung.pdf` | 2 | 8 KB | Past bid: ISMS build-out, 142 Personentage |
| `Angebotszusammenfassung_2024_IPv6_Migration.pdf` | 2 | 8 KB | Past bid: IPv6 migration, 310 Personentage |
| `Angebotszusammenfassung_2025_Netzwerkbetrieb.pdf` | 2 | 8 KB | Past bid: network operations, 96 Personentage |
| `Referenzschreiben_Landesamt_Musterland.pdf` | 2 | 8 KB | Reference letter for the 2024 IPv6 contract |
| `Referenzschreiben_Stadtwerke_Musterstadt.pdf` | 2 | 8 KB | Reference letter for the 2025 network contract |
| `Eigenerklaerung_Umsatz_und_Beschaeftigte.pdf` | 2 | 7 KB | § 45 VgV turnover, § 46 VgV headcount, §§ 123/124 GWB declaration |
| `profile.yaml` | — | 4 KB | The structured facts; the generator's input |
| `documents.yaml` | — | 17 KB | The page content; the generator's other input |

21 pages, 85 KB of PDF (140 KB with both YAML inputs and this file) — far under S6.1's 15 MB
fixture ceiling. Filenames are ASCII
(ä→ae, ö→oe, ü→ue), for the NFD/NFC reason `tests/fixtures/tenders/de/SOURCES.md` records.

The `Eigenerklärung` is one document beyond the story's list. It is here because the DE tender
fixture asks for exactly it, by name, for both the turnover and the headcount criterion — the
structured profile would otherwise have no retrievable evidence behind it.

## What the pack is tuned against

The DE fixture (`tests/fixtures/tenders/de/`, `Kriterienkatalog_Eignung`) demands at least
3 000 000 EUR turnover per year in the field of the contract, at least 29 VZÄ of average staff,
and at least three references of at least 25 abgerechnete Personentage each.

| Criterion | Demo company | Outcome |
|---|---|---|
| Turnover ≥ 3 000 000 EUR/year | 3,42 / 3,99 / 4,31 M EUR | supported |
| Staff ≥ 29 VZÄ | 25,0 VZÄ | **unsupported — the one real gap** |
| ≥ 3 references ≥ 25 PT | 142 / 310 / 96 PT | supported |

One supported and one unsupported criterion is what makes the S7.4 no-go walkthrough a genuine
no-go with a concrete, checkable gap rather than a vague one.

The **Freistellungsbescheinigung nach § 48b EStG expired on 2026-08-31** and is the only expired
entry in `profile.yaml`. S2.4.1's second acceptance criterion is that a certificate whose expiry
has passed is flagged on the profile, and no real fixture exercises it; page 2 of the tax
document prints the same expiry, so a reviewer can open the page the flag points at. The ISO
27001 entry is deliberately kept valid — it is the evidence a French tender's
information-security question has to retrieve, which is the pack's cross-border job.
