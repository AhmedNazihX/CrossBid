# DE tender fixture — sources

Story: **S6.1**. Retrieved **2026-09-10**. Real documents, unmodified.

## The tender

| Field | Value |
|---|---|
| TED publication number | `614251-2026` |
| Az. (buyer's file reference) | ZIB 14.16 - 99152/25/VV : 2 |
| Title | Beratungs- und Unterstützungsleistungen für IPv6-Migrationen in den Behörden und Organisationen des Bundes (IPv6-Experten) — **Los 2**: Netzwerk- und Informationstechnik, Externe Hardware, IT-Security |
| Buyer | Bundesrepublik Deutschland, Bundesministerium des Innern — Beschaffungsamt des BMI |
| Procedure | Offenes Verfahren nach VgV (Directive 2014/24/EU) |
| CPV | 72000000 — IT services: consulting, software development, internet and support |
| Official language | DEU |
| Tender deadline | 2026-10-06 |
| Notice type | `cn-standard` |

## Provenance

| Artefact | Source |
|---|---|
| Notice discovery | `POST https://api.ted.europa.eu/v3/notices/search` (documented API, no key) |
| `614251-2026.notice.de.pdf` | `https://ted.europa.eu/de/notice/614251-2026/pdf` (from the notice's `links.pdf.DEU`) |
| `documents/*` | `https://www.evergabe-online.de/tenderdocuments.html?id=888336` (the notice's `document-url-lot`) — e-Vergabe, the German federal procurement platform |

The procurement documents were fetched **once, by hand, to create this fixture**, with the
user's explicit authorisation on 2026-09-10. Access is anonymous: §41 Abs. 1 VgV obliges
German buyers to offer the Vergabeunterlagen over an unrestricted, direct, free-of-charge
internet address. The platform requires only a cookie round-trip — no account, no login.

**The application never does this.** The "no scraping anywhere" rule in `CLAUDE.md` stands:
at run time Crossbid reads TED, eCertis and Frankfurter through their documented APIs, and the
bidder uploads procurement documents by hand. This directory is build-time content, not a
run-time code path.

## Why the whole pack is not here

e-Vergabe offers **48 files, ~42 MB**, over S6.1's 15 MB ceiling. The 28 committed below are
every document that carries a requirement, a contract term, or a declaration a bidder must
sign. Excluded: the 3.7 MB locked `Angebotsformular`, five `.xlsx` planning templates (one is
12 MB), the 4.1 MB `Migrationsleitfaden`, the 4.5 MB `Verpflichtungsgesetz mit Anlagen`
(the 2-page `Eigenerklärung` version **is** committed), `.docx`/`.odt` CV and Q&A templates,
the supplier handbook, and the platform's own `_Hinweise` note. All are re-downloadable from
the URL above.

## Why this fixture is a fair test of the core bet

191 pages, 451 088 characters of German legal prose, **zero text-free pages** — so
`pymupdf4llm` reads all of it and the OCR that the plan cut is not needed. The pack carries
hard, checkable thresholds (turnover ≥ €3 000 000 per year, ≥ 29 VZÄ average staff,
≥ 3 references of ≥ 25 Personentage each) and the §123 / §124 GWB exclusion grounds, which are
Germany's transposition of Directive 2014/24/EU Art. 57 — the same criteria eCertis is built
on, with `amtliches-verzeichnis.ihk.de` (IHK Präqualifizierung) named as the national evidence.

Note for the demo: the fictional demo GmbH has 25 staff against a **29 VZÄ minimum**, so this
tender yields a genuine `no_go` with a concrete gap — the no-go walkthrough S7.4 needs.

## Filenames

Nine names were transliterated (ä→ae, ö→oe, ü→ue, ß→ss) because macOS stores umlauts as NFD
while CI runs on Linux, where the NFD/NFC mismatch breaks path lookups. Contents are untouched.

| File (committed) | Original name on e-Vergabe | Pages | Size |
|---|---|---|---|
| `AGB.pdf` | — same — | 10 | 211 KB |
| `Allgemeine_Bewerbungsbedingungen_elektronisch.pdf` | — same — | 9 | 186 KB |
| `Anlage_Unternehmensdaten_VV2.pdf` | — same — | 3 | 309 KB |
| `Aufforderungsschreiben_VV2_V1.pdf` | — same — | 1 | 109 KB |
| `Besondere_Bewerbungsbedingungen_VV2_V1.pdf` | — same — | 10 | 242 KB |
| `EVB_IT_Dienstleistung_AGB.pdf` | — same — | 15 | 245 KB |
| `EVB_IT_Dienstleistung_Kurzfassung_VV2_V1.pdf` | — same — | 3 | 70 KB |
| `EVB_IT_Dienstleistung_Langfassung_VV2_V1.pdf` | — same — | 12 | 143 KB |
| `EVB_IT_Dienstleistung_Muster1_Leistungsnachweis_VV2_V1.pdf` | — same — | 1 | 17 KB |
| `Eigenerklaerung_Ausschlussgruende_VV2.pdf` | `Eigenerklärung_Ausschlussgründe_VV2.pdf` | 6 | 244 KB |
| `Eigenerklaerung_Sanktionen_Russland_VV2.pdf` | `Eigenerklärung_Sanktionen_Russland_VV2.pdf` | 3 | 197 KB |
| `Eigenerklaerung_Verpflichtungsgesetz_VV2.pdf` | `Eigenerklärung_Verpflichtungsgesetz_VV2.pdf` | 2 | 1679 KB |
| `Erklaerung_zur_sozialen_Nachhaltigkeit_von_IT_VV2.pdf` | `Erklärung_zur_sozialen_Nachhaltigkeit_von_IT_VV2.pdf` | 16 | 484 KB |
| `Information_in_English.pdf` | — same — | 1 | 92 KB |
| `Kriterienkatalog_Eignung_VV2_V1.pdf` | — same — | 3 | 151 KB |
| `Kriterienkatalog_Leistung_VV2_V1_VEROeFFENTLICHT.pdf` | `Kriterienkatalog_Leistung_VV2_V1_VERÖFFENTLICHT.pdf` | 15 | 378 KB |
| `Leistungsbeschreibung_VV2_V1.pdf` | — same — | 21 | 540 KB |
| `Liste_Bedarfstraeger_VV2_V1.pdf` | `Liste_Bedarfsträger_VV2_V1.pdf` | 5 | 40 KB |
| `Mustervereinbarung_Auftragsverarbeitung_VV2.pdf` | — same — | 14 | 262 KB |
| `Rahmenvereinbarung_VV2_V1.pdf` | — same — | 14 | 324 KB |
| `Rechtsbehelfsbelehrung.pdf` | — same — | 1 | 91 KB |
| `Unterauftraege_VV2.pdf` | `Unteraufträge_VV2.pdf` | 1 | 929 KB |
| `VOL_B_2003.pdf` | — same — | 15 | 220 KB |
| `Verpflichtung_VS-NfD_und_VS-NfD-Merkblatt_im_Anhang_VV2.pdf` | — same — | 2 | 425 KB |
| `Verpflichtungserklaerung_Eignungsleihe_Unterauftraege_VV2.pdf` | `Verpflichtungserklärung_Eignungsleihe_Unteraufträge_VV2.pdf` | 2 | 910 KB |
| `Verpflichtungserklaerung_Scientology_VV2.pdf` | `Verpflichtungserklärung_Scientology_VV2.pdf` | 1 | 858 KB |
| `Vordruck_Information_Arbeitsbedingungen_BTTG_VV2.pdf` | — same — | 1 | 123 KB |
| `Vordruck_Referenzen_VV2.pdf` | — same — | 4 | 1561 KB |

## Reserve candidate

`621327-2026` (Deutsche Welle, HPE hardware supply and maintenance, 24-page notice) repeats its
8 selection criteria verbatim across 4 lots — **32 entries for 8 distinct criteria**. It is the
natural stress test for the extractor's dedupe pass. Not committed; re-downloadable from
`https://ted.europa.eu/de/notice/621327-2026/pdf`.
