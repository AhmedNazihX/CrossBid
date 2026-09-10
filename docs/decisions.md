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
