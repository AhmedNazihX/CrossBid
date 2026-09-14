# Decisions (ADRs)

One dated entry per architectural choice, written when the decision lands (story S7.2).
Format: context, options considered, choice, consequences. The 41 decisions settled in the
grill session of 2026-09-10 are listed at the top of `project-plan.md`; entries here record
what implementation actually forced, including where it contradicted the plan.

---

## ADR-0001 — The DE fixture is a real e-Vergabe document pack, fetched once at build time

**Date:** 2026-09-10 · **Story:** S6.1 · **Status:** accepted

### Context

S6.1 asks for a real German CPV-72 tender pack "downloaded from platforms that allow
anonymous access". Risk R2 anticipated that national platforms might require registration,
and set the mitigation as "fall back to notices whose documents are attached on TED itself".

That mitigation turned out not to be available. Of 100 recent German CPV-72 `cn-standard`
notices sampled through the TED Search API on 2026-09-10, **zero** hosted their procurement
documents on `ted.europa.eu`. Every `document-url-lot` pointed at a national platform —
`evergabe-online.de` (26), `dtvp.de` (22), `evergabe.nrw.de` (9), and roughly twenty others.
Each URL probed returned an HTML portal page, not a document.

So the choice was not "TED-hosted or national platform", it was "national platform, a notice
PDF only, or no real pack".

### Options considered

1. **Notice PDF only.** German eForms notices embed the `Eignungskriterien` and `Nachweise`
   as prose in the BT-750 fields, so an 11-page notice does carry real requirements. Clean
   provenance, zero tension with the no-scraping rule. But 11 pages of structured notice is a
   much easier target than a 191-page pack, so the recall figure would flatter the design and
   SP.1 would not actually test the core bet.
2. **Fetch the pack once from the national platform, by hand, for the fixture.** Faithful to
   the product premise. Requires deciding that a one-off build-time fetch is not what the
   "no scraping anywhere" rule prohibits.
3. **Ask the user to download it in a browser.** Same result as (2) with no rule question at
   all, at the cost of the user's time.

### Choice

Option 2, with the user's explicit authorisation on 2026-09-10.

The `CLAUDE.md` rule governs what **the agent does at run time**: Crossbid reads TED, eCertis
and Frankfurter through documented APIs, and the bidder uploads procurement documents by hand.
It never fetches from a national platform. `backend/tests/fixtures/` is build-time content,
not a run-time code path, and S6.1 explicitly sanctions the download.

Access is anonymous by law, not by loophole: §41 Abs. 1 VgV obliges German buyers to publish
the Vergabeunterlagen at an unrestricted, direct, free-of-charge internet address. The
platform asked for a cookie round-trip and nothing else — no account, no login.

### Consequences

- The DE fixture is the real pack for TED `614251-2026` (Beschaffungsamt des BMI, IPv6
  consulting, Los 2): **28 documents, 191 pages, 451 088 characters, 11 MB**.
- **Zero text-free pages**, so `pymupdf4llm` reads all of it and the OCR the plan cut
  (S2.1.2 notes) is genuinely not needed for this fixture. R3's parsing worry does not bite.
- e-Vergabe offers 48 files / ~42 MB, over S6.1's 15 MB ceiling. The 28 committed are every
  document carrying a requirement, contract term, or signable declaration; the exclusions are
  listed in `SOURCES.md` and are all re-downloadable.
- Nine filenames were transliterated (ä→ae, ö→oe, ü→ue, ß→ss): macOS stores umlauts as NFD,
  CI runs on Linux, and the NFD/NFC mismatch breaks path lookups. Contents untouched, original
  names recorded in `SOURCES.md`.
- **R2 is closed, but not as written.** The plan's stated fallback should be corrected: for
  German CPV-72 there is no TED-hosted-documents option to fall back to.
- The fixture happens to give the project its no-go walkthrough for free (see ADR-0002).

---

## ADR-0002 — The SP.1 golden set is hand-written, and scoped to the single-bidder base case

**Date:** 2026-09-10 · **Story:** SP.1 · **Status:** accepted

### Context

SP.1 scores extraction against "20 hand-picked mandatory requirements". S6.4 later allows
"LLM-assisted labels, hand-verified" for the full golden set. For SP.1 the labels *are* the
measuring stick, so how they are produced decides whether the number means anything.

The pack states its own mandatory list in three places: `Besondere Bewerbungsbedingungen`
§2 ("Verzeichnis der einzureichenden Dokumente"), `Kriterienkatalog Eignung`, and
`Eigenerklärung Ausschlussgründe`.

### Options considered

1. **LLM-assisted, then verified**, as S6.4 does. Cheaper, but the labels would be produced
   by the same class of model being measured, so a shared blind spot would silently raise the
   recall figure.
2. **Hand-written from the three documents.** Slower, independent of the model.

### Choice

Option 2. The list in `backend/scripts/spike_golden_de.yaml` was transcribed by reading the
three documents, one entry per distinct obligation, each with source document, page, and a
verbatim German quote. It came to **21 requirements**, not 20 — the pack's own list of
documents to submit is ten items, and splitting it further would have been arbitrary.

Scope is the **single bidder submitting alone**. Obligations that bind only a
Bietergemeinschaft, an Eignungsleihe, or a subcontractor are recorded under
`conditional_not_scored` and excluded from the figure: they are restatements of base
obligations for other legal persons, and scoring them would inflate recall with near-duplicates
of entries already counted.

### Consequences

- The recall figure measures 21 mandatory requirements across 47 sections of 191 pages.
- The pack sets hard, checkable thresholds — turnover ≥ €3 000 000/year, ≥ 29 VZÄ average
  staff, ≥ 3 references of ≥ 25 Personentage each. These exercise the numeric comparisons the
  matrix needs, not just document-presence checks.
- The demo GmbH has 25 staff against a 29 VZÄ minimum and €2.8m turnover against €3m, so this
  tender yields a genuine `no_go` with two concrete, quantified gaps. **The no-go walkthrough
  S7.4 needs comes free with this fixture**, and the demo company profile (S6.3) should keep
  those numbers rather than being tuned to pass.
- `conditional_not_scored` gives a later run something harder to score against, if the
  consortium path is ever built.

---

## ADR-0003 — SP.1 outcome: recall clears the gate; proceed to Increment 1

**Date:** 2026-09-10 · **Story:** SP.1 · **Status:** accepted — **GO**

### Context

SP.1 exists to test the assumption every later epic rests on, before any infrastructure is
built: that an LLM can extract the mandatory requirements of a real German tender pack, and
that retrieval then finds the company evidence for them. The gate: recall ≥ 0.70 after at most
two prompt iterations.

Measured on the real 191-page BMI pack (ADR-0001) against 21 hand-written mandatory
requirements (ADR-0002). Raw reports in `backend/scripts/spike_reports/`.

| | Run 1 — baseline | Run 2 — `stage` filter |
|---|---|---|
| Requirements extracted | 746 | 783 |
| Marked `mandatory` | 645 | 755 |
| Of those, `bid_eligibility` | — | **271** (484 dropped) |
| After dedupe | 579 | **238** |
| Golden requirements found | 21 / 21 | 21 / 21 |
| Recall (automated matcher) | **1.00** | **1.00** |
| Recall (hand-audited) | 0.90 | **0.95** |
| Cost | $1.32 | $1.40 |
| Wall clock | 1 038 s | 1 089 s |

Run 2 changed two things: a `stage` discriminator on the extraction schema
(`bid_eligibility` vs `contract_performance`, decided by "would a company still have to do this
if it never won the contract?") and a `checkable` flag.

### Choice

**GO.** Recall is 1.00 automated, 0.95 hand-audited, against a 0.70 gate. Increment 1 starts as
planned; section size (6 pages), the `pymupdf4llm` parser, structured output, and the model
slugs are all kept.

**The recall figure is reported with a caveat, because on its own it flatters the design.** In
run 1 it was measured against 579 candidates for 21 true requirements — with a set that large,
matching everything is close to guaranteed. Precision, not recall, is the real risk, and it is
the reason run 2 happened even though run 1 already passed.

Hand-audit of the matches: 20 of 21 carry the correct verbatim quote. Every quantified threshold
came out exactly right — `Der Umsatz muss mindestens 3.000.000,00 EUR pro Jahr betragen`,
`mindestens 29 VZÄ`, `mindestens 25 abgerechnete Personentage`, `nicht älter als drei Jahre`.
The one genuine miss is `EXCL-03` (§124 Abs. 1 Nr. 1 GWB, breach of environmental/social/labour
obligations), which the matcher paired at 0.68 with an ILO-norm question from the sustainability
annex — topically adjacent, wrong requirement, in both runs.

### Consequences

1. **`stage` belongs in the production model.** It cut the candidate set 579 → 238 with no
   recall loss. `models/requirement.py` (S0.4.1) gains a `stage` field, and `extract_reqs`
   (S3.2.1) filters to `bid_eligibility`. Without it the matrix carries the AGB, EVB-IT, VOL/B,
   framework-agreement and DPA duties — real obligations, but ones that bind the winner after
   award, not the bidder at qualification time.
2. **Checkability is a first-class property, and run 1 proved it the hard way.** All eight of
   run 1's checks returned `unclear`, because no company corpus can establish "we submitted form
   X". Only requirements asserting a *company property* are checkable against evidence. With
   the `checkable` flag steering which rows get checked, run 2 produced real verdicts:
   `FIN-01 unmet` (turnover below €3m in every reported year) and `TECH-06 unmet` (21 FTE
   against a 29 VZÄ minimum) — **the two gaps that make this tender a genuine `no_go`** — plus
   `TECH-04`, `TECH-05`, `EXCL-02` correctly `met`. S3.3.1 must route
   `document_submission` rows to the reviewer as "attach this document" instead of spending
   tool calls on RAG that cannot answer.
3. **The 10-minute budget in S3.1.1 is already blown by extraction alone.** 47 sequential
   extraction calls take ~18 minutes before `check_reqs` runs at all. The plan only fans out
   `check_reqs` (`Send`, concurrency 5); **extraction must fan out too**. This is the most
   concrete change SP.1 forces on S3.2.1, and it revises R9.
4. **Cost does not fit either.** $1.40 for extraction and scoring alone, against a $2.50
   budget for a whole bid *including* `check_reqs` over 238 rows at up to 4 tool calls each.
   Either the row count comes down further, or the budget goes up. Recommend deciding this when
   S3.3.1 lands, with the stage filter in place.
5. **The recall matcher needs to be stricter than cosine-over-threshold.** `EXCL-03` is a false
   positive in both runs at 0.68 against a 0.62 threshold. S3.2.3's matcher is reused by S7.1's
   eval report, so a loose matcher there would inflate a **graded** metric. Raise the threshold,
   require the matched quote to come from the expected document, or judge matches with an LLM.
6. 238 rows is still roughly 10× the 21-requirement base case, though the honest comparison is
   larger than 21 — the golden set deliberately excludes consortium, Eignungsleihe and
   subcontracting variants (ADR-0002), and the *Kriterienkatalog Leistung* and sustainability
   annex contribute legitimate rows. Treat 238 as "2–4× too many", not "10× too many", and
   revisit once the matrix is on screen in Increment 2.
7. SP.1's two permitted iterations are used. The spike stays at
   `backend/scripts/spike_extract.py` until S3.2.1 lands, then it is deleted per the story.

## ADR-0004 — Default embedding is `openai/text-embedding-3-small` (1536 dims)

**Date:** 2026-09-10 · **Story:** SP.1 (verification) · **Status:** accepted · **Supersedes** the
plan's `text-embedding-3-large` default and its `baai/bge-m3` fallback

### Context

The plan named `openai/text-embedding-3-large` (3072 dims) as the default embedding and
`baai/bge-m3` (1024 dims) as "the cheap multilingual switch". bge-m3 also carried R3: pgvector's
HNSW and IVFFlat indexes cap at 2000 dimensions, and dropping to 1024 was one of two stated
escape routes if the corpus outgrew a sequential scan.

Probing `POST /api/v1/embeddings` on 2026-09-10 showed the fallback does not exist on this
account, and that OpenRouter's embedding catalogue is much thinner than assumed. There is no
`/models` listing for embeddings — `?category=embedding` returns HTTP 400 — so each slug has to
be probed directly.

**Usable on this account:**

| Slug | Dims | Price | FR→DE top-1 |
|---|---|---|---|
| `openai/text-embedding-3-small` | 1536 | ~$0.027/1M | 7/8 |
| `openai/text-embedding-3-large` | 3072 | $0.13/1M | 6/8 |
| `qwen/qwen3-embedding-8b` | 4096 | ~$0.057/1M | 7/8 |

**HTTP 404 — "0 endpoints … available matching your guardrail restrictions and data policy":**
`baai/bge-m3`, `google/gemini-embedding-001`, `openai/text-embedding-ada-002`. This is the
account's own privacy/data-policy setting, not an OpenRouter outage; relaxing that setting would
unblock them.

**Not on OpenRouter at all:** Cohere (`embed-v4.0`, `embed-multilingual-v3.0`),
`mistralai/mistral-embed`, `voyage/voyage-3.5`, `nomic-ai/nomic-embed-text-v1.5`,
`jina-ai/jina-embeddings-v3` — all HTTP 400 "does not exist".

The FR→DE column is a purpose-built check of the wedge's second assumption, that cross-lingual
retrieval finds German evidence for a French requirement: eight French queries phrased as a
French tender would phrase them, scored top-1 against the 14-fact stand-in company corpus.

### Options considered

1. **Keep 3-large, put 3-small in the fallback slot.** Preserves the settled decision. R3 stays
   live: sequential scan now, `halfvec` later.
2. **Make 3-small the default.** 1536 dims is under the index cap, so R3 stops existing. ~5×
   cheaper. Scored 7/8 against 3-large's 6/8.
3. **Defer to S7.1** and let golden-set recall pick the winner.

### Choice

Option 2. `openai/text-embedding-3-small` is the default; 3-large stays configurable as the
quality switch; `qwen/qwen3-embedding-8b` is the non-OpenAI multilingual option; bge-m3 is
dropped.

The deciding argument is timing, not the scores. The plan itself notes that changing this slug
"means re-embedding and a column dimension change" — but **nothing is embedded yet; there is no
database**. The change is free today and costs a migration once S2.2.1 lands in Increment 1. A
dimension count that fits pgvector's index cap is a structural property worth locking in while
it is still free.

The 7/8-vs-6/8 result is explicitly **not** treated as proof that 3-small is the better model:
eight queries against a 14-line synthetic corpus is far too small a sample. It is read only as
"not measurably worse", which is enough when the structural advantages are this clear. S7.1
measures both on the real golden set and may reverse this.

### Consequences

- `company_chunks.embedding` and `tender_chunks.embedding` are `vector(1536)`, not
  `vector(3072)`. The Data model section of the plan still shows 3072 and must be corrected when
  S0.2.3 writes the migration.
- HNSW/IVFFlat are available from the start, so S2.2.1 can index rather than accept a
  sequential scan. **R3 is closed.**
- Embedding cost drops roughly 5×. Minor against LLM cost, but it makes re-embedding the whole
  corpus during tuning cheap enough not to think about.
- The spike keeps using 3-large for its own recall scoring (`SPIKE_EMBED_MODEL` overrides it),
  so that iteration 2 changes only the extraction prompt and the two runs stay comparable. The
  spike's matching threshold is calibrated per model and is a scoring device, not a product
  setting.
- All three models missed one case: "inscription au registre du commerce" never retrieved the
  `Amtsgericht Köln HRB 84512` line, which is terse and bundled with founding date and seat.
  **A note for S6.3**: evidence facts need descriptive surrounding text, or a short registry
  line will not retrieve for the requirement it satisfies.
- The two chat slugs were confirmed live in the same check at documented prices:
  `openai/gpt-5.6-terra` $2/$12 per 1M and `openai/gpt-5.6-luna` $0.20/$1.20 per 1M, both
  advertising `structured_outputs`, `response_format`, and `tools`.

---

## ADR-0005 — Keep OpenRouter's strict data policy; judge is `anthropic/claude-haiku-4.5`

**Date:** 2026-09-10 · **Stories:** S7.1, S5.1, S0.3.2 · **Status:** accepted

### Context

The plan named `anthropic/claude-sonnet-5` for two jobs: the DeepEval judge in S7.1 (whose
acceptance criterion is that "the judge model is from a different vendor than the model under
test") and the vendor-switch example in S5.1's multi-model demo, which carries graded Medium 7.

Live calls on 2026-09-10 show `claude-sonnet-5` returns **HTTP 404** on this account. It is
listed in `/models`, so the earlier verification — which only read the catalogue — recorded it
as available. It is not.

The error text is the same one `baai/bge-m3` produced in ADR-0004: *"0 endpoints out of 6
requested are available matching your guardrail restrictions and data policy."* The account's
privacy setting rejects every provider endpoint serving that model. This is a single account
setting silently shaping the entire usable model list.

Probed with live calls, **usable non-OpenAI chat models**:

| Slug | in / out per 1M | structured outputs |
|---|---|---|
| `anthropic/claude-haiku-4.5` | $1.00 / $5.00 | yes |
| `google/gemini-2.5-flash` | $0.30 / $2.50 | yes |
| `google/gemini-2.5-flash-lite` | $0.10 / $0.40 | yes |

**404 on this account:** `claude-sonnet-5`, `claude-opus-5`, `claude-sonnet-4.5`,
`gemini-2.5-pro`, `gemini-2.0-flash-001`, `deepseek-chat-v3.1`, `llama-4-maverick`,
`qwen3-235b-a22b`, `mistral-medium-3.1`, `nova-pro-v1`, `command-a`.

### Options considered

1. **Relax the account's data policy** and keep the plan verbatim. Unlocks Sonnet-5,
   Gemini-Pro, DeepSeek, Llama, Qwen and bge-m3. No documentation churn.
2. **Keep the policy strict and change the slugs.** Judge becomes Haiku 4.5; the multi-model
   demo uses OpenAI / Anthropic / Google as its three vendors.
3. Keep it strict with `gemini-2.5-flash` as judge — 3× cheaper, strong multilingually, but a
   weaker general reasoner.

### Choice

Option 2, chosen by the user.

The policy is kept strict **as a product property, not as an accident**. That setting governs
whether providers who may train on submitted prompts are allowed, and Crossbid feeds the model
a bidder's own evidence documents — register extracts, tax certificates, insurance, reference
letters — plus procurement packs. For a product positioned on EU cross-border compliance, "no
provider may train on this" is worth more than access to a slightly stronger judge. Recording
it here turns an invisible account toggle into a stated constraint.

`anthropic/claude-haiku-4.5` is the judge: the strongest available non-OpenAI reasoner, and
still a different vendor from the `openai/gpt-5.6-*` models under test, so S7.1's acceptance
criterion is met as written. Judge cost across 3 golden tenders is on the order of $1.

### Consequences

- S7.1's judge slug is `anthropic/claude-haiku-4.5`. S5.1's vendor switch offers
  `openai/gpt-5.6-terra`, `openai/gpt-5.6-luna`, `anthropic/claude-haiku-4.5`,
  `google/gemini-2.5-flash`, `google/gemini-2.5-flash-lite` — three distinct vendors, so
  **graded Medium 7 is satisfiable** and Easy 3 ("choose from a list of LLMs") has a real list.
- The dev panel's model picker must be populated from this verified list, not from
  `/models`. A picker built off the catalogue would offer options that 404 at run time.
- **Process lesson, the reason this ADR matters beyond the slug:** presence in `/models` does
  not imply usability. The 2026-09-10 pre-build verification checked the catalogue and recorded
  Sonnet-5 as available; two of the plan's model claims were wrong as a result. Every model
  slug this project depends on must be confirmed with a live one-token call, and S0.3.2 should
  fail fast at startup if a configured slug does not answer.
- BYOK (S5.4–S5.6) gains value it did not have in the plan: a user supplying their own
  Anthropic or OpenAI key bypasses this account's guardrails entirely, so the models available
  to them are wider than the app's defaults. The provider-selection UI should not assume the
  app's model list applies to a company running on its own key.
- If the policy is ever relaxed, ADR-0004's bge-m3 finding and this entry both reopen.

---

## ADR-0006 — FR and EN fixtures; S6.2's "15 criteria in the notice" is met by the pack

**Date:** 2026-09-10 · **Stories:** S6.1 (FR), S6.2 · **Status:** accepted

### Context

S6.1 needed a French CPV-72 pack and S6.2 an English notice stating "at least 15 selection or
exclusion criteria, so the golden set is not trivial".

**FR — TED `618320-2026`**, Ministère de l'éducation nationale, "Prestations de conseil en
architecture d'entreprise et d'expertise technique", CPV 72000000, `official-language` FRA,
deadline 2026-10-09. Committed: the French notice PDF, the *Règlement de consultation* (20 pages,
55 820 characters) and the buyer's `DUME_acheteur.xml`. 25 PDF pages, 0 text-free pages, 776 KB.
Both documents came from plain `GET` links on the public PLACE consultation page — no login, no
form. The full 14.7 MB DCE sits behind a POST form which does offer a genuinely anonymous route
("Je souhaite télécharger anonymement"); it was left for a human, with the URL in `SOURCES.md`.

**EN — TED `606362-2026`**, EASA, "Digital Communications Services", CPV 72400000, deadline
2026-10-12. The EU Funding & Tenders Portal served the whole 4.6 MB pack to a bare `curl` — no
cookie, no form. All 9 files committed unmodified. 138 PDF pages, 0 text-free pages.

### The deviation

**The EASA notice itself states zero criteria** — both criteria fields say "Sources: Procurement
Document". The 20 criteria (14 exclusion + 6 selection) are in `Tender_Specifications_V1.pdf`
§3.1–3.2 and `Annex_2_Declaration_on_Honour`, and the derivation is tabulated in `SOURCES.md`.

This is not a bad fixture choice; it is how the market works. Across **600** English CPV-72
`cn-standard` notices published since 2026-06-01, the maximum criteria count carried *in the
notice* was **13**, only 4 notices exceeded 8, and 496 carried none. The only notices clearing 15
in the notice body are Norwegian, where buyers set `Sources: Notice` — e.g. `610825-2026`
(Ålesund kommune) prints 21 named Article 57 exclusion grounds plus 10 selection criteria.

### Options considered

1. **Accept the pack-level count.** The EASA pack states 20 criteria; the fixture is rich and
   its documents are the most openly accessible of any platform surveyed.
2. **Promote the Norwegian notice**, which satisfies the criterion literally. But Norway is EEA,
   not EU, and `CLAUDE.md` scopes the course build to the EU — and a notice-only fixture is
   exactly the soft target ADR-0001 rejected for Germany.

### Choice

Option 1, and **S6.2's acceptance criterion is amended**: the 15-criteria bar is met by the
committed pack, not necessarily by the notice PDF. The intent behind the criterion — "so the
golden set is not trivial" — is satisfied at 20 criteria. Requiring them in the notice body
would force either an EEA fixture or a weaker one. `610825-2026` is recorded in the EN
`SOURCES.md` as a reserve if a notice-only English fixture is ever wanted.

### Consequences

- Three fixtures now exist: DE 191 pages, EN 138 pages, FR 25 pages, **all with zero text-free
  pages**, so OCR stays out of scope across the whole golden set.
- **The FR fixture changes what the matrix has to model.** Germany used pass/fail minima; this
  French buyer scores selection on a 10-point scale with numeric bands (turnover > €1.95M → 3/3,
  7–12 staff → 2/3, ≥ 4 references → 2/2, quality certification → 2/2) and **eliminates below
  5/10**. The rules-based scorer in S3.4.1 must handle a weighted threshold, not only "unmet
  mandatory ⇒ no_go". Against the demo GmbH this tender scores 6/10, a **go** — so the golden set
  now yields a no-go (DE) and a go (FR) without any tuning.
- The FR notice states the wedge in the buyer's own words: *"Le candidat non établi en France
  produit les attestations et certificats équivalents dans son pays d'origine"*, then names
  URSSAF, fiscal, SIREN and D.8254-2 evidence a German bidder does not have. This is the
  cross-border equivalence problem, verbatim, in a real tender.
- **The DUME is a structured shortcut and should be treated as one.** `DUME_acheteur.xml`
  declares 30 `ccv:Criterion` elements carrying canonical ESPD criterion UUIDs, in French. Where
  a tender publishes a DUME, criterion identification needs no LLM inference — read the ids.
  Worth a follow-up story; not in the current plan.
- TED API facts corrected in `CLAUDE.md`: `SORT BY ... ASC` is HTTP 400, pagination caps at 600
  results, and `selection-criterion-description-lot` is populated on only 14–17% of notices.
  That last figure is the strongest evidence yet for the upload-the-pack design.

---

## ADR-0007 — The criterion enum is keyed on eCertis EU-level UUIDs, never national ones

**Date:** 2026-09-10 · **Stories:** S1.1.1, S1.1.3 · **Status:** accepted

### Context

The extractor assigns each requirement a nullable `ecertis_criterion_id`, and the matrix uses it
to look up which national document proves that criterion. The plan's note said
`criteria?nationalEntity=de` "lists the national criteria for a country", which reads like an
invitation to key the enum on a national list.

Implementing the cache showed that would silently destroy the cross-border wedge:

- `GET criteria` returns **56** EU-level ESPD criteria.
- `criteria?nationalEntity=de` returns **the same 56 criteria under different, country-scoped
  UUIDs**. So does `nationalEntity=fr`. The DE and FR id sets are disjoint from each other **and**
  from the bare EU set. `nationalEntity=eu` returns 58 rows.
- Verified in the committed cache: national `sub_criteria[].id` values have **zero** overlap with
  the EU criterion ids.

The national listing and the national subtree share one id space, but the listing is a **lossy
view** of it — which is the second reason not to build from it:

- `criteria?nationalEntity=de` returns **one** sub-criterion per EU criterion: 56 rows, the
  primary one. 55 of those 56 ids appear verbatim as `sub_criteria[].id`, each under the same EU
  criterion (0 mispairings). The one absentee is "Direct or indirect involvement in the
  preparation of this procurement procedure", whose `countryFilter=de` detail call returns a
  stable empty 200.
- `criteria/{eu_uuid}?countryFilter=de` returns the **full** national subtree: **104**
  sub-criteria for the same 56 criteria.

So building the cache from the national listing would have under-reported German evidence by
roughly half while looking perfectly plausible. "Payment of taxes" has three German
sub-criteria; only one of them is in the listing, and the detail-only pair includes
`Bescheinigung in Steuersachen`.

A criterion id chosen from the German list therefore means nothing when looking up French
evidence — which is precisely the operation this product exists to perform.

### Choice

**The EU-level UUID from the bare `GET criteria` call is the only cross-border identifier**, and
it is what `criteria.json` and the generated `EcertisCriterionId` Literal use. Both
`evidence_de.json` and `evidence_fr.json` are keyed by EU id, with national ids retained one
level down as `sub_criteria[].id`. Verified: both files' key sets equal the EU id set exactly.

Two consequences of the API forced further decisions:

**Empty 200 means "no national entry".** eCertis answers HTTP 200 with a zero-byte body for a
criterion a country has no entry for — 17 of 56 for FR, 1 of 56 for DE. Genuine transient
emptiness also occurs and is indistinguishable at the wire level. Policy: retry 3× with 2s/4s
backoff; treat a persistent empty as "no evidence"; and **refuse to overwrite a cached criterion
that previously had evidence and now has none** (`--allow-shrink` to override). A silent
regression in a committed cache would be invisible until a demo.

**The taxonomy has to be stitched in.** `GET criteria` omits `CriteriaTypeName`, sending only a
meaningless `CriteriaTypeID`, so the bare list cannot tell an exclusion ground from a selection
criterion. Labels come from one extra `criteria?nationalEntity=eu` call; they are byte-identical
across countries, so this is an EU-level taxonomy the bare endpoint simply forgets. Result: 8
labels covering all 56 criteria — 18 technical/professional, 15 insolvency and misconduct,
8 economic/financial, 6 criminal convictions, 4 suitability, 2 taxes, 2 quality/environmental,
1 other.

### Consequences

- Cached: 56 criteria; DE 104 sub-criteria / 218 evidences; FR 68 / 94. ~500 KB total, committed.
- **Idempotence is content-addressed**, which the "a second run changes nothing" criterion
  requires: `source_date` is carried over verbatim while a SHA-256 over the canonical body
  (excluding `source_date` and the hash itself) is unchanged. No `fetched_at` anywhere. Every
  list has a total sort order; whitespace is collapsed because eCertis returns values like
  `"competent tax office\n"`. Verified byte-identical across three runs.
- The loader recomputes that hash on read, so a hand-edited cache file is **refused** rather than
  silently trusted.
- Run time is filesystem-only. Verified by replacing `socket.socket`, `create_connection` and
  `getaddrinfo` with raisers: all three files still load and resolve evidence.
- **The wedge, demonstrated on real data.** EU criterion "Payment of taxes" →
  DE `Certificate on the payment of taxes`, `Freistellungsbescheinigung`; FR
  `Tax attestation (IR) - Cerfa n°3666`, `Tax attestation (IS)`. Same criterion, different paper.
- FR has no national entry for 17 of 56 criteria, so S1.1.2's `not_found` path is the common case
  for France, not an edge case. The UI must present it as "no French equivalent recorded", not as
  an error.
- The undocumented `?lang=de` parameter returns German (marked `(Automatische Übersetzung)`) and
  is the cheap route to S1.1.2's "in German and English" requirement. Not cached — it doubles the
  fetch — but worth knowing before building that story.

### Bugs the test suite exposed (S1.1.1 hardening)

Writing the 131-test suite surfaced three defects in code that had already passed lint, types
and a live rebuild. Recorded because each is a class of bug this codebase will meet again.

1. **Order-dependent "take the first value".** Three helpers took whichever value eCertis
   happened to send first. Latent today, since every such list holds one value — but a live
   idempotence hazard the moment one holds two, and idempotence is S1.1.1's acceptance criterion.
   Now smallest-non-empty.
2. **Silent data loss when merging duplicated evidence.** An evidence id referenced from two
   `RequirementGroup`s kept only the first occurrence. **53 evidences in the committed cache
   (49 DE, 4 FR) are referenced from more than one group.** All 53 pairs happen to be
   byte-identical today, so the output was correct *by luck*; eCertis promises no such thing, and
   a stub arriving first would have erased issuer, jurisdiction and URL. Now merged field by
   field. Found by a hand-built fixture, not by real data — the real data hid it.
3. **A memoised loader keyed on un-normalised input.** `load_evidence("DE")` and
   `load_evidence("de")` were separate cache entries, parsing and holding the 324 KB German file
   twice. Normalisation has to happen *before* the memoised call, not inside it.

Behaviour preservation was proven, not assumed: all 94 recorded live responses re-normalised
with **0 differences**, **0 order-dependent results across 282 shuffle checks**, and a full live
rebuild produced byte-identical files (all four checksums unchanged).

The lesson worth carrying: real API data is a weak test of merge and ordering logic, because it
is accidentally well-behaved. The bugs appeared only under hand-built adversarial fixtures and
shuffled input. Later stories that merge or deduplicate — the extraction dedupe pass in S3.2.1
above all — should be tested the same way.

---

## ADR-0008 — Contracts, parsing, chunking and settings

**Date:** 2026-09-10 · **Stories:** S0.4.1, S0.3.2, S0.3.3, S2.1.1, S2.1.3 · **Status:** accepted

Four decisions from the same batch of work. Grouped because each is small on its own and they
share one theme: putting invariants somewhere a later story cannot quietly violate them.

### Invariants live in the models, not in the callers (S0.4.1)

`crossbid/models/` is the contract layer, and the rules that matter are enforced by validators
rather than trusted to graph nodes:

- **A `MET` row must carry a citation or an attached document.** This is the product's central
  promise — every matrix cell cites or says unclear. A row the agent believes is satisfied but
  cannot cite is `UNCLEAR`, which routes it to a human instead of counting towards a `go`.
- **A blocking gap forces `no_go`, and `no_go` requires a blocking gap.** A verdict that
  contradicts its own gap list would mislead the reviewer, and the reviewer is the safety
  boundary.
- **An override requires a reason**, because the review record is the audit trail.
- **A weighted score below the buyer's threshold must appear as a blocking gap** (ADR-0006),
  or a bid could be recommended while sitting below the buyer's own cut-off.

SP.1's findings are now types rather than prose: `RequirementStage` and `Checkability` carry the
reasoning from ADR-0003 in their docstrings, and `ecertis_criterion_id` is typed against the
generated 56-id Literal so the extractor cannot invent a criterion.

Two structural tests exist because nothing else would catch their failures: one asserts
`models/` imports nothing else from `crossbid` (a stray import would compile, pass every other
test, and invert the layering), and one asserts the criterion annotation has not silently
degraded to `str | None`.

### Parsing is a Protocol so Docling can slot in, and unread pages are stated twice (S2.1.1)

`Parser` is a `runtime_checkable` Protocol taking `Path | bytes` (so an upload needs no temp
file) and returning `ParsedDocument`. No backend types appear in the signature, and every
library exception is funnelled into one `ParserError`, so a caller never catches a pymupdf
error and swapping implementations changes no call site.

The decision worth recording: **`ParsedDocument` validates that `pages` is the complete run
1..N, and `unread_pages` is a computed field derived from `pages`.** A second implementation
cannot *disagree* about which pages were readable, because it does not get to say. That is what
makes S2.1.2's "the page count and shape match the default parser" checkable rather than
hopeful. An unread page stays in `pages` with empty text **and** appears in `unread_pages` —
listed twice, never dropped, because OCR was cut and "we could not read it" is the honest
terminal state.

**The trap this uncovered:** `pymupdf4llm` returns `"\n\n\n\n"` for an image-only page, not
`""`. A `text != ""` check would have called it readable and emitted a chunk of whitespace —
and ADR-0003's cheerful "zero text-free pages" would have hidden it, because no real fixture
has such a page. It was found only by *building* one. Recorded in `CLAUDE.md`.

### A chunk cites the page it starts on (S2.1.3)

`Chunk.pages` is every page the text came from; `Chunk.page` is `pages[0]`. First page, not
majority share: the reviewer opens one page and reads forward from the top of the retrieved
passage, and the passage begins there. A majority page can sit past the beginning of the
evidence, which is the wrong place to land someone. `pages` stays honest when pages are not
adjacent — if only the middle of three pages was unreadable, a chunk cites `(1, 3)`.

Measured with the 800/100 defaults: DE 191 pages → 202 chunks, 174 of them exactly 800 tokens;
FR 25 → 25; EN 138 → 109. **Zero non-final chunks fall outside ±10% of target** across all 28
DE documents; the 28 short chunks are exactly the 28 document tails, which is arithmetic rather
than a defect.

`cl100k_base` is pinned by name, because it is exact for `openai/text-embedding-3-small` — the
only consumer with a hard limit — while `encoding_for_model` raises `KeyError` on an OpenRouter
slug. Since `get_encoding` downloads its table on first use, the chunker takes an injectable
encoder so tests stay offline.

### Settings: secrets and behaviour never overlap (S0.3.2, S0.3.3)

Precedence is `settings.default.yaml` → `app_settings` row for **behaviour**, and environment →
root `.env` for **secrets and wiring**. The two sets of keys are disjoint, so "which one wins"
is never a judgement call. `RuntimeSettings` uses `extra="forbid"`, so a typo'd YAML key fails
at startup instead of doing nothing.

- Secrets are `SecretStr` and a test asserts no key appears in `repr`, `str`, or a JSON dump —
  including a password embedded in `DATABASE_URL`.
- Fail-fast messages are built from the error's *location*, never its input, so a bad value
  cannot leak through a validation error.
- **The transaction-pooler guard** refuses a DSN only when the host ends `.pooler.supabase.com`
  *and* the port is 6543, or when `pgbouncer=true` is present. Port 6543 alone is not the
  signal, because a local database could legitimately be mapped there. Compose, CI, the direct
  connection and the session pooler all pass; the message names the session pooler as the fix
  and prints only `host:port`, never credentials.
- `AUTH_MODE=dev` with `ENV=production` is refused at startup, and `ENV` is a closed enum so
  `ENV=prod` fails rather than quietly meaning "not production" and letting dev auth through.
- The no-key tracing path writes `false` to all four LangSmith flags and logs nothing —
  asserted with `caplog.records == []`. Writing only one flag would let a developer's stale
  exported value win.
- The `app_settings` override is implemented as a pure merge returning a **new** `Settings`;
  only the database *fetch* is left unimplemented, typed and pointing at S0.2.3.

### Consequences

- 334 tests, 100% line and branch coverage, all offline.
- Six defects in the config files were found by the story that consumed them, and fixed:
  `settings.default.yaml` had no `system_prompt` despite S0.3.2 asking for one (now present,
  and it is where the untrusted-data rule is stated to the model); `.env.example` did not
  document `VERIFY_MODEL_SLUGS`, `ENV=test`, or that the app owns the LangSmith flags; it
  claimed the Compose Postgres would be used when `DATABASE_URL` was unset, but **nothing in
  the backend derives a DSN from the `POSTGRES_*` variables** — only Compose does — so a host
  `make dev-api` had no database at all; and the `APP_ENCRYPTION_KEY` placeholder passes the
  presence check while not being a valid Fernet key, so `crypto.py` must validate its shape at
  startup when S5.4 lands.
- One test was rewritten rather than deleted: it had pinned the missing `system_prompt` as
  expected behaviour. Once the gap was fixed, the test asserts the prompt loads and states the
  untrusted-data rule.

---

## ADR-0009 — Schema, migrations, the data-block guard, and the generated API client

**Date:** 2026-09-10 · **Stories:** S0.2.1, S0.2.3, S2.3.2, S0.4.2 · **Status:** accepted

### Tenant isolation stays application-level, on evidence rather than preference

The `supabase-postgres-best-practices` guidance rates RLS **CRITICAL** for multi-tenant data,
and its "incorrect" example is precisely this project's settled decision. That deserved a check
rather than a citation, so the connection was inspected:

```
current_user = postgres   superuser = false   BYPASSRLS = true
```

**RLS policies would be silently inert on this connection.** Making them real needs a dedicated
non-`BYPASSRLS` role, its grants, and a different DSN — genuine scope for a project already
over its time estimate. So application-level `company_id` filtering stands, but the schema is
built to make RLS *additive* later rather than a rewrite: `company_id NOT NULL` on all ten
tenant-scoped tables, every composite index leading with it, and a test asserting both.

The honest cost: a bug in one query's `WHERE` clause leaks another company's data with no second
line of defence. That is the trade, stated plainly.

### Primary keys: UUIDs where they appear in URLs, `bigint identity` elsewhere

The guidance prefers `bigint identity` and warns that random UUIDv4 fragments indexes. Both
points are correct and neither decides this case: `pg_uuidv7` is not available on this project
and the server is PG 17 (no built-in `uuidv7()`), so time-ordered UUIDs are off the table.

Ids appear in URLs (`/bids/{id}`), and with no RLS backstop an enumerable `/bids/1` lets one
company probe for another's bids. At this corpus size index fragmentation is measurable in
neither time nor space, so the ranking is clear: UUIDs for URL-addressed tables, `bigint
identity` for append-only internals never addressed by id (`company_chunks`, `tender_chunks`,
`llm_usage`, `feedback`).

### Enum columns are `text` + check constraint, and a test guards the parity

Postgres enum types are awkward to alter in migrations, so enum columns are `text` with a check
constraint. That buys migration ease at the cost of a silent-drift risk: adding a value to a
Pydantic `StrEnum` and forgetting the migration type-checks cleanly, tests green, and then
raises `IntegrityError` the first time a node writes the new value.

So `tests/unit/test_migrations.py` asserts, per constraint, that its value list equals the
enum's — **and guards the guard**: any new `in (...)` constraint without a parity entry fails
the suite. Writing that test immediately found a real gap — `documents.kind` had a database
constraint and **no Pydantic contract at all**. `DocumentKind` now exists.

Two invariants are enforced in *both* layers, because a direct SQL write bypasses Pydantic: a
`met` row must cite something, and an override must record a reason.

### Migrations are immutable once applied

`scripts/migrate.py` records a SHA-256 per applied file and **refuses to run if an applied file
has changed**. The database reflects what the file said when it ran; re-running an edited file
cannot reconcile the two, so failing loudly is the only honest option — add a new numbered file.
It also refuses a badly-named file rather than skipping it (a silent skip diverges the schema,
the worst failure mode), and takes an advisory lock so a developer and a deploy hook cannot
interleave.

Verified against the live Frankfurt database: first run applied, second reported "up to date".

### The data-block guard uses a per-call unguessable tag

S2.3.2's delimiters carry a one-time `secrets.token_hex(8)` tag minted **after** the document is
read. The reasoning is elimination, and it is worth recording because each rejected option is
tempting:

- **Escaping the content is not available.** The product promises a verbatim quote and a page
  the reviewer opens. Rewriting content would let the model quote text that is not in the file.
- **Rejecting documents containing the delimiter is not available.** `<document>`, `-----BEGIN`
  and XML fragments occur legitimately — the FR fixture ships a DUME XML.
- **A fixed delimiter is published in our own source**, so a PDF author can close the block early.

What remains is unguessability. The tag is counted in the finished text and a wrong count throws
the candidate away and mints another (8 attempts, then it fails shut) — so the postcondition and
the collision check are the same line and cannot disagree.

Two design points that matter more than the delimiter shape:

1. **The operative instruction sits after the block as well as before it.** A block can be
   thousands of tokens, and an instruction given only up front competes with everything the
   document said since — which is the attack.
2. **Content is inviolable; metadata is normalised.** An uploaded filename is as
   attacker-controlled as the body, so labels are `json.dumps`-quoted (which is what keeps the
   header on one line whatever the filename holds), invisible Unicode is stripped from labels
   but preserved verbatim in content, and a missing page renders `pages="unknown"` rather than
   omitting the attribute — an absent attribute reads as "any page".

The system prompt was hardened to match: it now states the tag convention, and that **the block's
`DOCUMENT` header is the only authority for a name and page** — a document's own claim about
which file or page it is is content, never a citation.

**Residual, stated plainly:** this story delivers the wrapper. Nothing yet *enforces* that every
prompt uses it, because there are no prompt builders to enforce it on. When `extract_reqs`
lands (S3.2.1), its tests must assert that document text reaches a prompt only via
`wrap_as_data`.

### The CI staleness check was a no-op

S0.4.2's second criterion is "given a stale generated file, then CI fails". It would not have
held: the step ran `git diff --exit-code -- frontend/lib/api.ts` with `cwd = frontend/`, and git
pathspecs are relative to cwd, so it resolved to `frontend/frontend/lib/api.ts` — matching
nothing and exiting 0 however stale the file was. Verified by tampering with the tracked file:
as written `exit=0`, corrected `exit=1`.

Two further defects in the same step: a now-dead skip guard, and `uv sync && uvicorn &`
backgrounding the *whole chain*, so a cold cache raced the wait loop and the loop had no failure
exit — the job would have died inside `openapi-typescript` with a misleading message.

Worth knowing for later: `openapi-typescript` emits components in schema order, which FastAPI
derives from route registration order, so **reordering routers produces a real `api.ts` diff with
no model change**. A correct diff that will look like flakiness.

### Consequences

- 414 tests, 100% line and branch coverage, all offline; 13 tables live in Frankfurt with
  pgvector 0.8.2, HNSW indexes on both chunk tables, and zero foreign keys missing an index.
- `max_connections = 60` on this project, shared with `PostgresSaver` and `PostgresStore`. The
  psycopg pool must be sized deliberately in S0.2.2, not left at a default and discovered under
  the `check_reqs` fan-out.
- HNSW is approximate and pgvector applies the `company_id` filter *after* the ANN scan, so a
  small tenant inside a large corpus can lose recall. At this size the planner often prefers an
  exact sequential scan anyway; partial per-company indexes are the lever if it grows.

## ADR-0010 — One pool, sized by hand; the checkpointer and Store share it

**Date:** 2026-09-10 · **Stories:** S0.2.2 · **Status:** accepted

### The connection budget is a measured number, not a default

`show max_connections` on the Supabase project is **60**; `superuser_reserved_connections` is
**3**; and `pg_stat_activity` held **12** sessions with nothing of ours connected — Supabase's
own pooler, auth, storage and realtime services. That leaves about 45 for everything we start:
the API, the migration runner, a developer's `psql`, and a second API process when Compose and
`make dev-api` run side by side.

`crossbid/db.py` therefore pins those three figures as named constants, derives the headroom
(45) and a ceiling of half of it (22, "two processes must coexist"), defaults to a pool of
**10**, and refuses a larger `max_size` with an error that shows the arithmetic. The numbers are
also asserted by a test, so a change to the project is a change someone makes knowingly rather
than a surprise under the `check_reqs` fan-out — where the failure would read
`FATAL: too many clients`, which says nothing about pooling.

### What the library actually does with a pool decides who can use the budget

Read in langgraph-checkpoint-postgres 3.1.2 rather than assumed, because the two clients
behave differently in a way the documentation does not mention:

- **`AsyncPostgresSaver._cursor` holds one `asyncio.Lock` per saver around every operation,
  pool or not.** The checkpointer never uses more than one connection at a time; concurrent
  graph branches queue on the lock, not on the pool. Pool size does nothing for checkpoint
  throughput.
- **`AsyncPostgresStore._cursor` skips that lock when handed a pool** (its comment: "each
  `_cursor()` call checks out its own connection"), so the Store can take up to `max_size`.
- Both create their own tables on `.setup()` and are idempotent. `store_vectors` is only created
  when an `index` config is passed; none is, because pgvector search lives in our own
  `company_chunks` / `tender_chunks` under the schema `0001_init.sql` controls.
- `from_conn_string` opens with `prepare_threshold=0`; the pool does the same, so a query behaves
  identically whether the checkpointer or the read model issued it — and it is precisely why the
  transaction pooler is refused (ADR-0008's guard, now also run inside `Database.connect` for
  scripts that never pass through settings).

So one pool serves all three consumers (checkpointer, Store, read model), and the budget is one
number. The alternative — a pool per consumer — would have hidden the total.

### `.setup()` runs under an advisory lock, on a different key from the migration runner

Two API processes starting together would both run LangGraph's version bookkeeping. The setup is
wrapped in `pg_advisory_lock` on the borrowed connection (session-scoped, so lock and unlock must
use the *same* connection — the code does). The key is deliberately **not** `scripts/migrate.py`'s:
they guard different resources, and sharing one would make an API start wait on an unrelated
migration. A shared constant was also unavailable without breaking the script's rule of not
importing the package.

### The API starts without a database, but not with a broken one

`DATABASE_URL` unset means: start, warn once, serve `/health` and `/openapi.json`, and answer
**503 naming the variable** from any route that needs the pool. CI's generated-files job depends
on this — it boots the API with no Postgres to regenerate `frontend/lib/api.ts`. `DATABASE_URL`
set but unreachable means: **refuse to start**. Running on without checkpoints would lose every
paused bid, which is the exact failure the story exists to prevent.

### Verified, not inferred

The restart criterion was run against the Frankfurt project, not a fake: a one-node graph was
invoked under a `bid:{id}` thread and a Store item written; the `Database` was closed; a fresh
one was opened; `aget_state` returned the saved values and `aget` the item. The test is marked
`live` and resolves its DSN through `load_settings()` — the same path the API uses — so
`make test-live` needs no shell wiring.

Library behaviour learned on the way, all added to `CLAUDE.md`: psycopg_pool 3.3 deprecates
opening an async pool in the constructor (`open=False`, then `await pool.open()`); pgvector's
psycopg adapter returns a `Vector` object that is **not iterable** (`.to_list()`); and the
`anyio` pytest plugin is already in the tree, so async tests use `@pytest.mark.anyio` with a
shared `anyio_backend = "asyncio"` fixture rather than a new `pytest-asyncio` dependency.

### Consequences

- `crossbid.db.Database` is the one door to Postgres; `main.get_database` is the FastAPI
  dependency routers take. `Database.connection()` is the signature `ingestion.embeddings`'
  `ConnectionSource` Protocol names, so the two were written to meet in the middle.
- The `vector` type is registered per pooled connection in the pool's `configure` hook, so no
  consumer has to remember to do it.
- The migration runner does **not** apply LangGraph's tables and the app does **not** apply ours:
  `make migrate` then `make dev` is the order, and the README must say so.

## ADR-0011 — Embeddings, Storage, the extraction node, and the shell: four stories in parallel

**Date:** 2026-09-11 · **Stories:** S2.2.1, S2.2.2, S3.2.1, S4.1.2 · **Status:** accepted

Four stories with disjoint file ownership were built concurrently by four agents while S0.2.2
was built in the main session; this entry records what each settled and what the review found.
The parallel split worked because each brief named every file the agent owned and forbade the
rest — the one collision was a six-line `tests/integration/__init__.py` both sides created.

### S3.2.1 — the wrapper is now enforced, not just available

ADR-0009 closed with a residual: nothing enforced that document text reached a prompt only via
`wrap_as_data`. The extraction node's test fake **records the exact prompt the model was handed**,
and four tests act on those bytes — deleting everything between the tagged markers and asserting
no page's text survives outside them; that a forged `-----DOCUMENT` header planted in a page is
quoted with a tag that is not the wrapper's; that the operative ask follows the postamble; and
that the re-ask names pages, never the model's own text. That residual is closed.

Other choices, each argued in the module docstring: sections run under `asyncio.gather` plus a
`Semaphore` and **not** LangGraph's `Send`, because extraction is a fixed number of structured
calls with no decision about what to do next — `Send` fan-out is reserved for the genuinely
agentic `check_reqs`. `gather` orders by argument, which is what keeps dedupe independent of
completion order. A row is re-asked **exactly once** (cost bounded at 2× a section, never 3×);
the wire schema keeps `ecertis_criterion_id`, `page` and quote length loose so one bad row cannot
reject twenty good ones, and `Requirement` is what says no. Only `bid_eligibility` rows leave the
node (ADR-0003's 579 → 238). `translation` is filled in the same call rather than a second pass
over 238 rows.

The review round found one material defect before commit: **the fan-out had no failure isolation
for anything but the model call** — a prompt that would not render, or a defect in the row reader,
propagated out of `gather` and discarded every other section's finished rows, contradicting the
story. A catch-all now reports a `SECTION_FAILED` problem per section and the test that claimed to
cover this was rewritten to actually raise.

Two library facts that would otherwise have cost recall, both in `CLAUDE.md`: LangGraph matches a
node's `config` annotation **as a string**, so `RunnableConfig | None` under
`from __future__ import annotations` is silently never injected; and `pymupdf4llm` renders
emphasis as markdown, which SP.1's `page.get_text()` did not, so a strict verbatim check would
reject honest quotes containing a bold word.

The extraction fan-out now has its own settings key, `agent.extract_concurrency`: the agent had
borrowed `check_concurrency`, and the two fan-outs have different call shapes.

**Not closed:** the ≥ 0.9 recall criterion is measured by S3.2.3 against S6.4's labels, neither
of which exists. The SP.1 figure stands in, as the story says.

### S2.2.1 — a missing tenant scope is a type error, not a code-review catch

Four layers make an unscoped search structurally impossible: no generic `search(table, where)`
exists; each statement is a module constant with `company_id = %(company_id)s` written into its
text (tender searches add `bid_id`); those constants are `Final[LiteralString]`, which psycopg's
`execute` requires and pyright enforces, so a query assembled at run time **cannot be passed at
all**; and every scope argument is keyword-only with no default, asserted by `inspect.signature`.
This is the second line of defence ADR-0009 said did not exist, moved into the type system.

Verified rather than assumed: the migration's `vector_cosine_ops` commits every search to `<=>`,
and a test reads the SQL file to keep the two together; pgvector's adapter dumps `Vector` and
`ndarray` only, so a plain list would be sent as an array and rejected; the client authenticates
per request rather than baking the header into the injected `AsyncClient` — a real bug the tests
caught. Order is restored from the provider's `index` field, tested with a transport that answers
last-index-first. Every returned vector is checked against `embed_dimensions` with ADR-0004's
reasoning in the error.

The cross-lingual criterion was run live: a French query for information-security certification
ranked the German ISO 27001 passage first among four German passages sharing no token with it —
ranking computed in Python with the same cosine formula, so a failure would indict the model,
not pgvector. The demo pack (S6.3) does not exist, so the passages are hand-typed; the test
says so and names the switch-over.

### S2.2.2 — the key layout is the tenancy

Storage's own policies are not used for isolation; the object key `{company_id}/{document_id}/
{filename}` is, defined once. Ids are validated (identifier-shaped or it is a bug); the filename
is rewritten by allowlist — basename only, `[A-Za-z0-9._-]`, 120 chars, `"document"` if nothing
survives. `signed_url` refuses any key it could not itself have built for that company and answers
**not found, never forbidden**: a permission error confirms the document exists, which is the leak.
A test asserts every key we build is a key we will sign, so the strictness cannot lock a bidder out.

Two honest limits recorded by the agent and kept here: the ten-minute cap is enforced on what we
*ask* Supabase for, not proven on what it honours (a `live` test can do that later); and bucket
privacy is an operational precondition — a bucket created public in the dashboard fails no test.
Also confirmed: the client never parses the key, so `sb_secret_…` and legacy JWT keys both work.

### S4.1.2 — stock shadcn only, so the design gate holds

Header, navigation, footer with the advisory notice, skip link, mobile sheet, and empty states that
name the next step. Every visual is a stock primitive (`Button`, `Card`, `Sheet`); one
`NAV_ITEMS` list feeds both navigations so they cannot drift; nothing exists under
`components/matrix`, `components/pdf` or `components/verdict`, and the dashboard renders only the
first-run empty state — the bid list is S4.4.1, which is gated. No dependency changed. Verified in
a production build with Playwright: one `h1` per page, exactly one `aria-current`, no horizontal
overflow at 320 px, zero console output.

### A startup regression caught before it shipped

Because the API now connects at startup (ADR-0010), `infra/.env.example`'s `DATABASE_URL=…@localhost
:5432` default — correct for host runs — would have made `cp .env.example .env && make dev` fail:
inside the `api` container, `localhost` is the container. The default is now blank (Compose supplies
its own `db` DSN), the three ways to run are spelled out in the file, and the README quick start
gains the `make migrate` step, which the API does not do for itself.

### Consequences

- 710 tests, 100% line and branch coverage, all offline; 6 `live` tests, of which the restart,
  embeddings and vector-registration ones were run against the real services.
- Increment 1 has three stories left: S2.2.3 (upload-to-ready flow, now unblocked), S3.1.1 (the
  graph and `/bids`, now unblocked), and S4.0.1 — the design canvas the user must confirm before
  S4.5.1 and every matrix component. S4.2.2 waits on S2.2.3.

## ADR-0012 — Upload-to-ready, the bid run, the dev-auth bridge, and the first design draft

**Date:** 2026-09-11 · **Stories:** S2.2.3, S3.1.1, S0.3.1 (dev-mode bridge only), S4.0.1 (draft) · **Status:** accepted; S4.0.1 awaits the user's confirmation

### Who is calling, before sign-in exists

`crossbid/auth.py` is S0.3.1's Notes made concrete: with `AUTH_MODE=dev` the `X-Dev-Company` header
(a UUID) names the tenant and is believed — absent or malformed is 401 — and `AUTH_MODE=supabase`
answers **501** until token verification lands, so a deployment configured for real auth cannot
*look* authenticated. `settings.py` already refuses `dev` together with `ENV=production`. Every
router takes `CompanyContext` and every read-model statement is scoped by it; `main.get_app_settings`
serves the `Settings` the app was created with, so injected settings reach every dependency and the
`app_settings` row override (S4.6.2) has one place to land.

### Tender documents are not embedded at upload

S2.2.3's first draft embedded every upload. The concurrent S3.1.1 work made that wrong: documents
are uploaded *before* a bid exists (S4.3.1 disables Start until one is ready), and
`tender_chunks.bid_id` is `NOT NULL`, so there is nowhere to put a tender's vectors at upload time.
The pipeline therefore runs `uploaded → parsed → embedded → ready` for **company evidence** (into
`company_chunks`) and `uploaded → parsed → ready` for **tender kinds** — stored, page-counted, a
scanned PDF refused with a readable reason — leaving tender vectors to the graph under the bid.
`EMBEDDED_KINDS` is the one-line switch if that changes. Migration `0002` adds `documents.status`,
`failure_reason` and `updated_at`, with "failed iff there is a reason" enforced in SQL as well as
Pydantic; the parity guard in `tests/unit/test_migrations.py` now scans **every** migration file,
because its first draft scanned only `0001` and would have let `0002`'s status list drift.

Blocking work runs under `asyncio.to_thread`: pymupdf on a 191-page pack would otherwise stall
every `GET /documents/{id}` poll on the event loop.

### The review interrupt is an explicit node, measured against the alternative

Two ways to park a graph at `awaiting_review` were tried on langgraph 1.2.11 before choosing.
`interrupt_after=["extract_reqs"]` on the graph's **last** node leaves `aget_state().next == ()`
and no `interrupts` — indistinguishable from a finished run, and `ainvoke(None)` on it is a no-op.
An explicit `await_review` node calling `interrupt(payload)` parks with `next == ("await_review",)`
and a payload `{bid_id, requirements, problems}`; S3.4.2 resumes with `Command(resume=review)` and
receives the review as the node's return value. Known and tested: on resume the node re-runs, so
`awaiting_review` is written twice with the same value. Also measured: `ainvoke(None)` on a thread
with no checkpoint raises `EmptyInputError`, so the resume path checks `snapshot.created_at` and
starts from the row when nothing was checkpointed yet.

The graph is `START → parse_docs → extract_reqs → await_review → END`; each node runs inside a
`stage()` wrapper that writes `bids.status` to the read model on entry and problems/requirements on
exit — the dashboard reads rows, never checkpoints. Node failures become `StageError("<stage>
failed: <ExceptionType>")`, type only (ADR-0008). Migration `0003` adds `bids.failure_reason` and
`bids.problems`. The story's `finalizing`/`done` wording differs from `BidStatus`'s
`applying_review`/`complete`, which is what the `0001` constraint enforces; the model was kept and
the plan text is the thing to amend.

`BidRunner` owns the background tasks (tracked; shutdown awaits or cancels them **before** the pool
closes; a crash logs the traceback and marks the bid `failed`). `resume_unfinished_runs` at startup
re-invokes every non-terminal bid — the restart criterion — and refuses to start when there is
something to resume and Storage is unconfigured, rather than failing the bids. The two limits live
in settings as `agent.run_budget_seconds = 600` and `agent.run_budget_usd = 2.50`; the `live`
DE-pack test asserts them and fails if OpenRouter reports no cost rather than passing at $0. **It
has not been run** — it costs real money; the user decides when.

### Two migrations, one number

Both agents added a `0002`. `scripts/migrate.py` refuses duplicate versions, which is exactly the
failure it exists to catch; S3.1.1's became `0003`. Both were applied to Frankfurt in one run.

### The design canvas is a draft, and the gate is still closed

S4.0.1's canvas was drafted from the shipped shell's tokens (Geist, the shadcn neutral scale, 10 px
radius, 56 px header, 32 px controls) with the real FR fixture as content: dashboard, new-bid step
2 of 3, workspace at desktop and phone width, verdict confirm/override. Static mockups. Three
proposals the app had no answer for are called out on the canvas for the user's reaction: a status
colour set (met green, not met = the theme's destructive red, unclear amber, running blue, one
lightness and chroma), a 520 px PDF pane left of the matrix with one row expanded at a time, and the
PDF behind a *Document* tab on the phone. A second-pass review found real defects before handover —
verdict counts that contradicted the workspace header, a citation to a page the same screen called
unreadable, phone controls under 44 px, the wrong active nav — all fixed in version 2. The working
files are `docs/design/canvas/` (regenerated by `build.py`); the artifact is
https://claude.ai/code/artifact/2c3a373f-69f0-4d80-896a-53715377862f. **Nothing under
`components/matrix`, `components/pdf` or `components/verdict` exists**; that stays true until the
user confirms.

### The upload table, and the CORS gap it exposed

S4.2.2 (stock shadcn, exempt from the gate) added `frontend/lib/use-polling.ts` — a reusable hook
S4.5.1 will drive `GET /bids/{id}` with — and the documents table under `/company`, verified in a
production build at 320 px with 44 px targets and a stub API. Its agent noticed what nobody had
tested: the API had **no CORS middleware**, so a browser at `:3000` could not call `:8000` at all.
`main.py` now allows exactly one origin (`WEB_ORIGIN`, already in Compose and `.env.example`) plus
the `X-Dev-Company` header, and refuses any other origin — asserted by a preflight test. Until
sign-in lands the web app names the tenant through `NEXT_PUBLIC_DEV_COMPANY_ID`, a build-time
variable declared in the Dockerfile and forwarded by Compose.

### Consequences

- 960 tests, 100% line and branch coverage, all offline; 7 `live` tests. **The bid-run test was run
  once on 2026-09-11 and passed**: the 28-file, 191-page DE pack reached `awaiting_review` in
  **290 s** at an OpenRouter-reported **$1.38** (limits 600 s / $2.50) — 258 requirements before the
  reviewer, 13 problems, 49 model calls (47 sections plus two re-asks). Consistent with ADR-0003's
  238 after dedupe and its 4.4× fan-out estimate (~18 min sequential → under 5). Two limits of
  that number, for the next run: the test prints the 13 problems only as a count (the per-kind
  breakdown and any retry warnings are captured by pytest and shown only on failure), and the
  cost is the sum of whatever `usage.cost` values OpenRouter returned — a call that reported none
  is silently left out, and only an all-empty run fails. Both are one-line test improvements. `frontend/lib/api.ts` regenerated for `/documents` and `/bids`.
- Increment 1's backend is complete and the upload table is in. Remaining: the user's decision
  on the canvas (S4.0.1), then S4.5.1 (workspace polling + requirement list), and a `companies`
  row for the demo tenant, which nothing creates yet.
- Open: `MAX_UPLOAD_BYTES` (50 MB) is a router constant that should become
  `ingestion.max_upload_bytes`; the plan's status wording should be aligned to `BidStatus`.


## ADR-0013 — The design system's vocabulary becomes the contract's

**Date:** 2026-09-11 · **Stories:** S4.0.1, S0.4.1 · **Status:** accepted (user decision)

### Context

The user rejected the first canvas and supplied a design system (Claude Design project
`b81312f6`, synced under `.claude/skills/CrossBid Design System/`). Its content rules fix the
product's words: verdicts are **Go / Conditional / No-go / Insufficient evidence** ("never
Pass/Fail, never Approved"), and evidence is **Supported / Partially supported / Unsupported**.
The backend's contracts said `go / go_with_open_items / no_go` and `met / unmet / unclear /
not_applicable`. Two vocabularies for one thing would have leaked into the generated
TypeScript, the read model and every screen. The user chose to adopt the design system's.

### Decision

- `Decision` is `go`, `conditional`, `no_go`, `insufficient_evidence`. The fourth is new: the
  agent **declining** to judge -- nothing blocks the bid, but the documents do not settle
  enough rows for a recommendation. Its validator rule: at least one partially supported row,
  else "nothing is insufficient". `conditional` takes `go_with_open_items`'s place and rule.
- `RowStatus` is `supported`, `partially_supported`, `unsupported`, `not_applicable`. The
  central invariant survives the rename: a `supported` row must cite evidence or an attached
  document, in Pydantic **and** in SQL.
- `Verdict.mandatory_met` → `mandatory_supported`, `unclear_rows` → `partially_supported_rows`,
  so the old words do not linger in the API contract.
- Migration `0004` re-adds the three check constraints with the new lists (0001 is immutable,
  ADR-0009), renames the evidence constraint to say what it guards, and maps any existing rows
  first. The parity guard now reads the **last** definition of a constraint across all
  migration files -- its first draft read the first and would have failed on exactly this
  change.

### Consequences

- 963 tests, 100% coverage; `0004` applied to Frankfurt; `frontend/lib/api.ts` regenerated.
- The plan's F3.3/F3.4 story text is amended in place with a dated pointer here; F3.3's
  `met_via_equivalent` becomes `supported_via_equivalent` when that story adds it.
- The S4.0.1 canvas uses these words, and its open question about them is closed.


## ADR-0014 — The screen designs are confirmed; the UI gate is open

**Date:** 2026-09-11 · **Stories:** S4.0.1 · **Status:** accepted (user confirmation)

### What was confirmed

The user confirmed version 6 of the design canvas:
https://claude.ai/code/artifact/2c3a373f-69f0-4d80-896a-53715377862f — working files in
`docs/design/canvas/` (regenerated by `build.py`). Six artboards, each the reference a UI story
cites when it implements the screen:

| Artboard | Screen | Implementing stories |
|---|---|---|
| `Dashboard.dc.html` | Dashboard: greeting, ask bar, quick actions, key metrics, tenders table | S4.4.1 (bid list), S3.5.1/S4.6.1 (ask bar) |
| `NewBid.dc.html` | Analyse tender — step 2 of 3: chosen notice, upload the pack, start | S4.3.1 (TED search + flow); the start step lands early with S4.5.1 |
| `Main.dc.html` | Compliance matrix with the source page open in a right-hand panel | S4.5.1 (list, polling, source panel), S4.5.2 (row editing) |
| `Verdict.dc.html` | Review verdict: recommendation, what would change it, your decision with override reason | S4.5.3 |
| `WorkspacePhone.dc.html` | Matrix at 390 px: segmented Matrix / Source / Verdict, pinned action | S4.5.1 |
| `Landing.dc.html` | Marketing landing page from the design system's website kit | the public `/` page |

### Accepted changes on the way to confirmation

1. **The first draft was rejected outright** ("I hate the design canvas"). It had been built on the
   shipped shell's shadcn tokens. The user supplied a design system (Claude Design project
   `b81312f6`, synced to `.claude/skills/CrossBid Design System/`); draft 2 reproduces its shell
   (260 px canvas sidebar, one white content frame), tokens, Geist, component anatomy and logo.
2. **Its vocabulary became the contract's** — ADR-0013.
3. **The source page is a panel, not a permanent split.** S4.5.1 asks for the PDF beside the
   matrix; the design system's kit had no such screen, so the confirmed shape is a 400 px "Source"
   card to the right of the matrix, opened from a citation. On the phone the source is a tab.
4. **Second-pass fixes before each publish** (counts agreeing across screens, an unreadable page
   cited, sub-44 px controls, an over-long button, one orange tile per region) — recorded in the
   canvas commits.

### Consequences

- `components/matrix`, `components/pdf` and `components/verdict` may now be written; each
  component's docblock names the artboard it implements.
- The shipped shell (S4.1.2, stock shadcn top bar) does not match the confirmed design and is
  replaced by the sidebar shell as part of S4.5.1; the design system's tokens replace the shadcn
  neutral scale in `globals.css`.
- The PDF viewer uses the browser's own renderer (`<iframe>` on a short-lived signed URL with a
  `#page=N` fragment) — no PDF library is in the plan's tech stack, and asking for one is deferred
  until the native viewer proves insufficient.
- **S4.5.1 landed the same day on these artboards**: `app/globals.css` carries the design system's
  token sheet verbatim; `components/ui/*` reproduce the `.jsx` anatomy (button, badge, tag, card,
  tabs, metric-card, verdict-chip, input/select/checkbox, notice, data-table, sheet, icons) and the
  shadcn files they replaced were removed; the sidebar shell replaced the top bar. `GET
  /documents/{id}/url` signs a file for the viewer; a citation click remounts the iframe on
  `#page=N`. Left honest rather than faked: buyer/deadline tags, evidence statuses and the
  eCertis card (Increment 2), the verdict panel (Increment 3). The shadcn leftovers were removed the same evening with the
  user's approval — `class-variance-authority`, `lucide-react`, `shadcn`, `tw-animate-css`,
  `components.json` and the scaffold's `public/*.svg` — and `dependencies.txt` regenerated; the
  plan's tech-stack line now names the design system, with Radix kept for behaviour. The
  landing artboard is implemented under `components/landing/` (public `/`), placeholders and
  anchor-only links kept honest until real destinations exist. Placeholder routes
  `/certificates`, `/verdicts`, `/runs` exist only because the confirmed sidebar links to them.

---

## ADR-0015 — Increment 2's foundations: tools, company memory, the German overlay, and the fixtures that score them

**Date:** 2026-09-11 · **Stories:** S1.1.2, S2.4.1, S2.4.2, S6.3, S6.4 · **Status:** accepted

### Context

Increment 2 delivers the matrix in the browser. Its critical path is S1.4.1 (tool registry) →
S3.3.1 (`check_reqs`) → S4.5.1's matrix-row criterion, and all three sit behind the tools and
the company facts that the agent reaches for. Those, plus the two content wait-fillers, have no
dependency on each other, so five stories were built in parallel by separate agents against one
contract written first: `crossbid/tools/manifest.py`.

### Decisions

**1. A tool declares itself, and is handed its scope.** `ToolManifest` (name, description,
`external`, `default_enabled`) is what the registry will read and `GET /dev/settings` will
list; `external` is the field an operator actually needs, because it says the tool opens a
socket. `ToolContext` carries `company_id`, `bid_id` and the connection source, so a tool that
reaches Postgres **cannot be built without a tenant** — `tender_rag_search.build_tool` raises
at build time when `bid_id` is `None` rather than quietly searching every bid.

**2. Retrieval joins `documents` rather than issuing a second query.** `Evidence` needs a
document *name* for a citation a reviewer can click, and `ChunkMatch` had only an id. Both
search statements now join, which forced every column to be table-qualified — `documents` has
its own `id`, `name`, `pages` **and `company_id`**. `TENANT_PREDICATE` therefore lost its
leading `where` and the per-statement test got stricter, pinning
`where <chunk table>.company_id = %(company_id)s`. The join repeats the tenant in its `on`
clause: redundant while the foreign keys hold, free, and it stops a mislinked row from putting
another tenant's file name into a citation. Cosine `distance` keeps its name and direction;
only the tool's `score` is the similarity, converted in exactly one place.

**3. The bidder's language is a UUID-keyed overlay, not a second cache.** S1.1.2 needs German.
eCertis's undocumented `?lang=de` was probed live and **returns byte-identical UUIDs** across
languages — EU criteria, national sub-criteria and evidences alike — and the three id spaces
are mutually disjoint (56 + 172 + 89 = 317, zero collisions). So one flat map keyed on the UUID
serves all three levels. `l10n_de.json` is committed beside the English cache and
`CACHE_SCHEMA_VERSION` is deliberately **not** bumped: `criteria.json`, `evidence_de.json` and
`evidence_fr.json` stay byte-identical, which is what protects S1.1.1's "a second build changes
nothing" property and the enum S1.1.3 generates from them. Run time still opens no socket.

Neither language is authoritative: eCertis's *English* payloads contain untranslated German
prose, and its German payloads keep native German terms unmarked while stamping
`(Automatische Übersetzung)` on machine translations. The overlay is an addition, never a
replacement, and `lookup_evidence` never raises — a country with no entry answers `not_found`.

**4. The company profile splits by what the database depends on.** Scalars that carry a check
constraint or get joined (`country`, `legal_form`, `tone`, `language`, `name`) stay columns;
the variable-length lists (turnover, certificates) and the free-text registration fields go in
the existing `profile` jsonb. `COLUMN_FIELDS` and `JSONB_FIELDS` are asserted to partition
`CompanyProfile` exactly, so a field added later must be placed deliberately rather than
silently dropped on save. No migration was needed. Certificate expiry is **derived on the
response**, never stored, so `CompanyProfile` stays frozen.

`PUT`, not `PATCH`: S4.2.1 is one form that loads the whole profile and saves it whole, and a
merge has no answer for two id-less lists. **When the row saves but the LangGraph Store write
fails the route answers 200 with a `warning` field** (user decision, 2026-09-11): the save
genuinely happened, a 5xx would tell the bidder their facts were lost, and `PUT` is idempotent
so saving again repairs the memory. The failure is still logged with the company id.

**5. The demo pack and the golden labels are generated, committed and checked.** S6.3's ten
German PDFs are built by a committed script from two reviewable YAML inputs, byte-identical on
re-run (`no_new_id=True` plus emptied metadata — PyMuPDF's fresh trailer `/ID` was the only
non-determinism). Every page carries `MUSTERDOKUMENT — Demodaten, kein amtliches Dokument`,
every issuer and number is invented, and three tests assert the marker page by page through the
repo's own parser. The `Freistellungsbescheinigung` is deliberately expired so S2.4.1's flag
has something to catch.

S6.4's labels are **LLM drafts** (`labelled_by: llm_draft`, `verified_by: pending`) and the
story stays open until a human verifies them. What makes them safe to commit unverified is
`test_golden_labels.py`: for all 257 labelled requirements it re-opens the cited PDF and
asserts the quote appears verbatim on the cited page, under `extract_reqs._is_verbatim` —
imported, not reimplemented. A fabricated quote or a wrong page cannot pass CI.

### Consequences

- **SP.1's prototype is superseded and was partly wrong.** Run through the repo's own parser,
  3 of its 21 quotes fail verbatim matching (one contains a `[...]` elision, two join a heading
  to a table cell across a `<br>`). It claimed 3 requirement-bearing documents in the DE pack;
  there are **18**.
- **Any scorer must filter the DE golden file on `stage: bid_eligibility` first.** 13 of its 143
  scored rows are `contract_performance`, kept in `requirements` on purpose so S3.2.3 can score
  ADR-0003's stage filter in both directions. Unfiltered, recall reads 13 rows low.
- **The FR fixture independently confirms ADR-0007.** All 30 `ccv:Criterion` UUIDs in the
  buyer's published DUME are members of the generated EU-level `EcertisCriterionId` Literal, so
  8 FR labels carry a criterion id read off the document with no inference at all. The EN
  fixture carries **zero** ids on purpose — EASA does not use the ESPD (TS p.18 fn 12).
- **EN exclusion-ground recall is not yet scorable.** All 14 grounds live in `.docx` annexes and
  the parser is PDF-only, so only the umbrella Art. 138(1) row is labelled.
- 2 251 tests, 100 % coverage, all offline. S1.4.1 and S3.3.1 can now be built against real
  manifests.

### Two conventions the review forced, worth naming

**A check-constrained column is mirrored in the Pydantic field that writes it.**
`CompanyProfile.country` was `min_length=2, max_length=2` while `companies.country` carries
`check (country ~ '^[a-z]{2}$')`, so `{"country": "DE"}` passed the schema and died as a
`CheckViolation` — a 500 with a traceback, from a route whose docstring promises a 422 naming
the field. S2.4.1 is what first exposed that column to client input; before it, the only writer
hard-coded `"de"`. The regex is now on the field, and `test_migrations.py` pulls every
`check (col ~ '…')` out of the migrations and fails if one has no Pydantic mirror, beside the
enum parity checks that already do this for the `in (...)` columns. `"DE"` is **rejected, not
lower-cased**: a `PUT` that rewrote its own body would answer with something the caller never
sent, and the pattern reaches the generated client, so the form can say so first.

**`zz` is the unknown country.** `lookup_evidence` promises totality — S3.3.1 calls it without
a try/except — but `EvidenceAnswer.country` was an unconstrained `str`, so `"deu"` produced an
answer that then raised `ValidationError` inside the ReAct loop when converted to an
`EcertisEvidence`. Anything that is not two ASCII letters now normalises to `zz` (ISO 3166-1
user-assigned, CLDR "Unknown Region") and answers `not_found`. It doubles as the guard on the
only caller-controlled string that becomes a cache filename.

**`tests/conftest.py` is the only shared ground between test modules.** Two incompatible
`FakeConnectionSource` families had grown — one in `conftest.py` modelling
`connection.cursor()`, one in `test_documents_readmodel.py` modelling `connection.execute()` —
and the stories written in parallel imported whichever they found, so the fake that every
ADR-0009 tenant-scope assertion runs through was two artefacts. There is now one, and
`test_conftest_is_the_only_shared_ground.py` walks every test file's AST and fails on any
import of a `test_*` module.

### Also in this commit — the landing page opens with the logo reveal

Not a story. The user supplied `CrossBid Logo Reveal.mp4` and asked for it on the landing page,
then for it seamless and in the hero. It is the **one UI component that cites no artboard**,
which ADR-0014's rule otherwise requires; recorded here as the deviation.

What the file actually contains decided every parameter, measured frame by frame through a
canvas rather than assumed:

- The clip **does not end on the logo** — it dissolves the mark and then the frame. Playback
  is a window, `1.2 s → 7.56 s`. The start skips dead time (one dot, 166 mark pixels, from
  0.5 s to 1.25 s). The hold is the last frame on which the mark is still solid, and the
  honest signal there is not the pixel *count* — which drifts up to the very end — but their
  mean darkness: 23 flat from 7.40 s through **7.56 s**, then 25 at 7.58, 30 at 7.62, 56 at
  7.68, 114 at 7.74, and gone by 7.84. The dissolve begins at 7.58.
- **Final shape (2026-09-12): the forward reveal only, split-rate, no control.** Playing the
  reverse was tried and rejected — it deconstructs the mark to nothing (0 mark pixels from
  14.6 s), so the page rested on an empty band. The hold went back to **10.70 s**, the last
  frame on which the mark is whole. That leaves a 9.44 s window, which at natural speed is
  over WCAG 2.2.2's five seconds and obliges a visible pause control; the user rejected the
  control *and* the ~1.9× flat rate that would remove it. The way out is that **only half the
  window is animation**: the mark draws in between 1.26 s and ~4.2 s and is then flat at
  ~31 200 pixels and mean darkness 23 all the way to the hold, with the remaining 6.5 s being
  two passes of rings settling behind a mark that does not change. So the draw-in plays at
  1.0× and the settle at 3.5×, measured at **4 812 ms of motion end to end** — under the line,
  with the one part anybody watches at true speed. `BUILD_END_SECONDS` later, `SETTLE_RATE`
  lower or `REVEAL_HOLD_SECONDS` later each push it back over five seconds and silently re-owe
  a control.
- *(Superseded)* **The whole clip played, reverse included, at natural speed.** Two things follow and neither is optional. The reverse **ends on nothing**
  — mark pixels run 31 200 at 11.5 s, 8 117 at 13.0, 166 at 14.0 and **0 from 14.6 on** — so
  resting there would leave the hero with an empty band for as long as a visitor stays. On
  `ended` the component cross-fades to the static lockup instead, the same asset a
  reduced-motion visitor gets, so a logo stays on the page. And 14.8 s at 1.0× is far past
  WCAG 2.2.2's five seconds with no rate short of a visible fast-forward bringing it back, so
  **a pause control is now a requirement of the length, not a style choice**. It is revealed
  on hover and on keyboard focus — the most it can be hidden and still be a mechanism.
  `visibility: hidden` was the first attempt and was wrong: it takes the button out of the tab
  order, so `:focus-visible` can never fire and a keyboard user has no mechanism at all
  (measured — `btn.focus()` left `document.activeElement` elsewhere). `opacity-0` keeps it
  focusable; `pointer-events-none` stops an invisible target swallowing clicks. Verified by
  tabbing to it for real: reached in 9 presses, `:focus-visible` matches, opacity resolves to
  1, Space pauses the clip and the label flips to "Play animation".
- *(Superseded by the above, kept for the reasoning)* **The clip was re-cut to 14.8 s, and the
  hold moved to its end.** The new
  file is a full cycle: a dot, the mark drawing in by 4.0 s, a long hold while *two* passes of
  rings come and go, then the whole thing disassembling back to a dot and looping. An
  intermediate pass had held at 6.82 s — the floor of the **first** ring pass — because it fit
  five seconds at a gentler rate. That was wrong twice: a second ring pass climbs away
  immediately after it (peaking near 7.75 s), so the page rested mid-animation with rings still
  to come, and the user's instruction is explicit that it stops at the end. The hold is now
  **10.70 s**, the last frame of the mark's solid plateau — mean darkness 20.2 at 10.64 and
  20.5 at 10.68–10.70, then 21.2, 21.8, 23.2, 24.9, 27.2 and 34.3 by 10.92, while the pixel
  count stays flat either side (≈123 580 at both 10.70 and 10.82), which is why darkness and
  not count is the signal. **`PLAYBACK_RATE` rose to 2.0×**: the window is 9.44 s of source,
  and 1.3× → 7.26 s, 1.6× → 5.90 s and 1.9× → 4.97 s are all at or over WCAG 2.2.2's line,
  where only 2.0× → 4.72 s leaves margin. The mark still draws in over ~1.4 s; the remaining
  ~3.3 s is rings settling behind a mark that no longer changes, where speed costs nothing.
  If it ever reads as rushed the fix is a slower rate **plus** a pause control — the two travel
  together, and neither is compliant alone.
- An earlier re-cut (2026-09-11) had the rings clearing before the mark faded, and the hold
  sat after that: counting faint pixels *outside* the mark's bounding box, which separates
  rings from glyph anti-aliasing, gives 4 040 at 5.00 s, 1 807 at 6.75 and **129 at 7.00**,
  flat thereafter. The held frame is the mark alone, not a mark inside a halo.
- **`PLAYBACK_RATE = 1.3` is a WCAG constraint, not a style choice.** That window is 6.36 s of
  source, over 2.2.2's five-second threshold, which would oblige a visible pause control on
  the hero. At 1.3x it is 4.89 s of wall clock, so the whole reveal plays and nothing is owed.
  Slowing the rate, starting earlier or holding later re-crosses five seconds and silently
  reintroduces the requirement.
- **3.4 s of motion is under WCAG 2.2.2's five-second line**, so no pause control is required
  and the hero stays clean. Widening the window past five seconds reintroduces the requirement.
- The hold is watched with `requestAnimationFrame`, not `timeupdate`: at ~4 ticks a second the
  event overshot to 7.93 s, a quarter-second into the fade.
- **Seamlessness is arithmetic, not taste.** The clip's ground is opaque `#FAFAFA`, which punched
  a rectangle through the hero's grid. `mix-blend-mode: multiply` takes white to transparent,
  but multiply is a product: 250 over 250 lands on 245, a measured 4-value step at the band's
  edge. `brightness(255/250)` lifts the ground to true white first, where multiply is the
  identity. After: inside and outside the band both read `(250,250,249)`.
- The frame is cropped on both axes to the mark (x 15–85 %, y 34–66 %), which renders it at
  ~748 px against the headline's 678 px — a little larger, as asked — without the band
  swallowing the fold. The crop is a **mask, not a clip** (2026-09-12): the clip's concentric
  rings run the full height of the source frame (0.000–0.998 from 1.5 s to 6.5 s — the source
  already cuts them at its own edges), so a hard crop sliced them with a straight line
  mid-animation. Opening the band to fit them would have made it 537 px tall instead of 216
  and dropped the mark to ~595 px, under the headline. Instead the video overflows its box
  behind a radial mask: the rings dissolve into the canvas, the layout box stays the size of
  the mark, and the CTA does not move. Verified no horizontal overflow at 390 / 768 / 1440 /
  1920 px — the hero section's own `overflow-hidden` contains the sideways spill. The `IntersectionObserver` therefore watches the **band**, not the video:
  the video is 312 % of the band tall and all but 22.4 % of it is clipped, below the threshold.
- `prefers-reduced-motion: reduce` gets the static lockup and **zero network requests** for the
  clip: the preference is resolved before the element is ever rendered, since a default of
  `false` was measured putting one request on the wire before the effect could remove it.
- The cross-fade and the hold loop hang off the video's `playing` **event**, not off the
  `play()` call. Flipped at call time, a refused autoplay (iOS Low Power Mode,
  `media.autoplay.default=5`) faded the lockup out and left an empty band on the start frame,
  and `watchForHold` recursed at 60 fps forever waiting for a hold point that could not
  arrive. Both paths are verified by stubbing `play()` to reject: the video stays at
  `opacity: 0` and the lockup at `opacity: 1`.
- The user replaced `CrossBid Logo Reveal.mp4` with a smaller encode mid-session (2.37 MB →
  1.72 MB). The served copy is that file byte for byte — identical `sha256`, one source of
  truth — and every constant above was re-measured against it: the ground is still
  `(250,250,250)` and the mark still runs x 18.80–81.15 %, y 36.67–63.15 %.

---

## ADR-0016 — The tool registry: what the agent may reach, and who may look

**Date:** 2026-09-12 · **Stories:** S1.4.1 · **Status:** accepted

### Decisions

**Tools are discovered, not listed.** `tools/registry.py` walks `crossbid.tools` for modules
exporting a `ToolManifest`. `build_enabled_tools(context, settings)` builds exactly the names in
`runtime.enabled_tools` — **sorted by tool name, not by the YAML's line order**. Reordering the
settings file must change *which* tools are bound, never the order the model is shown them;
otherwise one bid's prompt differs from the next's for no reason anybody recorded.

**A configured name with no module is skipped with one log line, not an error.** Two of the five
names in `settings.default.yaml` (`search_ted`, `currency_convert`) are Increment 4 stories. At
run time a typo and a not-yet-landed story are the *same observation* — a name nothing provides
— so nothing in the registry could tell them apart, and refusing would kill a run because the
YAML names next month's tool. The typo is caught instead at test time, by the manifest sweep
that asserts every configured name is either built or one of the declared pending stories.

**A tool that cannot be built propagates.** The build is eager. The tools the registry would
otherwise drop silently are exactly the ones `check_reqs` cannot work without: a run that
searched no tender would answer "no evidence found" for every requirement, which is a wrong
answer indistinguishable from a right one. All three build failures (`bid_id` absent, `db`
absent, malformed UUID) are caller bugs, not operator configuration.

**`GET /dev/settings` reports behaviour, never environment.** The exclusion is a rule rather
than per-field judgement: everything in `EnvSettings` is out, reusing the split `settings.py`
already draws — secrets and deployment wiring in the environment, behaviour in `RuntimeSettings`.
`ModelSlugs` and `AgentSettings` are reused verbatim, so a field added to either is behaviour by
construction and cannot become an accidental leak. **`system_prompt` is excluded too**: it is
S2.3.2's standing injection defence, and publishing its wording on an unauthenticated route
hands anyone who can get a PDF into the pipeline the exact text to write around.
`system_prompt_set: true` is reported instead, and a test asserts the payload carries neither a
secret nor the prompt.

**The gate is `ENV != production`, and the refusal is a 404.** S4.6.2's criterion is a
developer-role check, but no role mechanism exists — auth is still the `X-Dev-Company` dev
bridge, and "developer role via an env-var email list" is an open question in the plan. Rather
than invent one, the route refuses in production the way `seed_dev_company.py` and
`_refuse_dev_auth_in_production` do. The refusal is 404 with Starlette's own body, byte-identical
to an unknown path, because a 403 confirms the route exists. No tenant header is required: the
answer holds no tenant data, `X-Dev-Company` is self-asserted and so authorises nothing, and
demanding it would turn the 404 into a 401 that gives the route away. S4.6.2 tightens this to a
real role check with the environment gate staying underneath.

### Consequences

- The first criterion ("only enabled tools are bound when the graph builds") is tested on the
  **list**, not on a bound model: `model.bind_tools(...)` would test langchain, not us.
  `graph.py` is untouched — `check_reqs` does not exist yet, and a dead `tools=` seam would be
  speculative. `build_enabled_tools` is the single seam S3.3.1 plugs into.
- The registry does not pass the RAG tools' `embedder=`, so each built tool constructs its own
  `EmbeddingsClient`. `rag.py` wants one client per run; that needs either a widened
  `ToolContext` or a registry parameter, and S3.3.1 is the story that knows which.
- 2346 tests, 100% coverage.

---

## ADR-0017 — `check_reqs`: the agentic core, and what it is not allowed to invent

**Date:** 2026-09-12 · **Stories:** S3.3.1 · **Status:** accepted

### Context

This is the product. Everything before it prepares evidence; this is the node that decides what
a bidder can prove. It is also the brief's **Hard 1 (agentic RAG)**: the outer graph stays a
deterministic workflow with a human interrupt, and the agentic part is a small ReAct loop *per
requirement* inside this node. The plan's story text predates ADR-0013 and names five statuses;
only the four in `RowStatus` exist.

### Decisions

**Evidence is an index, never a sentence.** The model does not write quotes — it returns
`EvidenceRef(search, passage)`, two integers naming which tool call and which `[n]` within its
result. The loop keeps each call's `RagSearchResult.hits` in call order and resolves through
`RagHit.as_evidence()`, so the quote, document name and page in a matrix row are bytes the
store returned. This is the product's central promise made structural rather than trusted: a
test scripts a model whose rationale *contradicts* the passage it cites and asserts the row
carries the passage. An out-of-range reference resolves to nothing, and a `supported` verdict
left with no resolvable citation is **downgraded to `partially_supported`** with a note — the
honest outcome, and it keeps `MatrixRow`'s validator from having to raise.

**Two things happen without the model at all.**
- eCertis is looked up **in code** when the requirement carries a criterion id. The story's
  guarantee then does not depend on the model choosing to call a tool, and it costs no tool
  call from the budget. The register's answer is also stated in the prompt.
- A requirement whose `checkable` is not `COMPANY_PROPERTY` returns `partially_supported`
  with **no model call**. ADR-0003 measured this: SP.1 answered `unclear` for all eight
  submission duties. This branch is what makes checking fit the $2.50 run budget.

**The tool budget is a counter that cannot be cheated.** `searches` is both the count and the
record, and it grows for refused and failed calls too. Calls past the budget in a turn still get
a `ToolMessage` ("not run, budget spent") because a dangling tool call makes the provider reject
the next request; the loop then stops asking and the closing ask says the budget is gone.

**Concurrency is structural, not a semaphore.** A conditional edge emits
`min(check_concurrency, n)` `Send`s and each lane checks its share sequentially. Two
consequences: the bound survives a resume with nothing to re-establish, and the Postgres
checkpointer — which serialises on one lock (CLAUDE.md) — writes once per lane instead of once
per requirement.

**`status` needed a reducer.** Concurrent lanes all merge `status` in one superstep and a plain
channel raises `InvalidUpdateError`. The concurrent writers are always the same stage, so "last
write wins" is one answer arriving several times rather than a race. It is a **named function**,
not a lambda: `BinaryOperatorAggregate.__eq__` treats any lambda as equal to any other.

**Every failure is a row, never an exception.** A tool that raises, an unbound tool name, a tool
returning the wrong type, a spent budget, a failed verdict call, a `DataWrapError` — each
produces a row, and the message naming a tool failure carries the exception *type* only, because
a tool error can quote a URL or a database row. A database outage still fails the run.

**One `EmbeddingsClient` per lane.** `ToolContext` gained `embedder`, because it *is* the scope
object the registry hands every tool; a parameter on `build_enabled_tools` would put one pair of
tools' resource into the registry's signature for every future tool to ignore. Per lane rather
than per run (a run-scoped client has no close point after the fan-out) or per requirement (258
pools). A test monkeypatches `rag.EmbeddingsClient` to raise, so a tool building its own is a
failure and not merely a cost.

**The matrix row id is `uuid5` over the requirement id**, so a resumed run updates rather than
doubles. The table has a unique index on `requirement_id`: a random id would not conflict on
`id` and the insert would then be *refused*. The `do update set` list deliberately omits
`reviewer_status`, `override_reason`, `attached_doc_ids` and `reviewed_at` — a re-run must never
overwrite a human's decision.

### Consequences

- The graph is `parse_docs → extract_reqs → plan_checks -[Send × lanes]→ check_reqs →
  await_review`. With no requirements the edge returns the node name rather than an empty `Send`
  list, which would leave the superstep with no successor and finish the run unreviewed.
- `GET /bids/{id}` now returns `matrix_rows`, ordered to line up index-for-index with
  `requirements`, filled in **lane by lane** — so it is non-empty *while* `status` is `checking`
  and grows between polls. S4.5.1 must render partial.
- `not_applicable` and `unsupported` are model-chosen only; no code path produces them, so
  S3.3.2's deterministic tests for those must script the verdict.
- 2427 tests, 100% coverage. The live test (`test_check_reqs_live.py`, $0.25 tripwire) is
  written and **not run**.

---

## ADR-0018 — Increment 2 closes: every status pinned, the matrix on screen

**Date:** 2026-09-12 · **Stories:** S3.3.2, S4.5.1 (matrix-row criterion) · **Status:** accepted

### S3.3.2 — the tests found a real bug, which is the point of the story

**The downgrade path blew the rationale cap.** `_verdict_row` trimmed the model's rationale to
`MAX_RATIONALE_CHARS` (600) and *then* appended the 131-character "uncited support" notice, so
an uncited-`supported` row could reach the matrix with a **732-character** `agent_rationale` —
in the one column the module's own docstring promises is bounded. The per-branch "rationale
within its cap" assertion is what caught it. The fix trims the *model's* half so the notice
survives whole: the notice is the reason the row is not `supported`, and half of it tells the
reviewer nothing.

A frozen `Branch` table drives every sweep, one route per status plus each
`partially_supported` **code** path separately — the model's own answer (0 calls, 1 turn), the
requirement that never reached the model at all (`checkable != COMPANY_PROPERTY`, **0 calls, 0
turns**), and the downgrade (1 call, 2 turns). Per branch: the row field by field, exact tool
calls and model turns, the cap re-tested with a model that never stops searching, and
concurrency through the real checker. Evidence is compared against `Evidence(...)` **literals**
rather than values derived from the fake hit, so a model that retyped a quote is
distinguishable from one that cited it.

Two guards matter beyond this story. `{branch.status} == set(RowStatus)` is the line that fires
if the plan's "five statuses" ever comes back against ADR-0013's four. And every guard was
**mutation-verified** — reverting the rationale fix, renaming a status in `check.md`, dropping
`evidence=`, `asyncio.gather`-ing the lane, and binding `dict` instead of `CheckedRequirement`
each make the intended test fail. A test that has never failed is a test nobody has checked.

### S4.5.1 — matrix rows, read-only

Rows render from `Main.dc.html`, with `WorkspacePhone.dc.html`'s card and tally at 390 px.
`ecertis_evidence.found === false` renders on the **neutral** card, never a danger tint, with
the sentence "That is an entry France does not publish, not a gap in your bid" — ADR-0007's
fact stated as product copy rather than as a failure. The four statuses carry the design
system's words verbatim and the word always renders beside the dot, so colour is never
load-bearing.

**Partial results are stated, not implied.** Rows arrive lane by lane, so a requirement with no
row yet reads "Checking…" while the run is in flight and "Not checked" once it settles — never
a blank cell — and the summary appends "· 6 of 7 checked so far" so a partial tally cannot be
mistaken for a finished matrix.

One thing the API cannot yet support: evidence may name a **company** file that is not in
`bid.documents`, because the check searches both corpora. `citableDocuments()` appends those
with `pages: 0`, which the source panel already renders as `p. N / ?`.

Deviations from the artboard, deliberate: the desktop metric band still shows Requirements /
Pages / Problems rather than the artboard's four matrix counts (that band is not matrix-row
rendering); the phone artboard's "4 partial" is written "4 partially supported" because
ADR-0013 forbids paraphrasing the vocabulary; Confirm / Change status / Add evidence are S4.5.2;
and citations read `doc p. N` without the artboard's `§4.1` because the API carries no section
marker.

### The still is a fallback, not a poster

Noticed on the shipped page: **the band's first paint was the finished logo**, which then
cross-faded to the clip's opening frame — one dot — and drew the mark again. A visitor saw the
logo, saw it vanish, and saw it assemble. The cause was treating the static lockup as a poster
and painting it at full opacity until playback began.

It is now transparent unless the animation is not going to happen: `prefers-reduced-motion`,
a refused `play()`, or a media `error`. The band's first paint therefore matches the clip's own
first frame, which is near-empty, and the still appears only when it is the answer rather than
a placeholder. Verified in the browser — across a normal load the lockup's opacity never rises
above 0, while a stubbed-rejecting `play()` and a `reduce` preference each put it at 1.

### The landing clip, settled

The hold is **4.20 s** — the frame where the reveal finishes and before the rings begin to
move, found by tracking two signals at once: the mark's mean darkness reaches its solid plateau
(~20.25) by 4.20, and the outer ring's radius holds at **889 px through 4.20** then shrinks
continuously (888 at 4.22, 887 at 4.42, 886 at 4.52, collapsing to 331 by 6.4). Stopping there
makes the window 2.94 s, which is inside WCAG 2.2.2's five seconds — so for the first time the
component needs **neither a fast playback rate nor a pause control**. Every earlier version had
to trade one for the other.

The served file is now cut from the master with `ffmpeg -t 4.24 -c copy`: **2.43 MB → 0.48 MB,
80 % smaller**, on the page that matters most. **A re-encode was tried and rejected**, and the
reason is worth keeping: CRF 18 reached 0.30 MB and was indistinguishable in every still, but
measured in the browser its ground decoded to **231 where the master decodes to 250**. Chrome
reads these files as full range whatever the container claims — `color_range=pc`, x264
`fullrange=1`, `-vf scale=in_range=…:out_range=…` and a `tv` tag were each tried and each still
decoded to 231 — so any encoder that writes limited-range values shifts the ground permanently.
Under the `multiply` blend that paints a visibly darker rectangle across the hero: the exact
seam the mask and brightness lift exist to remove. A stream copy cannot introduce it, and the
held frame is byte-identical to the master's.

---

## ADR-0019 — The recall script, and the honest gap it leaves

**Date:** 2026-09-12 · **Stories:** S3.2.3 (and the S6.4 verification folded into it) · **Status:** accepted

### The matching rule

A golden label and an extracted `Requirement` match when **all three** hold: same document
(exact filename), pages at most one apart, and their quotes share **one unbroken run** of at
least 20 characters covering at least 0.6 of the shorter quote — compared through
`extract_reqs._comparable`, **imported, never restated**, so the score cannot drift from the
extractor's own idea of a verbatim quote. Containment either way falls out of that rule rather
than being special-cased: it is simply the case where the run covers the shorter quote whole,
which is what lets the extractor quote a longer or shorter span of the same clause.

Deliberately **not** matched, each for a reason: a translation or paraphrase (only
`source_text` is compared, never `translation` — a matcher that accepted translations would
score the translator, not the extractor); the same clause from a different document (two
citations, the line `_dedupe` already draws); the same words more than a page away; a shared
phrase under 20 characters, which is the boilerplate false positive — 20 is the shortest quote
in any committed golden file, so no label is made unmatchable by the floor.

Multiplicity is asymmetric on purpose: one extracted row may satisfy several labels, because a
quoted enumeration really does carry several duties, but each label is credited to exactly one
best row so recall cannot be inflated by a single sprawling quote.

### The denominator is the trap, so it is pinned

`scored_labels` filters on `kind=mandatory` **and** `stage is MATRIX_STAGE` — the constant
imported from `extract_reqs`. ADR-0015 recorded why the DE file keeps 11 `contract_performance`
rows in `requirements`: so the stage filter can be scored in both directions. Unfiltered, recall
reads 11 rows low.
`test_the_de_denominator_leaves_out_its_deliberate_post_award_labels` pins 116 mandatory and
105 scored against the real answer key, so deleting the filter fails loudly rather than
quietly producing a worse number that still looks plausible.

The report also surfaces the *other* direction as **stage-filter leaks**: matched pairs whose
stage disagrees, which is how a wrongly-staged label gets found rather than silently dropped.

### The threshold is not published

`evaluation.recall_threshold: 0.9` lives in `settings.default.yaml` and **not** on
`GET /dev/settings`. It gates how good extraction must be before a story counts as delivered;
it is not something the agent does. Moving it from a browser would change the number the course
reports while changing nothing about the system. ADR-0016's response-shape pin therefore passes
unchanged.

### What this story does *not* establish

**No real extraction has been scored.** The committed extraction results are `source:
synthetic`, built from the golden labels themselves — every quote a real span of the page its
label cites, with spans widened and narrowed, every 13th mandatory label dropped, orphan
sentences taken from excluded documents and two judgement fields changed. They exercise the
script; they measure nothing. The figures they produce (DE 0.92, EN 0.93, FR 0.94) are
properties of the fixtures, and **every report prints a `SYNTHETIC INPUT` banner saying so**.
The denominators, by contrast, are real.

So S3.2.1's criterion — "at least 0.9 on the DE golden tender, measured by S3.2.3" — now has a
script and still has no measurement. Three things stand between here and closing it:

1. **A live DE run** (`make test-live`, ~$1.38, ~5 min). `test_bid_run_live.py` now writes what
   it extracted to `tests/fixtures/extractions/de.live.json` **before** its budget assertions,
   so a paid run is never thrown away by a failing assert. FR and EN have no live path at all —
   the live test is DE-only.
2. **A human adjudicating the four lists** that run produces, and correcting `golden.yaml` where
   the report is right.
3. **The header flip**, which only a person can do: `labelled_by:
   llm_assisted_human_verified`, `verified_by`, `verified_on` in each of the three files.
   `GoldenMeta._verification_is_consistent` enforces it as all-or-nothing.

That closes S6.4, and with it S3.2.1 — and with the still-unrecorded end-to-end demo,
Milestone 1.

### Measured, 2026-09-12: recall is **0.75**, and R1 has materialised

The live DE run was made (245 s, $1.47, 48 model calls, **279 requirements**, 5 problems) and
scored. `scripts/recall.py` reports **0.75 — 79 of 105 mandatory bid-eligibility labels —
against a 0.90 threshold, and exits 1.** That is the first real measurement of S3.2.1's
criterion, and it fails. Risk **R1** ("extraction recall stays below 0.9") is no longer a risk;
it is an observation, and it is recorded here rather than smoothed over.

It is *not* yet evidence that extraction is poor, because three numbers have to be read
together:

- **26 misses.** Splitting them: **13 have no extracted row within a page of the label** — real
  extraction misses. The other **13 have a row on the same page that the matcher rejected**,
  which is a human judgement call: the same duty worded differently, or genuinely two different
  requirements. If all 13 were accepted, recall would read 0.88 — still short.
- **173 candidate missing labels.** The extractor found 279 rows; the answer key has 162
  entries, 105 of them scored. That asymmetry is the strongest signal in the report: the
  LLM-drafted key is very likely *incomplete*, and a missing label makes a correct extraction
  look like noise. This is exactly the failure a verbatim check is structurally blind to, which
  is why the report exists.
- **23 disagreements** on `kind` / `ecertis_criterion_id` for matched pairs.

So the number to report in `REPORT.md` is not settled until a person has adjudicated those
three lists. What *is* settled is the honest figure as of today, and the pipeline that produced
it: SP.1's 1.00 automated / 0.95 audited came from 21 hand-picked labels across 3 documents; the
key now covers 18 documents, and a harder denominator is most of the difference.

The DE golden file's own header still reads `verified_by: pending`, so **S6.4, S3.2.1 and
Milestone 1 all remain open** — correctly.

### The answer key was the problem, and fixing it did **not** fix the score

The 173 candidates were adjudicated against the PDFs: **154 accepted** (149 labels, four
extractor-split sentences merged), **19 rejected** — restatements already labelled, a
`Rechtsbehelfsbelehrung` that grants a right rather than imposing a duty, cross-references with
no obligation of their own, section headings whose requirements are the bullets beneath, and one
matcher artefact. The key went from 162 entries to **346**, and its scored denominator from 105
to **219**.

**The control is the number that matters.** Accepting the candidates and stopping there would
have reported **0.875** — a 0.125 rise bought entirely with rows the extractor had already
produced. So an independent sweep was run over the highest-yield documents, looking for
requirements **neither** the key **nor** the extractor had. It found **35**, of which 27 are
scored and **25 land as fresh misses**. That removed 0.108 of the 0.125.

Measured recall is therefore **0.77 (168 of 219)**, against 0.75 before. Essentially none of
that +0.02 is evidence that extraction improved: the numerator moved by exactly the rows the
extractor had already found. **Recall is ~0.75–0.77 and still far below 0.90.** What changed is
that the denominator is now three times harder and defensible.

Two findings worth more than the score:

- **The `Leistungsbeschreibung` was read by neither.** Its entire *Externe Hardware* personnel
  section (4.2.2/4.2.3) and the *Netzwerk* minimum requirements (4.1.2) were absent from the key
  *and* from the extraction — 16 labels the sweep had to write from scratch. By contrast the
  `Allgemeine Bewerbungsbedingungen` yielded **one** optional clause in nine pages: that document
  was labelled well. The gap is concentrated, not diffuse.
- **`Information_in_English.pdf` was excluded for a wrong reason.** Its stated reason — "adds no
  obligation of its own" — is false: the file states the German-language obligation itself, and
  by the matcher's own rule a restatement in another document is its own citation. It moves to
  `documents_scanned`. The other ten exclusions were re-checked and stand.

The sweep also exposed a real weakness in the matcher: two sweep labels (DE-485, DE-540) are
**falsely credited** to a near-identical sentence one page away — the ±1-page window and the 0.6
overlap rule together cannot separate a clause from its own restatement on the facing page. Noted
on both entries rather than papered over.

### A red measurement is allowed to be committed

`test_recall_script.py` asserted that *every* shipped extraction result is synthetic and scores
green. That was true until a real one was committed, and would then have had to be deleted to
keep the evidence — the classic case of a test that enforces a habit rather than a rule. It is
now split by artefact: a **synthetic** fixture must declare itself synthetic and score green
(they are built to), while **every** shipped result must declare its provenance, and the live
result is pinned to exit **non-zero** because it is below the threshold. When extraction
improves enough to pass, that test fails and is the reminder to record it in an ADR.

### Consequence for the layering rule

`eval/` sits **beside** `routers/`, not under it: it imports the agent, and nothing in a request
path imports it. `docs/project-plan.md`'s layering line is amended to say so.

2 718 tests, 100 % coverage, all offline. **Every story of Increment 2 is now built.**

---

## ADR-0020 — The answer keys are verified, and what verifying them changed

**Date:** 2026-09-13 · **Stories:** S6.4 (closed) · **Status:** accepted (user verification)

All three golden keys now read `labelled_by: llm_assisted_human_verified`, `verified_by: Ahmed
Nazih Ali`, `verified_on: 2026-09-13`. Each carries a `VERIFICATION.md` worksheet beside it and
a header stating what a person actually adjudicated.

### What the human pass was, and was not

It was not proofreading. `test_golden_labels.py` already re-opens every cited PDF and asserts
every quote appears verbatim on its cited page, every criterion id is a real member of the
generated enum, and `documents_scanned`/`documents_excluded` partition the pack exactly. A typo
or a wrong page cannot survive CI, so none of the review was spent on them.

What a person decided was four things a machine cannot: whether a clause is *a duty on the
bidder*, whether a criterion is pass/fail or scored, whether the key may claim what the
extractor is forbidden to infer, and whether a near-match is the same obligation.

### The four rulings

1. **`Kriterienkatalog Leistung` criteria are scored, not pass/fail.** Missing one costs
   Leistungspunkte; it does not exclude the offer. Applied to all **35** non-A criteria, not only
   the 12 that happened to disagree with the extractor — the rest were unmarked only because the
   extractor agreed, and leaving them would have made the key internally inconsistent. The **11
   A-Kriterien stay mandatory**: "das Angebot muss … mindestens 80 Punkte erreichen" is a
   threshold *on* points, and an offer below it is excluded.
2. **The statute is not the duty.** Six DE labels quoted the recitation of the law rather than an
   obligation — the § 299 StGB / § 108e StGB / IntBestG entries listed *inside* one exclusion
   ground, the sub-clause on how the buyer may prove it, and the Russia-sanctions annex. The
   bidder's duty in each case is the Eigenerklärung, labelled separately; counting the statute as
   well made one obligation look like six.
3. **A pointer is not a requirement.** DE-228 quoted the notice's eForms "Quellen der
   Eignungskriterien" field, which points at the procurement documents. The reference requirement
   itself is labelled in `Kriterienkatalog_Eignung`.
4. **The key keeps criterion ids the extractor may not infer.** The 16 disagreements are expected,
   not defects, and the report lists them separately from misses.

### The same rulings, applied to FR and EN — one matched each

Screening both keys against all four is what made those reviews small: **74 scored labels, two
matches.** FR's four banded criteria ("Critère n°N … noté sur 3") are the Leistung analogue and
became `optional`; FR-025 ("n'ayant pas obtenu la note de **5/10** … sont éliminés") is their
elimination gate and stays `mandatory`, the A-Kriterien analogue.

**EN matched ruling 2 and was deliberately answered the other way.** EN-017's quote is narration
about the objective of the exclusion criteria. In DE, dropping such a label lost nothing because
the duty was labelled separately. Here it inverts: the nine lettered situations of Art. 138(1)
and five further declarations live in `Annex_2_*.docx`, which the PDF-only parser cannot
page-anchor, so **EN-017 is the only representation of 14 real requirements**. Making it
informational would have the key assert this tender has no exclusion requirements at all. The
same rule, read as a rule rather than applied mechanically, gives the opposite answer.

### What it did to the number, and what that means

DE recall moved **0.77 → 0.73 → 0.75 → 0.76** across the rulings. **None of that is extraction
changing** — the extractor produced the same 279 rows throughout; only the denominator moved,
each time for a recorded reason. Every move failed the pinned denominator test first, which is
why the pin exists: it makes a change to the scored set a decision rather than a drift.

**S6.4 is closed. S3.2.1 is not** — its criterion is "recall at least 0.9 on the DE golden
tender", and the measurement is **0.76**. Its answer key is now verified, so what remains is the
number, not the evidence. Milestone 1 additionally wants the recorded end-to-end demo.

### One consequence for the demo and the user guide

DE extraction carries **zero** criterion ids and correctly so (the pack publishes no DUME, and
the prompt forbids inferring one). `check_reqs` only looks up eCertis when a requirement carries
an id, so **the eCertis card never appears in a DE walkthrough**. FR's eight ids were read off
the buyer's published `DUME_acheteur.xml` — all 30 of its UUIDs are members of the generated
enum, independently confirming ADR-0007. **The cross-border wedge must be demonstrated on FR**,
which affects S7.4's user guide and Milestone 1's recorded demo.

---

## ADR-0021 — Three real extraction defects, and a measurement too noisy to prove them

**Date:** 2026-09-13 · **Stories:** S3.2.1 (still open) · **Status:** accepted

Attacking the extraction gap found three genuine defects and fixed all three. It did **not**
improve recall, and the reason that sentence is not a contradiction is the last section.

### The diagnosis, which the answer key made possible

Only **55 of the DE pack's 191 pages (29 %)** produced a single row, and the misses were
concentrated: 17 of 43 in the `Leistungsbeschreibung`, which yielded 11 rows across pages 13–14
and nothing at all from pages 1–12. With `section_pages: 6` that document is four sections, and
two of them returned empty with **no problem recorded**.

### Defect 1 — `max_tokens: 4096` silently lost whole sections

Probing one section live (pennies, not a $1.50 run) returned `LengthFinishReasonError`. A dense
section returns **one** structured object holding every requirement it found; the
`Eigenerklärung Ausschlussgründe` section alone holds fifteen. Exceeding the completion cap
raises, which `_attempt` records as a bare `model_error` and re-asks once — and the re-ask hits
the same wall. Six to twelve pages of requirements vanish with nothing in the output saying why.

Raised to 16384. The same probe then returned 12 rows. This is a correctness bug independent of
any score: a run that silently drops a section is wrong even if recall never moves.

### Defect 2 — the verbatim check rejected honest quotes over parser punctuation

Seven rows from `Eigenerklärung Ausschlussgründe` were thrown away as "not verbatim" while
quoting the buyer exactly. The page holds
`... aufträge gegen geltende<br>umwelt-, sozial- oder arbeitsrechtliche ...` — `<br>` being
what `pymupdf4llm` writes when a table cell wraps — and the model, reading the clause as a
human does, wrote a space. The quote matched for 65 characters and then diverged on punctuation
the buyer never wrote. `_normalised` already stripped `**bold**` for exactly this reason
(ADR-0008) but not the tags.

The two substitutions differ, and reversing them re-breaks the check: `<br>` becomes a **space**
or `geltende<br>umwelt` fuses into a word in no document; `<sup>` becomes **nothing** or
`EUR<sup>1</sup>` splits into `EUR 1` and rejects a quote reading `EUR1`. Both directions are
pinned by tests — the second was caught *by* the first version of that test failing.

### Defect 3 — the statement of work was read as background

`prompts/extract.md` warns hard against marking delivery duties `bid_eligibility`, citing the
484 spurious rows that mistake once produced. A `Leistungsbeschreibung` reads like delivery, so
the model returned empty lists for it — while pages 9–12 carry seventeen **personnel
qualification minimums**, which are selection criteria wherever they are printed. The prompt now
names that case, with the test that settles it: a company that never won the contract would
still have had to *have* those staff to be allowed to bid.

Probed before and after on the same section: **0 rows → 14**, all
`mandatory/bid_eligibility/technical_professional`. Two controls — the framework agreement and
VOL/B — still returned **0 rows**, so the exception did not become a general loosening.

### Why the score did not move, and what that means

| configuration | matched | recall |
|---|---|---|
| baseline | 134 | 0.76 |
| + statement-of-work prompt | 130 | 0.73 |
| + `max_tokens` 16384 | 135 | 0.76 |
| + markup fix | 128 | 0.72 |

Four live runs of the same pack, same model, `temperature: 0.0`: **128 to 135 matched, a spread
of 7 labels — 4 points of recall.** Every effect being chased is inside that. At n = 1 per
configuration the table above measures noise as much as it measures the changes, and reading it
as "the markup fix cost 7 labels" would be unfounded.

**So the three fixes are kept on their own direct evidence — a probe showing 0 → 12 rows where a
section had silently died, a documented rejection of honest quotes, 0 → 14 rows with clean
controls — and not on the headline.** Reverting them to recover 0.76 would be optimising a noisy
metric over a system known to be wrong.

The headline is **0.76 → 0.72 on the committed run, and the honest summary is that recall is
~0.74 ± 0.02 and unchanged.** S3.2.1 stays open.

### What this changes about method

Single live runs cannot validate an extraction change: the noise floor is ±4 points and each
measurement costs ~$1.60 and four minutes. Anything further needs repeated runs per
configuration, or a cheap offline proxy. The **section probe** built here is that proxy for
targeted work — it isolates one section for pennies and answers "does this section extract at
all", which is what found all three defects. Total spend for this round: about **$6.40**.

One consequence for the next attempt: `Erklaerung_zur_sozialen_Nachhaltigkeit` pages 9–12 now
produce 16 `no_verbatim_quote` rejections where they previously produced a `model_error` and
nothing. That section is no longer silently lost, which is the improvement; its quote fidelity
is the next defect, not a regression.

---

## ADR-0022 — The DUME is a structured input, and the wedge finally runs

**Date:** 2026-09-14 · **Stories:** S2.4.3, and DUME/ESPD ingestion (new, unnumbered) · **Status:** accepted

### The discovery that forced this

The cross-border wedge — eCertis equivalence, the thing that distinguishes this from TenderWolf
— was **completely dark end to end**, and nobody had noticed because every piece worked in
isolation: the cached register, the bidder-language lookup, the tool, `check_reqs` calling it,
the UI card, and eight human-verified FR labels carrying criterion ids.

`check_reqs` only looks up eCertis when a requirement carries an `ecertis_criterion_id`, and
**nothing in the running system ever set one.** Scanning all 38 fixture PDFs across DE, FR and
EN found **zero** real ESPD criterion UUIDs. `prompts/extract.md` forbids inferring one from
wording, correctly (ADR-0007: a wrong id is worse than none). The only input that carries them
is `DUME_acheteur.xml`, and upload was PDF-only, so the pipeline never saw it. The human
labellers had read that file off disk; the product could not.

This also corrects advice given earlier in ADR-0020 and in `HANDOVER.md`: "demo the wedge on FR"
was **wrong**. FR's RC prints no UUIDs, and the notice's two are TED internal identifiers, not
criteria.

`CLAUDE.md` had already specified the fix and it had never been built: *"Treat a published DUME
as a high-confidence structured input, not as prose to extract."*

### Decisions

**The ESPD type code classifies; no model is asked.** `CRITERION.EXCLUSION.*` →
`exclusion_ground`, `SELECTION.ECONOMIC_FINANCIAL_STANDING` / `TECHNICAL_PROFESSIONAL_ABILITY` /
`SUITABILITY` → their categories. A prefix table, not inference — which is the whole point of
preferring a DUME to prose. All 30 of the fixture's criteria survive validation against the
generated `EcertisCriterionId`; an id the register does not know is dropped and reported as an
`INVALID_CRITERION_ID` problem rather than looked up and silently answering nothing.

**A DUME row has no page, and may not pretend to.** `Requirement.page` became `int | None` and
gained `source: tender_document | espd_request`, bound by a model validator: **page is present
exactly when the source has pages.** `migrations/0005` enforces the same as a check constraint,
`(source = 'espd_request') = (page is null)`, which a direct SQL write cannot bypass. Giving such
a row `page: 1` would render in the workspace as `DUME_acheteur.xml p. 1` — a citation a reviewer
can click and land nowhere, which is exactly the failure the product's citation promise exists to
prevent. It cites file + criterion id instead, and the UI renders it as a **label, not a link**,
because the file is XML and the source panel shows PDFs.

**The upload boundary was extended, not loosened.** A new `DocumentKind.TENDER_ESPD_REQUEST` and
an accept-list keyed on kind: every other kind stays PDF-only, and an XML posted as
`tender_document` is still 415 with the PDF message. The three-fold spoofing defence keeps its
shape for XML — suffix, declared content type, and a content sniff that is a full parse through
the hardened reader, so a hostile file is refused at 415 before any background task exists.

**XML hardening, written down because `defusedxml` is not installed and was not added.**
`ingestion/safe_xml.py`: a 4 MB cap checked before parsing; then an `expat` preflight that builds
no tree and whose `StartDoctypeDeclHandler` **raises**, refusing a DOCTYPE before its internal
subset is read — closing billion-laughs, quadratic blowup, external entities and external DTDs at
the declaration site rather than trusting a runtime default; depth capped at 40; only then
`ET.fromstring`, which by construction cannot meet an entity declaration. Twelve tests fire real
payloads, including an XXE at `/etc/passwd`, asserting the refusal rather than merely the absence
of an exception. **Residual risk, stated:** parsing is still linear work on attacker-sized input
bounded only by the cap, and namespace and attribute handling are expat's.

### Consequence

An FR bid now yields **30 requirements carrying criterion ids** — 24 exclusion grounds resolving
straight to eCertis matrix rows, 6 selection criteria additionally entering the checking loop.
`test_espd_to_ecertis.py` pins the chain offline and free: a French buyer's tax criterion becomes
a row whose `ecertis_evidence` names the **German** paper for a `de` bidder, with the scripted
model asserted to have received **zero prompts**. The wedge is no longer notional.

### S2.4.3 — the one-command seed

`make seed-demo` writes the demo GmbH, its profile, its Store memory at `profile/{company_id}`,
and all ten S6.3 documents driven to `ready` through the **same** `DocumentPipeline` wiring the
upload route uses, so a seeded document is chunked and embedded identically to an uploaded one.

Idempotence is by deterministic `uuid5` ids with a read before every write, so a second run
**spends nothing** — not merely "changes nothing", which matters because embeddings are billed.
A document whose row exists but is not `ready` is **reported, not repaired**: re-upload collides
with `x-upsert: false` and re-embedding would duplicate chunks, so it names the row and the exact
Storage key and exits 1. First run costs ≈ **$0.0002**.

It is a second script rather than an extension of `seed_dev_company.py`, which imports nothing
from `crossbid` on purpose — that is what lets it run before the package is importable and with
no secret present, and folding them together would have cost it that property.

---

## ADR-0023 — The wedge ran, but the product could not reach it

**Date:** 2026-09-14 · **Stories:** the S2.4.3 walkthrough, and the DUME upload path · **Status:** accepted

### The discovery

ADR-0022 ended "the wedge is no longer notional", and at the layer it tested that was true:
`test_espd_to_ecertis.py` pins a French criterion becoming a row naming German evidence, with
the model receiving zero prompts. What it could not see is that **no user could produce that
row**, because the web app would not let a DUME be uploaded.

`lib/documents.ts` listed three `DocumentKind` values where the schema has four, so
`tender_espd_request` never appeared in the upload form's select. `validateUploadFile` refused
any file not ending `.pdf`. The file input's `accept` was `application/pdf,.pdf`. Each of the
three would have been sufficient on its own.

**`DOCUMENT_KIND_LABELS` already had a correct entry for the kind** — label, hint and all,
added with the ADR-0022 work. That is what made the omission invisible to review: every search
for the kind's name in the frontend found a hit, and the hit was unreachable code.

This is ADR-0022's own failure mode recurring one layer up. There, every piece worked in
isolation and nothing set `ecertis_criterion_id`. Here, the backend sets it correctly and
nothing could deliver the file that makes it happen. A test for each piece did not add up to a
test of the path.

### Decisions

**Client validation is a table keyed by kind, not a constant.** `uploadShapeFor(kind)` returns
the suffix, the accepted content types, the byte cap and the four refusal sentences, mirroring
`XML_KINDS` and the `*_DETAIL` constants in `routers/documents.py`. The sentences are copied
deliberately so the bidder reads the same words whichever side notices first; the server stays
the authority, since neither side can settle a PDF from its filename and the ESPD request is
only confirmed by a full parse.

**A kind that has no pages shows `—`, never `0`.** `ingestion/pipeline.py` stores zero pages for
an XML form as "the honest count", and it is honest in the database. Printed in a table column
it becomes a claim — *we read this file and found no pages* — about a file that was never
paginated. `hasPages(kind)` gates the pages column, the unread-pages column and the start-bid
checklist's description. This is the same distinction ADR-0022 drew by making a requirement's
`page` nullable and rendering its citation as a label rather than a link.

**`TENDER_DOCUMENT_KINDS` exists twice and both copies must agree.** `readmodel/bids.py`'s copy
already carried the warning that omitting the ESPD request there "would be the one way to upload
a DUME and never use it". The frontend's copy omitted it. A duplicated set with a comment
explaining the trap on only one of the two copies is not a safeguard.

### Consequence

Verified on a real run rather than a fixture — notice + RC + DUME for 618320-2026, uploaded
through the browser: **135 requirements, 30 of them from the DUME**, each carrying a real
criterion id and a null page, with the `(source = 'espd_request') = (page is null)` constraint
holding exactly 30 to 30. All 30 eCertis lookups returned `found: true`. The card resolves
*Terrorist offences* to `Auszug aus dem Bundeszentralregister / Führungszeugnis` and
*Professional risk indemnity insurance* to the demo company's own €5 000 000 policy. The DUME
row cites `DUME_acheteur.xml · ESPD criterion` as a label, never a page link.

**The lesson for the remaining increments:** a wedge is reachable only if some test or run
starts where a user starts. Three ADRs now describe the same product working at three different
depths; only the third one a person could perform.

### Three configuration traps, recorded because each looked like a broken product

None is an architectural decision, and all three cost real time, presenting as "the app is
broken" rather than as configuration. They are in `HANDOVER.md` in full.

- **`npm run build` while `next dev` runs** overwrites the `.next` the dev server serves from:
  the HTML renders and every `_next/static/*` chunk 404s. Indistinguishable in the browser from
  the known `output: 'standalone'` / `next start` gotcha, and a separate cause.
- **Next reads `.env*` from `frontend/` only**, so the root `.env`'s `NEXT_PUBLIC_DEV_COMPANY_ID`
  never reached `npm run dev` and every API-backed screen 401'd. Only `make dev` was ever wired,
  through a Compose build arg. Fixed with an untracked `frontend/.env.local`.
- **`SUPABASE_STORAGE_BUCKET` was unset**, so the app used the code default `company-documents`
  while the project's bucket is `company-docs`; every upload failed `404 Bucket not found`.
  `storage.py` suppresses Storage's own message on purpose (ADR-0008), so the only symptom was
  "The file could not be stored" on all ten seeded documents. **When uploads fail wholesale,
  list the buckets before reading the code.**

---

## Retro — Increment 2, and the re-forecast the cadence asks for

**Date:** 2026-09-14 · **Status:** the sprint's closing note, not a decision

### What slipped, and why

Every story of Increment 2 was built on 2026-09-12, two days after the increment started. What
took the remaining two days was not code, and that is the finding worth carrying forward:
**three separate times, something was "done" at the layer it was tested and not done at the
layer a person touches.** S6.4's labels existed but were unverified drafts, so S3.2.1's recall
figure measured nothing until a human adjudicated 346 entries. The eCertis wedge passed its
tests while nothing in the running system set a criterion id (ADR-0022). Then the DUME could be
ingested but not uploaded (ADR-0023). Each was found by trying to *use* the product rather than
by reading or testing it, and each would have been found on the demo recording instead — which
is the one thing that had been deferred every sprint.

The other real cost was measurement noise. Four identical live runs scored 128–135 of 177, so a
single $1.60 run cannot validate a prompt change; two days of recall work produced three genuine
extraction fixes (ADR-0021) and no movement in the headline, and the honest reading is that the
headline could not have moved detectably either way. The section probe, found late, does the
same job for pennies. **Recall stands at ~0.74 ± 0.02 against a 0.90 target and is reported as
a measurement, not chased.**

Nothing was descoped. Increment 3's S2.4.3 was pulled forward because the demo needed it.

### Velocity, measured

Work began 2026-09-10 and this note is written on 2026-09-14: **five calendar days** for
Increment 0, Increment 1, Increment 2 and one Increment 3 story — about **43 of the plan's 75
stories**, plus the unnumbered DUME ingestion. 3 996 tests, 100 % coverage, 23 ADRs.

The plan's estimate was 87–205 hours for 75 stories, and R5 flagged velocity as unknown. It is
no longer unknown, but **the measured figure does not refute the estimate — it replaces its
unit.** This is agent-assisted calendar time with a single reviewer, not solo developer-hours,
and the two are not comparable. Quoting "43 stories in five days" as if it beat a 205-hour
estimate would be the same error as quoting 0.72 recall as precise.

### Re-forecast to the submission line

| Increment | Stories left | Forecast |
|---|---|---|
| 3 — review round-trip | 6 (S2.4.3 done) + S6.5, S7.3 | ~1 day |
| 4 — every graded requirement | 18 | ~2–3 days |
| 5 — submission-ready | 5 | ~1 day |

**~4–5 calendar days to Milestone 5**, at the observed rate and assuming no repeat of the
verification work that dominated this sprint. Two things make that optimistic and are named
rather than buffered: Increment 4 is the widest (18 stories, including magic-link auth, the
first story to touch real sign-in), and S7.1's eval report will re-open the recall question
with a threshold that is currently failing.

**The change to make next sprint:** record the demo *first*, not last. Every defect this sprint
was reachable only by using the product end to end, and the demo is exactly that walk. Deferring
it turned the walkthrough from a recording into a debugging session three times running.

---

## ADR-0024 — The scorer decides by rule, and the prose is a table

**Date:** 2026-09-14 · **Stories:** S3.4.1 · **Status:** accepted

S3.4.1 asks for "a clear go or no-go with the exact gaps in my language". Three things in that
sentence had to be decided before any of it could be built.

### Where the judgement lives

**The decision is a pure function and nothing else may make it.** `agent/scoring.py` takes
requirements, matrix rows, the bidder's profile and a language, and returns a `Verdict`. No
model, no database, no clock. `tests/unit/test_scoring.py` is therefore the specification
rather than a smoke test — if a decision cannot be re-derived from the matrix the bidder can
see, it is not a decision this product is allowed to make. The node above it
(`nodes/score_verdict.py`) exists only to fetch the one input the state does not carry.

Five rules, each forced by something already in the repo rather than invented here:

1. **Only `bid_eligibility` is scored.** SP.1's 579 "mandatory" requirements (ADR-0003) are
   what happens without the filter. The DE golden key deliberately keeps `contract_performance`
   rows so the filter can be scored in both directions, and the handover already warns that
   anything scoring must apply it.
2. **`unsupported` is fatal on a mandatory row and on *any* exclusion ground**, whatever the
   extractor called the ground's `kind`. An exclusion ground marked `optional` is an extraction
   defect, and reading it as a softer requirement would let that defect decide a bid.
3. **A mandatory requirement with no row is an open item, never a pass.** Checking is total, so
   a missing row means a lane never ran. "Not checked" must never read as "fine".
4. **`insufficient_evidence` is "nothing was settled", not a proportion.** A cut-off like "fewer
   than half the rows" would be a number nobody in the plan chose. An empty matrix is the same
   answer for the same reason — which is why `Verdict` now refuses a `go` with
   `mandatory_total == 0`, and permits declining when nothing was scored at all. Both are new
   clauses in the model's validator, and both are the "never a `go` without evidence" criterion
   restated where it cannot be bypassed.
5. **A gap names numbers only where the comparison is honest.** `required` comes off the
   requirement's own `Threshold`; `actual` comes off the typed profile, and only for `at_least`
   against FTE or against turnover *in the same currency*. Converting currencies is
   `currency_convert`'s job; a scorer that guessed would be inventing the bidder's answer.

### The prose is data, not a model call

The story also asks that the explanation follow the user's language and tone settings. It is
rendered from a table of format strings — `agent/verdict_text.py`, nine `Phrasebook` entries
keyed `(language, tone)` over `de`/`en`/`fr` × `plain`/`formal`/`brief`.

**A model was the obvious alternative and was rejected.** The rules engine refuses a model's
opinion on the decision; letting one write the sentence that explains the decision would
readmit it one field later. It would also make the same bid come back differently on every run,
which is precisely what makes a `live` recall measurement expensive to read (ADR-0021), and it
would put a network failure inside a node that currently cannot fail.

Splitting the table into "language chooses words, tone chooses structure" does not survive
contact with the brief tone: `Kein Angebot.` is not the plain headline with clauses removed, it
is a different sentence. Nine flat entries are greppable, and `test_verdict_text.py` walks every
pair, every `Decision` and every field, asserting no unresolved brace survives — a derivation
would not have made that checkable.

Two smaller findings inside that table. **Thousands are grouped per language**: `3,000,000 EUR`
in German prose reads as three point zero, because the comma is a decimal separator there, so
German gets `.`, French a space, English `,`. And **the "and 35 more" line is not a bullet** —
a reader counting bullets should be counting gaps.

### Where it runs, and what it changed

`plan_checks → check_reqs → score_verdict → await_review`, with `score_verdict` wrapped in the
`scoring` stage like every other node. Two consequences worth naming:

- **The empty-extraction path now goes to the scorer, not straight to the interrupt.** A bid
  whose extraction found nothing still owes its reviewer an answer, and rule 4 makes that
  answer `insufficient_evidence` rather than a silent park.
- **The read model gains `set_bid_verdict`**, writing the `bids.verdict` column 0001 already
  declared, and `BidSummary.decision` is read out of it rather than kept in a column of its
  own — two places recording one answer is two places that can disagree. A stored verdict the
  contract no longer recognises (a pre-0004 `go_with_open_items`, say) answers `null` and logs,
  rather than 500-ing a bid its reviewer needs to re-run. This is the scoring half of S3.4.3;
  the review half lands with S3.4.2.

`Verdict.score` stays `None`. The French fixture's weighted 5-of-10 cut-off is real, but nothing
in `Requirement` carries a buyer's points scale, so producing one would mean inventing it.

---

## ADR-0025 — Two answers, kept apart: the review round-trip

**Date:** 2026-09-14 · **Stories:** S3.4.2 · **Status:** accepted

The human interrupt was built in S3.1.1 and parked a bid at `awaiting_review` with nothing to
resume it. This is the other half: the reviewer's submission crosses the interrupt, the scorer
re-runs on their statuses, and the bid ends `complete`.

### The verdict and the decision are different facts

The first design tried to make the review produce *one* answer — the final verdict — and it
does not fit, for a reason that is not a modelling inconvenience but the point of the story.

**The verdict is what the rules say about the matrix as the reviewer left it. The decision is
what the reviewer decided.** A reviewer who marks two rows `not_applicable` and still says
`no_go` is exercising judgement the rules cannot encode, and that is why a person is in the
loop at all. `Verdict`'s own validator makes the collapse impossible anyway: it refuses a
decision that contradicts its gaps, and a human override frequently does exactly that.

So `finalize` records three things — the agent's original verdict, the re-scored one, and the
reviewer's decision — and **the override is the difference between them**, not a flag. The
`reviews` table 0001 declared already had columns for all three; what was missing was
`bids.decision`, added in 0006, so the dashboard can read a final answer without joining.

That means `BidRow.decision` now has two sources with a precedence rule: the reviewer's call
once there is one, else the agent's advisory one off the verdict. This *revises* ADR-0024,
which derived it from the verdict alone and argued against a second column. The argument there
was against two copies of one answer; this is two different answers, and a bid parked at
`awaiting_review` still needs something on the dashboard.

### The parts that could have gone quietly wrong

**`matrix_rows` stopped being an appending channel.** `apply_review` returns the whole matrix
with the reviewer's dispositions on it, and under `operator.add` that second copy would have
sat *beside* the agent's original — 135 rows becoming 270, the re-score running over both, a
reviewer's `unsupported` counted next to the `supported` it replaced. `state.merged_rows`
replaces by id and appends what is new, which is identical to `operator.add` for the checking
lanes (their ids are disjoint) and correct for the review.

**`model_copy(update=...)` skips validation.** It is the obvious way to write a revised row and
it would have let a reviewer mark a row `supported` with nothing cited — straight past
`MatrixRow`'s central invariant, into the database, and out to a bidder as proof. Every revised
row is rebuilt through `model_validate` instead. The router checks the same thing first and
answers 422, so the node's raise should be unreachable; it is there because "should be" is not
an argument for leaving the bypass open.

**The 409 is a conditional `UPDATE`, not a status check.** A read-then-write would let two
submissions both see `awaiting_review` and both resume the graph. `claim_bid_for_review` moves
the row off `awaiting_review` in one statement and the loser sees `rowcount == 0`. It cannot
distinguish "already reviewed" from "still running" and the router deliberately says the same
thing for both.

**The resume payload is re-validated at the interrupt.** `interrupt()` returns whatever
`Command(resume=...)` carried, and a resume can be issued by anything holding the thread id, so
`_request_review` parses it as a `ReviewSubmission` before any node downstream sees it.

### The review runs inline, unlike every other graph invocation

`POST /bids/{id}/review` awaits the resume rather than answering 202. Everything past the
interrupt is rules and two statements — no model call, no page to parse — so it finishes inside
a normal request, and making the reviewer poll for the consequence of their own click would be
latency invented for symmetry with `POST /bids`. A failure is written to the bid before the 500
is raised, because the bid was already claimed off `awaiting_review` and a silent failure would
strand it.

### `reviews.reviewer_id` is now nullable, and that is the honest answer

`auth.py` says it plainly: under `AUTH_MODE=dev` a header is not a credential. There is no
verified identity to record. The obvious substitute — the company's `owner_user_id` — would
assert that a particular person reviewed a bid when the system cannot know it, and **an audit
trail that records an unverified identity is worse than one that records none.** The column
stays empty until magic-link sign-in (S0.3.1) can fill it truthfully. This is a real gap in the
audit story and is named here rather than papered over.

---

## ADR-0026 — The reviewer's edits had nowhere to land

**Date:** 2026-09-14 · **Stories:** S3.4.3 · **Status:** accepted

S3.4.3 reads as bookkeeping — "the read-model tables are written at each point, `GET /bids`
reads only from them, and a consistency test proves it". Writing the consistency test found
that the first half was false in a way nothing else would have caught.

### The bug the story existed to find

`readmodel/matrix.py`'s upsert deliberately excludes `reviewer_status`, `override_reason`,
`attached_doc_ids` and `reviewed_at` from its `do update set` list. That is a real safeguard —
a resumed run re-checking a requirement must refresh the agent's finding and leave a human's
disposition alone — and its docstring said, correctly, "S3.4.x writes them from the review,
through its own statement."

S3.4.2 did not write that statement. `apply_review` returned a matrix with every row
dispositioned, `_project` wrote it through the *agent's* upsert, and every reviewer column was
silently dropped. The bid reached `complete`, the audit row was written, the decision was
recorded — and the matrix in Frankfurt still read `pending` on every row. Nothing failed. The
checkpoint was right and the projection was wrong, which is precisely the failure mode the
plan's read-model rule names.

**This is ADR-0022 and ADR-0023's pattern a third time**: every piece correct in isolation, the
path between them never walked. The difference is that this time the walk was a test rather
than a demo, which is what the Increment 2 retro asked for.

`write_reviewed_rows` is now the second statement, called once at `finalize` with the whole
matrix. Every row is written, not only the edited ones, because "confirmed, at this time" is a
fact about an untouched row and leaving it `pending` makes a finished bid indistinguishable
from an abandoned one.

### The consistency test is a comparison, not a recorder

`test_read_model_consistency.py` runs one bid from `START` to `complete` — fan-out, interrupt,
a review that changes a row, the re-score — and then compares everything the poller can see
against `aget_state`.

The design choice that makes it worth anything: **the fake read model stores what the real
statements store.** The matrix upsert replaces by id and preserves the reviewer's columns; the
reviewer's update writes only those; problems and verdict are replaced whole. A convenience
fake that remembered the last list it was handed would have agreed with the checkpoint by
construction and proved nothing — and would have passed against the bug above.

Both subtleties were mutation-checked rather than assumed. Removing the `write_reviewed_rows`
call fails two tests; reverting `matrix_rows` to `operator.add` fails two others. A consistency
test that cannot fail is a comment.

### What is deliberately not tested here

The SQL. `test_bids_readmodel.py` asserts the statements, including that the agent's upsert
still cannot name a reviewer column — a text assertion, so re-widening it to "fix" a future bug
fails loudly. What this test adds is whether `graph._project` maps the *state* onto those
writes faithfully, which is answerable offline and was where the defect actually was.

---

## ADR-0027 — Resilience: what is retried, what is re-asked, and what is only warned about

**Date:** 2026-09-14 · **Stories:** S3.4.4 · **Status:** accepted

The story reads as one theme and is five separate mechanisms. An audit of the code against
its criteria before writing any of them found one already satisfied, two absent and two
partial — which is why what follows is a set of placements rather than a feature.

### Two failures, two layers, and the split is deliberate

A **route** failure — a timed-out call, a dropped connection, a rate limit, a 5xx — is
retried once and then reissued against a different model. A **schema** failure — an answer
that does not validate — is re-asked once with a correction and then becomes a
`partially_supported` row for the reviewer. They are handled one layer apart on purpose:

- `llm.ResilientModel` owns the route, because a route failure is the same failure whatever
  was being asked and the wrapper can know nothing about the question.
- `check_loop._verdict_with_one_re_ask` owns the structure, because only that module can
  write the correction, and the correction is the whole point of re-asking.

Collapsing them would multiply: two attempts × two re-asks is six model calls for one
requirement, against a $2.50 run budget and 258 requirements.

**`ChatOpenAI` retries twice by itself.** `max_retries=0` is now set, and without it "one
retry" would have been one of ours on top of two of langchain's — three times the latency
before a fallback, and an `llm_timeout_seconds` that bounded a third of the real wait. This
was the single most likely way for the story to be "done" and untrue.

**The fallback is a different vendor.** `models.fallback` is
`google/gemini-2.5-flash-lite`, not a second OpenAI slug. The failure a fallback exists to
survive is the primary route being slow or down, and a second slug on the same route is down
with it. It is also probed by `verify_configured_models`, because a fallback nobody checked
is worth nothing: the one moment it is used is the moment the primary has already failed.

### Two criteria are not about failure at all

"No eCertis entry → flagged" and "an expired certificate → a warning with its date" describe
a row that came back *looking* settled while something about it needs a human's eye. Both
now live in `agent/flags.py`, applied by `score_verdict`.

**`score_verdict` is the only node holding the profile and the whole matrix at once.** The
obvious placement was a checking lane, and it would have meant threading the certificate list
through `plan_checks`, the graph state, every lane's `Send` payload and `Bidder` for the
benefit of one comparison. The scorer already fetches the profile for `tone` and the gap
figures. The flagged rows go back on the `matrix_rows` channel, which S3.4.2 had already made
a merge-by-id reducer, so they replace rather than double — a placement that would not have
been available one story earlier.

**Nothing is downgraded.** The status stays as checking left it. The story asks for a
warning and the product is advisory: a reviewer told that the ISO 27001 certificate behind a
`supported` row expired in March is better served than one whose row silently became
`partially_supported` with the reason buried. A downgrade would also move the verdict on a
fact the scorer never saw.

**The certificate matcher is a heuristic, and it is stated rather than hidden.** There is no
join to make — `CertificateHeld` carries a name and an expiry, `Evidence` carries a document
id and a filename. Substring matching was tried first and fails on the real names:
`ISO/IEC 27001:2022` normalises to `isoiec270012022` and `ISO_27001_Zertifikat.pdf` to
`iso27001zertifikatpdf`, and neither contains the other — the one pairing that matters most
would have been missed silently. Shared *tokens* work, because the signal in a certificate
name is the standard number. The threshold is two and not one: `ISO 9001` against that same
filename shares only `iso`, and warning there would send the reviewer after the wrong paper.
`test_flags.py` is written as the matcher's specification — the pairings it must make and the
ones it must refuse — and pins the threshold, because lowering it to one is the tempting fix
when a pairing is missed.

A proper join wants `document_id` on `CertificateHeld`. That is a profile story, not this one.

### Corrected while here

`CertificateHeld`'s docstring said "the scorer reads it" and the scorer did not: the only
consumer of `expires_on` in the whole backend was `GET /companies/me`. It is true now.
`is_expired_on` also joins `is_valid_on` on the model, and the two are **not** each other's
negation — a certificate with no recorded expiry is neither valid nor expired, which is why
the profile form warns about one group and this story flags only the other. The router's
inline copy of that predicate now calls the model's.

"Unread pages are listed on the bid" needed no code: the parser derives them, the pipeline
stores them, and `GET /bids/{id}` returns them per document alongside the `problems` list. It
gained a test at the layer a reviewer meets it, which is the only part that was missing.

---

## ADR-0028 — What a fresh reading of Increment 3 found

**Date:** 2026-09-14 · **Stories:** S4.5.2, S4.5.3, and corrections to S3.4.1/S3.4.2 · **Status:** accepted

The two workspace screens closed F3.4. Before wiring them, the four backend commits were read
again from scratch against ADR-0024 to ADR-0027 — "does the code do what the ADR says". It
found six defects the test suite did not, four of them in the scorer's own rules, and every
one of them a **wrong answer that validated cleanly** rather than a crash.

### The scorer was wrong in three ways, all of them generous to the bidder

**An exclusion ground the extractor labelled `informational` could not block a bid.**
`_severity_of` short-circuited on `kind is INFORMATIONAL` *before* the test that gives an
exclusion ground its severity regardless of kind — while the module docstring and ADR-0024
rule 2 both say, in as many words, that `kind` is not consulted for an exclusion ground. The
test written for that rule parametrised `optional` and not the third value of the same enum.
Reproduced: a bidder with evidence *against* them on a conviction, and one supported formal
requirement, scored **`go` with zero gaps**. `kind` comes from the extraction model, so this
is exactly the extraction defect the rule exists to neutralise. The kind check now applies
only to requirements that are not exclusion grounds, and the test parametrises all three.

**A matrix nobody had checked scored `conditional`.** Rule 4 reaches
`insufficient_evidence` only when some row is `partially_supported`. Five mandatory
requirements with *no rows at all* — a lane that never ran, a cancelled shutdown — produced
"This bid is possible with open items. 0 of 5 mandatory requirements are supported." An
*empty* matrix correctly declined, so the worse state got the more encouraging answer than
the better one.

**A matrix whose mandatory rows were all `not_applicable` scored `go`**, with a rationale
reading "0 of 3 mandatory requirements are supported". The `go` gate counted *settled* rows,
and `not_applicable` settles.

All three are one repair: **the gate is `mandatory_supported`, not `settled`.** The agent
needs one mandatory requirement it can say is supported, or it declines. That single sentence
covers the empty matrix, the unchecked matrix, the all-partial matrix and the all-inapplicable
matrix — each of which was a different wrong answer before. `not_applicable` still closes a
gap; it just cannot open a recommendation. `Verdict`'s validator moved with it: `go` now
requires `mandatory_supported > 0` rather than `mandatory_total > 0`, and declining is
refused exactly when a `go` would be available.

### The 409 was not airtight, and the claim that made it was undone one node later

`claim_bid_for_review` is a correct conditional `UPDATE`. It is also immediately reversed: on
resume LangGraph re-runs `await_review` from its top and the stage wrapper's first act is to
write `awaiting_review` again. The project already knew that — `graph.py` decision 2 documents
it and a test asserts the status is written twice — and nothing had connected it to the claim.
So for the several awaited round-trips until `apply_review` writes its own status, the row is
claimable a second time: a double-click resumes one thread twice, for two audit rows, two
decisions and two passes of `write_reviewed_rows`.

The router test passed because its fake runner never re-runs the real graph — **the same trap
ADR-0026 says the consistency test was written to avoid**, one layer up.

`BidRunner` now holds an in-flight set, tested before the first `await` so nothing interleaves
between the test and the insert, and the router answers the same 409 for it. One API process
(ADR-0010) is what makes an in-process guard sufficient; a second process would need the
database claim to survive the resume instead.

### A failed review left the bid permanently dead

After the claim, any exception sent the bid to `failed` — which is terminal, which
`resume_unfinished_runs` skips, and which `claim_bid_for_review` refuses. A transient pool
timeout in `record_review` would therefore strand the bid for good, with the reviewer's
submission sitting in its checkpoint and a permanent 409 in front of the only endpoint that
could finish it. `release_bid_to_review` puts it back on `awaiting_review` with the reason
recorded: the graph is still parked, and resubmitting is the affordance the product has. A
test asserts the status a release restores is the one a claim accepts, because the defect was
that they disagreed.

### `GET /bids/{id}` never showed the reviewer's decision

ADR-0025's whole point is that the verdict and the decision are two different facts, and
`BidResponse` carried only the first. For the case the ADR is written about — the reviewer
overrides a `conditional` re-score with `no_go` — the dashboard showed `no_go` and the
workspace showed `conditional`, with the reviewer's own click answering with the re-score.
`BidResponse.decision` now carries it. S3.4.3's consistency test could not see this: it
compares the projection against the checkpoint, not the API shape.

### What was checked and found sound

Worth recording, because these were the suspicions: `_decide` cannot produce a `Decision`
that `Verdict` rejects (fuzzed over every 1-, 2- and 3-requirement matrix across all
kind × category × stage × row-status combinations, before and after the repair);
`merged_rows` is order-stable and duplicate-free under LangGraph's superstep fold, including
on a resumed lane; `ResilientModel.ainvoke`'s two-block control flow has no path that
discards a successful answer or falls back after one; `flags` is applied once and cannot
double-append, because the graph has no back-edge; and all five new SQL statements carry
`company_id` and are in their module's `SCOPED_STATEMENTS`.

### Left standing, deliberately

The row-edit validation exists twice — `routers/bids.py::_check_row_edit` builds a candidate
row for the 422, `review.py::_reviewed` builds it again for the write. They agree on every
input today. Consolidating them is the right change and is not this story's; the risk is
recorded here because it is what would turn a future `MatrixRow` invariant into a 500 plus a
stranded bid rather than a 422.

`RETRYABLE` includes `RateLimitError` and retries with no backoff, so a 429 costs one wasted
call before the fallback. And `check_loop`'s re-ask catches `ValidationError` only — a
`LengthFinishReasonError` is the same "not the requested shape" and is re-asked by nothing,
which is the failure mode ADR-0021 caught in extraction. Both are noted rather than fixed:
they are cheap to add and neither is a wrong answer, only a wasted or lost one.

---

## ADR-0029 — The walkthrough, and the gap only the walkthrough found

**Date:** 2026-09-14 · **Stories:** the F3.4 walkthrough · **Status:** accepted

Increment 3 was code-complete, 4 233 tests green, four ADRs written and a fresh reading of the
backend already done (ADR-0028). The round trip had still never been walked in a browser. It
has now: the FR pack uploaded through the upload form, a bid started, the run parked, a row
edited, the verdict confirmed — against Frankfurt, on the real build.

### What the run proved

`618320-2026`, notice + RC + `DUME_acheteur.xml`, French source, German bidder. Parked at
`awaiting_review` in **2 min 23 s**: **144 requirements, 30 of them from the DUME**, 144 matrix
rows, **29 of 30 eCertis lookups resolved** — the thirtieth has no national FR entry, which is
the normal answer ADR-0007 documents and which `flags.py` now writes onto the row as a reviewer
notice. Verdict `conditional`, 1 of 131 mandatory supported.

The review then behaved as designed, end to end: the client refused an override with no reason
and moved focus to the field; one row was marked `not_applicable` with a reason; the bid ended
`complete` with **143 rows `confirmed`, 1 `overridden`, and `reviewed_at` set on all 144** — the
write ADR-0026 added, doing its job on real data rather than in a fake. Exactly **one** `reviews`
row, `reviewer_id` NULL as migration 0006 intends, `bids.decision = conditional`. A second
submission answered **409**, and the audit table still held one row. The re-score moved the open
items from 143 to 142 because of that single edit, which is S3.4.2's "the scorer re-runs on my
statuses" visible on screen.

### The defect

Pressing **Confirm verdict** with a row edit the server refuses sent the request anyway. The
bid was never at risk — the router validates before it claims, so it answered 422 and left the
bid parked — but the reviewer was shown
`Row e0842294-1954-5037-a8f4-794173452245 cannot be marked supported`: **a raw UUID they have
never seen**, which is precisely the answer S4.5.2's mirrored rules exist to spare them.

It is an integration gap, and an instructive one. Each half was right. The matrix computed
`blockers` and showed each row its own sentence. The verdict panel deliberately did not read
them — its author wrote, in as many words, "if you hand it edits the server would refuse, the
422 surfaces as a form error rather than being caught early". Neither is wrong alone. The
defect lived in the wiring between them, which belonged to neither author, and **no test at
either end could have seen it**: the matrix's tests end at the hook's output and the panel's
begin at its props.

`VerdictDecisionForm` now takes `blockedRowCount` and refuses last — after the decision and the
acknowledgement, because a reviewer who has not chosen a decision should be told that first —
with a sentence that counts rows instead of naming ids and points at the matrix, where each row
is already saying what is missing.

### The lesson, now four for four

Increment 2 recorded three occasions where something was done at the layer it was tested and
not at the layer a person touches: unverified answer keys, a wedge no run could light
(ADR-0022), a DUME no user could upload (ADR-0023). Increment 3 has now produced two more —
reviewer edits that reached `complete` without reaching the database (ADR-0026, found by a
test that walked the path) and this one, found only by a person-shaped walk of the same path.

The pattern is sharp enough to state as a rule: **a seam between two correctly-built pieces is
not covered by either piece's tests, and only a walk crosses it.** Both halves of Increment 3's
frontend were built in parallel against a written contract, and the contract was honoured on
both sides; the gap was in what neither side was asked to own.

---

## ADR-0030 — S4.4.1 moved to Increment 3, and the deadline that had no source

**Date:** 2026-09-14 · **Stories:** S4.4.1 · **Status:** accepted

Increment 3's third criterion is "dashboard shows the final verdict from the read model". The
story that builds the dashboard, **S4.4.1, sat in Increment 4** — so read literally the
increment could not close until the one after it did. Read loosely it was already satisfied:
`/verdicts` renders the final verdict from `GET /bids` and nothing else.

The user's decision was to take it literally and **move S4.4.1 into Increment 3** rather than
reword the criterion. Increment 4 is now 17 stories.

### The gap that only building it exposed

`bids.deadline` and `bids.buyer` have existed since 0001 and **nothing has ever written
either**. Extraction sets no `Requirement.deadline` (0 rows on the real FR run), and TED search
— which would carry both — is S1.2.1, in Increment 4. So "a deadline countdown" had no data
source at all, and the column would have rendered an em dash for the life of the increment.

The source now is the start form: the bidder has the notice in front of them. That is a smaller
claim than it sounds — S1.2.1 will replace typing with TED's own fields, and the columns it
writes are the ones already here.

### An offset, and deliberately not a zone

"A countdown **in the buyer's time zone**" cannot be served by `bids.deadline timestamptz`
alone. Postgres keeps the *instant* and returns it in whatever zone the session asks for, so
the wall clock the buyer printed is lost on the way in. A German bidder looking at a French
tender would be shown Berlin's hour for Paris's deadline.

Migration **0007** adds `deadline_utc_offset_minutes`. The offset and **never an IANA zone**:
a published notice states `09.10.2026 16:00 (UTC+02:00)` and TED's
`deadline-receipt-tender-date-lot` likewise carries an offset, so `Europe/Paris` would be an
inference — and one whose answer changes twice a year. Two constraints keep it honest: a
plausible range, and *an offset cannot exist without its deadline*, because an offset alone
would print as a time zone on a bid that has no date.

The two fields answer two different questions and the code never mixes them. **The countdown is
the distance between two instants and has no zone at all.** The **displayed** deadline is the
instant shifted by the offset and then formatted as UTC — exact for a fixed offset, independent
of the viewer, and unable to drift with a DST rule.

**A timestamp with no offset is refused, not assumed to be UTC.** `POST /bids` rejects it and
the start form blocks the submit rather than silently dropping what was typed; the form's zone
select has **no default**, because defaulting to the browser's offset is exactly how a German
bidder submits Berlin's clock for a Paris deadline and never sees it happen. A deadline is the
one field where a silent few hours is a real error rather than a tidiness one.

### Verified the only way that discriminates

The developer machine sits at UTC+02:00 and so does the French tender, so rendering "16:00"
proves nothing on its own. The stored offset was flipped to zero and the same instant printed
**14:00 (UTC)** — while the countdown stayed at 25 days, because the instant never moved.
Restored afterwards. On the real completed bid the row reads *9 Oct · 25 days / 16:00
(UTC+02:00) · Ministère de l'éducation nationale · Conditional · confirmed · 142 open items*.

### Two tiles refused

The artboard shows *Requirements checked / last 7 days* and *Go rate*. Neither was built.
`BidSummary` carries no requirement count and no history, so the first cannot be computed at
all; the second is arithmetic over a handful of decided bids rendered as a trend, which is a
number that would be quoted and should not be. A third tile, *Value*, needs a contract value
nothing carries. Saying so here is cheaper than a screen that implies data the product has not
got.

**`open_items` is counted from the matrix, not from the verdict's gaps.** A bid that has not
been scored has no gaps and still has work in it; and a reviewer who confirmed a
`partially_supported` row confirmed that it is *still unproven*, not that it is settled.

### One thing the tenant guard caught

The open-items count is a correlated subquery, and it was first written scoped by
`m.company_id = b.company_id` — correct, since the outer query pins `b` to the parameter.
`test_the_startup_query_is_the_one_deliberately_unscoped_statement` rejected it anyway, and was
right to: the rule is that every statement carries the tenant predicate **in its own text**, so
that a fragment is safe on its own terms rather than by where it happens to be spliced. The API
connects as a `BYPASSRLS` role (ADR-0009), which is the whole reason that rule is absolute.

---

## ADR-0031 — The recorded demo is dropped as a gate; the walk is not

**Date:** 2026-09-14 · **Stories:** Milestone 1 · **Status:** accepted

The user asked for the recorded end-to-end demo to stop being a requirement. Checking what it
actually was before removing it turned up three things, and together they make this a smaller
decision than it looked.

**It was never a done-when criterion.** Increment 1's criteria are `docker compose up`, a
page-cited translated requirement list from an uploaded pack, a checkpoint surviving a restart,
and the confirmed screen designs. No demo. The recording appears only in the *status* column,
as "the cadence requires a recorded end-to-end demo against Frankfurt" — and **no such cadence
is defined anywhere**: the word appears twice in the plan, both times referring to a practice
that is never stated. A gate nobody wrote down was holding a milestone shut.

**The course brief does not ask for one.** `135.md` grades problem definition, understanding of
agent concepts, technical implementation and reflection. It mentions no video, screencast or
presentation. So dropping it costs nothing at grading.

**What earned the demo its reputation was the walk, not the tape.** The Increment 2 retro's one
process recommendation — *record the demo first, not last* — was written because three defects
that session were reachable only by using the product end to end. That argument is about
walking, and the walk is now a thing that happens: ADR-0029 records one performed against
Frankfurt on 2026-09-14, which found a fourth defect of exactly the same shape. Increment 3 also
produced ADR-0026, where the walk was a *test* rather than a person and found a fifth.

So the practice survives in the form that was doing the work, and the artefact that was not
pulling its weight is gone. **Milestone 1 is now held by S3.2.1's recall gate alone.**

`docs/demo-runbook.md` is kept rather than deleted. It is the written route through the product
that found those defects, and it is where **S7.4's screenshots** come from — a user guide needs
stills, not video. Its header now says so, and it carries the warning that Frankfurt is no
longer in the clean first-run state the script used to assume.

---

## ADR-0032 — The adversarial fixtures, and the attack this pipeline already drops

**Date:** 2026-09-14 · **Stories:** S6.5 (unblocks S2.3.1, then S5.3) · **Status:** accepted

S6.5 asks for "at least three PDFs, each planting one instruction in a different form (plain
paragraph, white-on-white text, inside a table), with a manifest of page and planted text".
Building them settled four things.

**The pack is generated, not hand-placed.** `tests/fixtures/adversarial/documents.yaml` holds
the prose; `scripts/build_adversarial_pack.py` renders the PDFs and derives `manifest.yaml`
from the same source. A committed binary whose planted text nobody can grep is a fixture that
rots the first time a line wraps differently: the guard's test then greps for a string the
parser no longer produces and passes or fails for reasons unrelated to the guard. The builder
closes that by re-parsing its own bytes with **`PyMuPDFParser` — the parser the ingestion
pipeline itself uses** — and refusing to write a manifest that names a page whose text does not
carry the instruction, compared under `extract_reqs`' own normalisation. This is the same
generated-fixture shape as S6.3's demo pack (`--check`, byte-identical rebuilds, `no_new_id`).

**Each document also carries decoys, and they are half the point.** A guard measured only
against payloads has no precision, and every procurement document on earth says "der Bieter hat
… einzureichen". Each fixture therefore plants exactly one attack among legitimate imperative
sentences on the same pages, and the manifest lists both. S2.3.1 is answerable for flagging
every plant *and* leaving every decoy alone; without the second half, a rule that flags the word
"muss" would pass.

**The literal white-on-white attack cannot reach the guard, and that is measured, not assumed.**
`pymupdf4llm` drops white glyphs. `page.get_text()` returns the payload; `PyMuPDFParser` does
not — and the chunker, the embeddings and every prompt are built from the latter. The same holds
for PDF render mode 3 (invisible text) and for sub-point font sizes. So the textbook form of the
attack is already dead in this pipeline, **by accident rather than by design**, and a fixture
whose plant no guard can ever see would have quietly tested nothing at all.

Two consequences, and the second is the reason this is an ADR rather than a code comment:

1. **The attack the guard must actually catch is `covered_text`** — black glyphs painted first,
   then hidden under an opaque white rectangle. Just as invisible to a reader (a test renders the
   region and asserts every pixel is white), and fully present in what the parser reads. That is
   the `EN_Tender_Specifications_Extract.pdf` plant.
2. **The white-ink document is committed anyway, as a negative control.** It is recorded
   `reaches_the_parser: false`, and the builder asserts *both* halves — present in the raw text
   layer, absent from the parsed page. Swapping PyMuPDF for Docling, which may well keep white
   text, then fails this build and says so, instead of silently re-opening a door we are
   currently holding shut by luck. Docling is a stretch item in the plan, so this is not
   hypothetical.

The pack is therefore **four documents, not three** — the story's floor is "at least three", and
the fourth is a control rather than a fourth attack. Forms: `paragraph` (de), `table_cell` (fr),
`covered_text` (en), `white_ink` (de). Three languages, matching the golden tenders.

**Every page says it is synthetic.** These files carry working injection payloads, so a footer on
every page names this repository and the story, and `README.md` in the fixture directory says not
to feed one to a real assistant. The footer is constant across every page of every document,
plant or no plant, so it cannot become the signal a guard learns instead of the attack.

