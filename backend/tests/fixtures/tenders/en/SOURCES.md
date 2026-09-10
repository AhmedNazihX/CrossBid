# EN tender fixture — sources

Story: **S6.2**. Retrieved **2026-09-10**. Real documents, unmodified.

## The tender

| Field | Value |
|---|---|
| TED publication number | `606362-2026` |
| OJ S issue | 170/2026, published 2026-09-03 |
| Buyer's internal reference | EASA/2026/OP/0006 |
| Procedure identifier | `0b2464f8-2d96-4e26-b1f4-5001cf101d3b` |
| Title | Digital Communications Services |
| Buyer | European Union Aviation Safety Agency (EASA), Cologne — legal type: EU institution, body or agency |
| Buyer country on TED | DEU (EASA's seat is Cologne; the procedure is an EU-institution procurement, not a German one) |
| Procedure | Open, framework contract without reopening of competition, max 2 participants |
| Legal basis | Regulation (EU, Euratom) 2024/2509 (the EU Financial Regulation), **not** Directive 2014/24/EU |
| CPV | 72400000 — Internet services |
| Lots | 1 (`LOT-0001`) |
| Official language | ENG |
| Submission languages | all 24 official EU languages |
| Value | €8 000 000 excluding VAT, 12 months renewable 3× (48 months max) |
| Tender deadline | 2026-10-12 10:00 (UTC+02:00) |
| Notice type | `cn-standard` |
| Award criteria | Quality 60 % / Price 40 %, technical threshold 70/100 with a 30/38 sub-threshold on the simulation exercise |

## Provenance

| Artefact | Source |
|---|---|
| Notice discovery | `POST https://api.ted.europa.eu/v3/notices/search` (documented API, no key) |
| `606362-2026.notice.en.pdf` | `https://ted.europa.eu/en/notice/606362-2026/pdf` (from the notice's `links.pdf.ENG`) |
| `documents/*` (all nine) | `https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/tender-details/docs/0b2464f8-2d96-4e26-b1f4-5001cf101d3b-CN/download-0b2464f8-2d96-4e26-b1f4-5001cf101d3b-CN.zip` — the "Download" link on the EU Funding & Tenders Portal tender page |
| Platform page (the notice's `document-url-lot`) | `https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/tender-details/0b2464f8-2d96-4e26-b1f4-5001cf101d3b-CN?#anchorDocuments` |

Fetched **once, by hand, to create this fixture**, with the user's explicit authorisation on
2026-09-10. This one is the cleanest provenance of the three fixtures: the EU Funding & Tenders
Portal publishes every procurement document as a **plain, unauthenticated `GET` URL**, plus a
single "Download" zip of the whole pack, and served all 4.6 MB to a bare `curl` with no cookie, no
account, no form and no user-agent games. Open publication of the procurement documents is an
obligation of the Financial Regulation's procurement annex, and the portal simply does it — but the
exact article was not verified, so treat the legal basis here as "the portal publishes them openly"
rather than as a citation.

The links were located by opening the tender page in a browser and reading the anchors — the page
is an SPA, so the URLs are not in the initial HTML. The portal's own JSON API
(`api.sedia-backoffice-production.eu/public/ehelp/versions/{uuid}-CN`) returns HTTP 403 to a plain
request, and `api.tech.ec.europa.eu/search-api` (apiKey `SEDIA`) indexes the FAQs for a procedure
but not the tender record itself, so neither is a usable route.

**The application never does this.** The "no scraping anywhere" rule in `CLAUDE.md` stands: at run
time Crossbid reads TED, eCertis and Frankfurter through their documented APIs, and the bidder
uploads procurement documents by hand. This directory is build-time content, not a run-time code
path.

## Nothing was excluded

The published pack is nine files, 4.8 MB uncompressed — under a third of the 15 MB ceiling — so all
nine are committed exactly as served, including the two `.docx` forms and the `.xlsx` price sheet.
No curation was needed and nothing was dropped. (The DE fixture had to be cut from 42 MB; this one
did not.)

## The criteria count — 20, and how it was reached

**The notice PDF on its own states zero criteria.** Both eForms fields delegate:

```
2.1.6. Grounds for exclusion → Sources of grounds for exclusion: Procurement Document
5.1.9. Selection criteria    → Sources of selection criteria:    Procurement Document
```

So the count below comes from **the documents**, specifically
`documents/Tender_Specifications_V1.pdf` §3.1–§3.2 (pages 17–24) and
`documents/Annex_2_Declaration_on_Honour_exclusion_and_selection_criteria_V1.docx`. Counting rule:
one entry per distinct obligation a tenderer must satisfy, at the level at which the document
itself numbers them; restatements of the same ground for a different legal person are listed but
excluded from the headline, following ADR-0002's `conditional_not_scored` convention.

### Exclusion criteria — 14

From Annex 2, Part A. Section I enumerates Article 138(1) of the Financial Regulation as nine
lettered situations:

| Item | Ground | Sub-limbs |
|---|---|---|
| (a) | bankruptcy, insolvency, winding-up, liquidator, arrangement with creditors, suspended business | — |
| (b) | breach of obligations relating to payment of taxes or social security contributions | — |
| (c) | grave professional misconduct | **6** — (i) misrepresenting information, (ii) agreements distorting competition, (iii) violating IP rights, (iv) unduly influencing decision-making, (v) attempting to obtain confidential information, (vi) incitement to discrimination, hatred or violence |
| (d) | criminal offences established by final judgment | **6** — (i) fraud, (ii) corruption, (iii) criminal organisation, (iv) money laundering or terrorist financing, (v) terrorist offences, (vi) child labour or trafficking in human beings |
| (e) | significant deficiencies in performing a legal commitment financed by the EU budget | — |
| (f) | irregularity within Reg. (EC, Euratom) 2988/95 Art. 1(2) | — |
| (g) | created an entity in another jurisdiction to circumvent fiscal, social or labour obligations | — |
| (h) | (legal persons) was itself created with the intent in (g) | — |
| (i) | intentionally resisted an investigation, check or audit | — |

Plus five further grounds for rejection, each a separate declaration in Annex 2:

| Source | Ground |
|---|---|
| Part A §IV (a) | previous involvement in preparing these procurement documents, where it breached equality of treatment |
| Part C (9)(a) | tenderer, group members, subcontractors and relied-upon entities not subject to EU restrictive measures (TEU Art. 29 / TFEU Art. 215) |
| Part C (10)(a) | the same, for directors, controlling persons and beneficial owners |
| Part D (11)(a) | no established debt to the Agency |
| Part E (12)(a) | the tender was prepared independently and autonomously from other tenders in this procedure |

**9 + 5 = 14.**

Not counted in the headline, because they are the same grounds restated for other legal persons or
routes to establishing them:

- Part A §II restates situations (1)(c)–(1)(i) for directors, controlling persons and beneficial
  owners — **7** restatements.
- Part A §III restates (a) and (b) for natural or legal persons assuming unlimited liability for
  the tenderer's debts — **2** restatements.
- Between §I and §II, the declaration lists **7** routes by which Art. 138(3) facts and findings
  can trigger (c)–(i) in the absence of a final judgment (EPPO / Court of Auditors / OLAF findings,
  non-final judgments, decisions of entrusted entities, information from Member States, competition
  decisions, being told of an OLAF investigation, "other similar situations") — evidence routes,
  not additional grounds.
- Part A §V (remedial measures) and §VI (evidence on exclusion criteria) are procedure, not
  criteria.

### Selection criteria — 6

From Tender Specifications §3.2, which states each with its minimum level of capacity, basis for
assessment and required evidence:

| Ref | Criterion | Minimum level |
|---|---|---|
| §3.2.1 | legal and regulatory capacity | Business Partners Form, official registration document, VAT registration document |
| **F1** | economic and financial capacity | **average yearly turnover of the last two financial years above EUR 1 500 000** |
| **T1** | experience with publicly accessible Drupal platforms | **≥ 2 projects** in the last 3 years, **each ≥ EUR 100 000**, each showing all three of: **≥ 2 500 pageviews/day**, **≥ 5 Drupal content types**, container/PaaS/SaaS-class infrastructure |
| **T2** | experience with restricted-access (login-required) Drupal platforms | **≥ 1 project** in the last 3 years showing all three of: role-based access control, multi-step approval workflows, modern cloud-native infrastructure |
| **T3** | information-security capacity | compliance with Appendix 2 and Appendix 3 of the draft contract, plus a named IT Security Manager with backup (Annex 7 confirmation statement) |
| §3.2.3 / Annex 2 Part B §II | absence of professional conflicting interests | applies to the tenderer, all involved entities and all subcontractors |

**Total: 14 + 6 = 20 distinct criteria, clearing the 15 bar.**

Two other honest readings of the same pack, for transparency:

- **Floor, 15.** If only Article 138(1)'s nine grounds count as "exclusion criteria" and the five
  further declarations are treated as something else, the total is 9 + 6 = 15 — still at the bar,
  not below it.
- **Leaf level, 41.** Counting every tick-box separately — §I's 9 grounds plus (c) and (d)'s twelve
  sub-limbs = 21, §II's 7 and §III's 2 restatements, §IV's 1, Part C's 2, Part D's 1, Part E's 1 —
  gives 35 exclusion leaves; with the 6 selection criteria that is 41, and T1 and T2 each carry
  three further sub-conditions on top.

## Why this fixture is a fair test of the core bet

Six PDFs, **138 pages, 338 434 characters, zero text-free pages** — `pymupdf4llm` reads all of it
and the OCR the plan cut is not needed. Three `.docx`/`.xlsx` files add 39 168 characters of form
text, all reachable by unzipping and reading `word/document.xml` / `xl/sharedStrings.xml`, so no
extra parser is required for this fixture either.

What it tests that the DE and FR fixtures do not:

1. **A different legal regime.** DE and FR are both Directive 2014/24/EU transpositions, so their
   exclusion grounds are Art. 57 and eCertis maps them directly. EASA runs under the **Financial
   Regulation Art. 138**, whose grounds overlap Art. 57 but are not identical — (e) deficiencies in
   an EU-financed commitment, (i) resisting an audit and the EDES database have no Art. 57
   equivalent. The Tender Specifications say so outright in footnote 12: "*The European Single
   Procurement Document (ESPD) may not be used yet in calls for tenders of the European Union
   Aviation Safety Agency (EASA)*". **eCertis cannot map this tender**, and the matrix must degrade
   to `unclear` with a citation instead of inventing an equivalence. That is exactly the failure
   mode the advisory-only design is supposed to survive, and it should be tested, not avoided.
2. **Hard, checkable numeric thresholds of a kind the other two lack.** €1 500 000 average
   turnover, ≥ 2 reference projects at ≥ €100 000 each, ≥ 2 500 pageviews/day, ≥ 5 Drupal content
   types. The pageview and content-type thresholds are *technical properties of a past project*,
   not company-level facts, so they exercise the `checkable` flag from ADR-0003 differently from a
   turnover figure: RAG over a company corpus can find a Drupal reference but is unlikely to find
   its daily pageviews.
3. **An English source with a German-speaking bidder.** The wedge is source-language extraction and
   bidder-language explanation. This fixture is the control case: source and UI language are both
   English, so any difference in extraction quality against the DE and FR fixtures is attributable
   to language rather than to the pack.

And it is a plausible bid: a website framework contract for a Drupal shop, €8m over four years,
with an SME-sized turnover floor of €1.5m. Note that the demo GmbH (about €2.8m turnover) clears
F1, so the verdict here will turn on T1 and T2 references rather than on finance — a third verdict
shape alongside the DE `no_go` (two quantified gaps) and the FR banded score.

## Filenames

Nine names were rewritten: spaces → underscores, and the buyer's long
`_Digital Communications Services_` infix dropped where it only repeated the tender title. Spaces
are legal on both macOS and Linux but make shell and pytest parametrisation fragile, and the
original names are pure ASCII, so no transliteration was needed. Contents are untouched.

| File (committed) | Original name on the portal | Pages | Size |
|---|---|---|---|
| `606362-2026.notice.en.pdf` | TED-generated, no filename | 5 | 135 KB |
| `documents/Invitation_to_tender_V1.pdf` | `Invitation to tender_Digital Communications Services_V1.pdf` | 5 | 623 KB |
| `documents/Tender_Specifications_V1.pdf` | `Tender Specifications_Digital Communications Services_V1.pdf` | 50 | 1 079 KB |
| `documents/Annex_2_Declaration_on_Honour_exclusion_and_selection_criteria_V1.docx` | `Annex 2 - Declaration on Honour on exclusion and selection criteria_Digital Communications Services_V1.docx` | — | 64 KB |
| `documents/Annexes_3-8_V1.docx` | `Annexes 3-8_V1.docx` | — | 36 KB |
| `documents/Annex_6_Model_Financial_Offer_V1.xlsx` | `ANNEX 6 - MODEL FINANCIAL OFFER_V1.xlsx` | — | 48 KB |
| `documents/Annex_9_Simulation_exercise_V1.pdf` | `Annex 9 - Simulation exercise_V1.pdf` | 3 | 522 KB |
| `documents/Draft_Framework_Service_Contract_V1.pdf` | `Draft Framework Service Contract_Digital Communications Services_V1.pdf` | 50 | 1 209 KB |
| `documents/Appendix_2_to_the_Draft_Framework_Service_Contract_V1.pdf` | `Appendix 2 to the Draft Framework Service Contract_V1.pdf` | 10 | 554 KB |
| `documents/Appendix_3_to_the_Draft_Framework_Service_Contract_V1.pdf` | `Appendix 3 to the Draft Framework Service Contract_V1.pdf` | 15 | 547 KB |

`Annexes_3-8_V1.docx` contains Annex 3 (agreement / power of attorney), Annex 4 (identified
subcontractors), Annex 5.1 and 5.2 (commitment letters), Annex 6 (pointer to the separate xlsx),
**Annex 7 (the T3 confirmation statement)** and **Annex 8 (the F1 economic & financial capacity
form)** — so the evidence templates for two of the six selection criteria live in this one file.

## Candidates considered and rejected

The 15-criteria bar was tested against **600 English-language CPV-72 `cn-standard` notices**
published since 2026-06-01, pulled through the TED Search API and ranked by the number of distinct
entries in `selection-criterion-description-lot`.

| Candidate | Why not |
|---|---|
| **The whole eForms field route** | The best English notice in the sample carried **13** distinct selection criteria (`489972-2026`); only 4 of the 600 carried more than 8, and 496 carried none at all. No English CPV-72 notice reaches 15 through `selection-criterion-description-lot` alone. |
| `612350-2026` — European Commission DG BUDG et al., "Development, Implementation, Maintenance and Operation of financial IT Systems" | The strongest alternative and worth keeping in mind: an inter-institutional framework across ~40 EU bodies, 29-page notice, ENG, deadline 2026-10-26, documents also on the F&T Portal. Rejected because at ~40 buyers and 2 lots it is an outlier in scale, not a case an SME would meet, and its notice likewise states "Sources of selection criteria: Procurement Document". |
| `601493-2026`, `546615-2026`, `589951-2026`, `599422-2026` — Malta, Department of Contracts / Water Services Corporation | English, EU, open, good CPV-72 subjects, but every notice delegates its criteria to the documents and the documents sit on `etenders.gov.mt/epps/cft`, a generic platform entry point with no per-tender deep link. |
| `625880-2026`, `621127-2026` — Ireland (IDA Ireland, Uisce Éireann) | Same pattern: `etenders.gov.ie/epps/cft`, zero criteria in the notice. |
| `545522-2026` — ESB (Ireland) | One selection criterion in the notice; no deadline published. |
| `489972-2026`, `610825-2026` — Ålesund kommune (Norway) | These are the only notices found that state 15+ criteria **in the notice itself** — see Reserve candidate below. Rejected as the committed fixture because Norway is EEA, not EU, and `CLAUDE.md` scopes the course build to the EU. |
| `444529-2026` — Statens Kartverk (Norway), SOC/IRT/MDR security services | 22 exclusion grounds enumerated in the notice and 8 selection criteria, but the deadline passed on 2026-08-31 and Norway is out of scope. |
| `431003-2026` — SPRIND GmbH (Germany), "Bug Bounty Program Services" | An EU buyer publishing in English, with the §§123/124 GWB exclusion grounds enumerated in the notice — the nicest oddity in the sample. Rejected: deadline passed 2026-07-06, and a German buyer's English notice is a weaker cross-border case for a German bidder. |
| `450905-2026` — Fluxys Belgium | 8 selection criteria, no deadline in the notice, documents behind `publicprocurement.be` publication workspaces. |
| `606362-2026` — the committed one | Its own weakness, stated plainly: the notice PDF carries **no** criteria, so the 15-criteria acceptance criterion is met by the *pack*, not by the notice. See below. |

## The honest caveat on S6.2's second acceptance criterion

S6.2 reads "*Given the notice, then it states at least 15 selection or exclusion criteria*". Read
strictly — criteria printed in the notice PDF — **this fixture does not satisfy it, and neither
does any EU English CPV-72 notice sampled on 2026-09-10.** EU-institution eForms notices and
Irish and Maltese notices alike answer "Procurement Document" for both criteria fields. The 20
criteria above are in the committed pack, which is where the brief for this story says they may be
counted, and which is where a real bidder reads them.

If the strict reading matters, the fix is `610825-2026` below; it costs the EU-only scope decision.

## Reserve candidate

`610825-2026` (Ålesund kommune, Norway — "IT services: consulting, software development, Internet
and support", ENG, deadline 2026-10-05) is the only open English CPV-72 notice found whose **notice
PDF alone** clears the bar: its 10 pages enumerate **21 named exclusion grounds** — corruption,
fraud, money laundering or terrorist financing, participation in a criminal organisation, terrorist
offences, child labour and trafficking, breaches of environmental / labour / social law, agreements
distorting competition, grave professional misconduct, conflict of interest, involvement in
preparing the procedure, early termination or comparable sanctions, unpaid social security
contributions, unpaid taxes, suspended business activities, bankruptcy, arrangement with creditors,
insolvency, assets administered by a liquidator — because the buyer set `Sources of grounds for
exclusion: Notice` rather than deferring to the documents, plus **10 selection criteria** in
`selection-criterion-description-lot`. That is ~31 criteria stated in the notice, and they are the
Directive 2014/24/EU Art. 57 set verbatim, so eCertis maps them cleanly.

It was not committed because Norway is EEA rather than EU and `CLAUDE.md` scopes the course build
to the EU, and because a notice-only fixture is a much softer extraction target than a 138-page
pack — the same argument ADR-0001 used to reject the notice-only option for Germany. Not
committed; re-downloadable from `https://ted.europa.eu/en/notice/610825-2026/pdf`, with its
documents on `https://tendsign.com/doc.aspx?MeFormsNoticeId=98867` (not probed).
