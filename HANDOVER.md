# Handover — end of the Increment 3 backend session (2026-09-14)

Written for whoever picks this up next, including a future me with no memory of the session.
`CLAUDE.md` is still the standing brief; `docs/project-plan.md` is still the source of truth for
scope. This file only covers what changed, what it cost, and what is genuinely open.

---

## Where the project stands

**Increment 4 is complete: 17 of 17 stories, on `origin/main` at `f99d97b` (2026-09-15).**
**4 871 tests, 100 % coverage, `make lint` clean.** ADR-0032 to ADR-0059 record everything it
decided. **Check migrations first.** A probe on 2026-09-15 found 0007 applied: True, 0008 applied: False. Run `make migrate` before any live work.

What a bidder can now do, end to end: sign in with a password, a magic link, register, or reset
a password (S4.1.1, ADR-0038, ADR-0053); describe their company (S4.2.1); search TED and start a
bid from a notice, with the notice's own deadline and buyer written to the bid (S1.2.1, S3.2.2,
S4.3.1); upload a pack whose text is scanned for planted instructions before anything is
embedded, with a cheap-model second opinion on every flag (S2.3.1, S5.3, ADR-0049, ADR-0054);
ask the tender questions and get answers whose citations open the page they came from (S3.5.1,
S4.6.1, ADR-0055, ADR-0058); rate any matrix row (S4.6.3). An operator can see cost per bid and
per node, and switch models per role, tune the prompt and toggle tools from `/runs` without a
redeploy (S5.1, S5.2, S4.6.2, ADR-0050, ADR-0056, ADR-0059).

**Three things this increment found that were never built, each described by a docstring as
if it were.** `verify_configured_models` had no caller (ADR-0050). `tender_chunks` had no writer
for three increments — `tender_rag_search` searched an empty table and answered "nothing found"
to every question, well-formed and useless — while `pipeline.py` said "the graph owns its
vectors" (ADR-0057; fixed, and proven against Frankfurt: 21 passages from the real FR document).
`fetch_app_settings_row` raised `NotImplementedError` since S0.3.2 while the YAML's first line
said "overridden by the `app_settings` row" (ADR-0059). Each was found only when adjacent work
needed the missing piece. **Treat prose about a caller as a claim to `grep`, not as evidence.**

Four things a later story must not undo:

1. **Two keys open a tool** (ADR-0052). `build_enabled_tools(..., needed=, caller=)` builds
   `enabled_tools` ∩ `needed`. The operator's list may not be widened by code; a node may not be
   handed the whole toolbox by forgetting to narrow. `needed` is required, not optional.
2. **The injection guard withholds on the retrieval path and reports on the extraction path**
   (ADR-0049). The same tender PDF is withheld from `tender_chunks` *and* extracted in full; that
   asymmetry is the design. `ingestion/guarding.py` holds the rule once for both corpora.
3. **A chat citation is built from the retrieval ledger, never from the model** (ADR-0055). The
   model emits `(search, passage)` integers; a reference naming nothing is dropped and logged.
4. **The settings panel's "applied" means the next run** (ADR-0059). The runner reads a
   `SettingsProvider`; runs in flight keep the graph they started on. `confirm_flagged_chunks`
   and `available_models` are deliberately not browser-editable.

---

## Where Increment 2 left it (still true)

**Increment 2 is code-complete.** Every story built and committed: S1.1.2, S1.4.1, S2.4.1,
S2.4.2, S3.3.1, S3.3.2, S4.5.1's matrix criterion, plus the wait-fillers S6.3, S6.4 and S3.2.3.

**3 996 tests, 100 % coverage, `make lint` clean, working tree clean.** ADR-0015 through
ADR-0023 record the decisions, and the Increment 2 retro and re-forecast close the sprint.

**Added 2026-09-14.** The DUME work landed and the cross-border wedge now runs where a person
can reach it (ADR-0022, ADR-0023). A full FR run was performed against this build and proved
it: **135 requirements, 30 of them from the DUME, and 30 of 30 eCertis lookups resolved**, the
card resolving *Terrorist offences* to `Auszug aus dem Bundeszentralregister / Führungszeugnis`.

**That run was then deleted on purpose.** Frankfurt is **reset to the clean first-run state** —
the demo company and its ten evidence documents, **no tender documents and no bids** — so the
demo could be recorded as a live take rather than a narration. **That is history — the
recording was dropped as a gate (ADR-0031) and Frankfurt now holds a completed bid again.** At
the time of writing this paragraph there was no parked bid;
there is none, and that is deliberate. `docs/demo-runbook.md` is the script and describes both
the state to expect and how to reset it again after a take.

The product runs end to end: a tender pack goes in, requirements come out cited and translated,
each is checked against the company's documents by a per-requirement ReAct loop with eCertis
equivalence where a criterion id exists, and the matrix renders read-only in the browser.

### The two milestones

| | state | what actually holds it open |
|---|---|---|
| **Milestone 1** | in progress | **S3.2.1's recall, and nothing else** |
| **Milestone 2** | **closed 2026-09-14** | every criterion verified against Frankfurt, not asserted |
| **Milestone 3** | **closed 2026-09-14** | eight stories — S4.4.1 was pulled in; walked end to end |

**Milestone 2 closed on 2026-09-14** because its criteria were checked rather than assumed —
including the one nobody had ever run: a French query for information-security certification
returns `Zertifikat_ISO_IEC_27001_2022.pdf` as its top hit against the German evidence pack.

**Milestone 3 closed on 2026-09-14.** Its third criterion — "dashboard shows the final verdict
from the read model" — named a surface whose story (S4.4.1) sat in Increment 4, which would have
made the two increments circular. **S4.4.1 was pulled into Increment 3 and built**, and building
it found that nothing had ever written `bids.deadline` or `bids.buyer`: migration 0007 and the
start form's new fields are the fix. Increment 4 is therefore 17 stories, not 18.

**Milestone 1 is now held by exactly one thing: S3.2.1's recall gate, 0.72 against 0.90.**

The recorded demo was dropped as a gate on 2026-09-14 (ADR-0031). It was never one of
Increment 1's done-when criteria — it lived in the status notes as "the cadence requires" a
recording, and no such cadence is defined anywhere in the plan — and the course brief asks for
no video. What earned the demo its reputation was the *walk*, not the tape, and the walk has
been done (ADR-0029). `docs/demo-runbook.md` is kept as the walkthrough script and as the
source of S7.4's screenshots, which are stills.

The recall gate changed character on 2026-09-14 too. It used to be "not yet measured against a
verified key"; the key is verified now, so it is measured — and it fails. **Verifying the key
made the figure trustworthy, not higher.** What to do about a threshold set before anything had
been measured is an open decision, not an outstanding piece of work. The two candidate paths
are in the Increment 2 retro: amend the criterion and report 0.74 ± 0.02 honestly, or spend
time on extraction knowing the noise floor means a single $1.60 run can validate nothing.

---

## The number, and why it is the headline

**Recall on the DE golden tender is 0.72 on the committed run, against a 0.90 threshold. It
fails.** `uv run scripts/recall.py tests/fixtures/extractions/de.live.json` reproduces it and
exits 1.

**The honest figure is ~0.74 ± 0.02.** Four live runs of the same pack, same model,
`temperature: 0.0`, gave **128–135 matched labels out of 177** — a spread of 7 labels, four
points of recall. Risk **R1** ("extraction recall stays below 0.9") is no longer a risk; it is a
measurement.

Do not quote 0.72 as if it were precise, and do not quote 0.76 (an earlier run) as if the
system had got worse since. State the mean and the spread.

### What that noise floor means for anyone tuning extraction

**A single live run cannot validate a change.** Each costs about $1.60 and four minutes, and the
noise is larger than any effect one prompt edit produces. Either run each configuration several
times, or use the **section probe** — the technique that actually found every defect this
session:

```python
# isolates ONE section against the real model for pennies, not $1.60
node = build_extract_reqs(get_settings())
result = await node._extract_section(section, bid_id="probe", language="de")
```

Build the `DocumentSection` from `PyMuPDFParser().parse(path.read_bytes(), document_id=name)`
and slice `parsed.pages` to the page range. It answers "does this section extract at all",
which is the question that mattered.

---

## What happened this session, in the order it mattered

1. **Increment 2's seven stories**, several built in parallel by subagents. ADR-0015 to ADR-0018.
2. **The landing hero got a logo reveal** — many rounds on it, now settled (see below).
3. **The first real recall measurement**: 0.75, which exposed that the *answer key*, not the
   extractor, was the bigger problem — 173 clauses the extractor found had no label at all.
4. **The answer key was completed and then verified by a human** (S6.4 closed, ADR-0020). The
   key went 162 → 346 entries; the scored denominator settled at 177.
5. **Three real extraction defects found and fixed** (ADR-0021), with no improvement in the
   headline — see below.

---

## The three extraction defects, all fixed, none of them visible in the score

Kept on their own direct evidence, not on the headline. Reverting them to recover a better
number would be optimising a noisy metric over a system known to be wrong.

1. **`max_tokens: 4096` silently lost whole sections.** A dense section returns one structured
   object holding every requirement it found; exceeding the cap raises
   `LengthFinishReasonError`, which `_attempt` records as a bare `model_error` and re-asks once
   into the same wall. Six to twelve pages vanished with nothing in the output saying why. Now
   **16384**.
2. **The verbatim check rejected honest quotes.** `pymupdf4llm` writes `<br>` where a table cell
   wraps; the model writes a space. Seven rows quoting the buyer exactly were thrown away.
   `_normalised` now strips parser tags — `<br>` → a space, `<sup>` → nothing. **Reversing
   either re-breaks it** and both directions are pinned by tests.
3. **The statement of work was read as background.** `prompts/extract.md` warns hard against
   marking delivery duties `bid_eligibility`, so a `Leistungsbeschreibung` returned empty lists
   — while its pages 9–12 carry seventeen personnel qualification minimums, which are selection
   criteria wherever printed. The prompt now names that case.

**Next defect in that queue:** `Erklaerung_zur_sozialen_Nachhaltigkeit` pages 9–12 now produce
16 `no_verbatim_quote` rejections where they previously produced a `model_error` and nothing.
That section is no longer silently lost — its quote fidelity is the next thing to look at, not a
regression.

---

## Facts that will bite you if you do not know them

- **The eCertis card needs the FR tender's `DUME_acheteur.xml` uploaded — the PDFs alone will
  not do it.** DE extraction carries **zero** criterion ids, and correctly so: the pack publishes
  no DUME and `prompts/extract.md` forbids inferring one (ADR-0007 — a wrong id is worse than
  none). `check_reqs` only looks up eCertis when an id is present, so a DE walkthrough never
  shows the cross-border wedge.

  **Corrected 2026-09-14 (ADR-0022):** an earlier version of this file, and ADR-0020, said
  "demo the wedge on FR" full stop. That was wrong and would have produced a dark card on
  camera. Scanning all 38 fixture PDFs across DE, FR and EN found **zero** real ESPD criterion
  UUIDs — FR's RC prints none, and the notice's two are TED internal identifiers, not criteria.
  The eight FR ids were read by a human straight off `DUME_acheteur.xml`, a file the product
  could not ingest at all until the DUME work landed. So the demo step is: upload
  `DUME_acheteur.xml` as `tender_espd_request` **alongside** the FR PDFs, then run the bid.
  **This affects S7.4's user guide**, whose screenshots come from the same walk.
- **Any scorer must filter the DE key on `stage: bid_eligibility`.** Rows deliberately sit in
  `requirements` that are `contract_performance`, so the stage filter can be scored in both
  directions (ADR-0015). `scored_labels` does this; anything new must too.
- **`next start` cannot serve this app.** `next.config` sets `output: 'standalone'` for the
  Docker image. Use `make dev-web` (`npm run dev`) locally, and `node .next/standalone/server.js`
  in production. Starting it the wrong way yields a working-looking server whose chunks 404 and
  a "client-side exception" in the browser. This cost time twice.
- **`npm run build` while `next dev` is running breaks :3000 the same way.** The build overwrites
  the `.next` the dev server is serving from, so the HTML still renders and every
  `_next/static/*` chunk 404s — identical symptom, different cause, and the one that actually
  happened the third time. Restart the dev server after any build.
- **`SUPABASE_STORAGE_BUCKET` must be set, and the Frankfurt bucket is `company-docs`.** The
  root `.env` carried no such line, so the app used the code default `company-documents`, which
  does not exist in the project — every upload failed `404 Bucket not found`. `storage.py`
  deliberately suppresses Storage's own message (nothing about the bucket leaves the server), so
  the only symptom is "The file could not be stored. Please upload it again." on all ten seeded
  documents. If uploads fail wholesale, list the buckets before debugging the code. Note
  `infra/.env.example` still says `company-documents` — it is an example, not this project.
- **The host needs `frontend/.env.local`.** Next reads `.env*` from `frontend/` only, so the
  root `.env`'s `NEXT_PUBLIC_DEV_COMPANY_ID` never reaches `npm run dev`; the app then sends no
  `X-Dev-Company` header and every API-backed screen 401s. Only `make dev` (Compose) was ever
  wired, via a build arg. Untracked and not secret — both `NEXT_PUBLIC_*` values are inlined
  into the client bundle by design. `make seed-dev` prints the line.
- **The pinned denominator is a feature.** `test_recall_script.py` fails whenever the scored set
  changes. That is deliberate: it forces a change to the answer key to be a recorded decision
  rather than a drift. Update the constant *with its reason*, do not delete the test.
- **`de.live.json` is a real, red measurement and is committed on purpose.**
  `test_recall_script.py` pins it to exit non-zero. When extraction finally passes, that test
  fails and is the reminder to record it in an ADR.

---

## The landing hero clip, settled — do not re-derive it

Every constant in `frontend/components/landing/brand-reveal.tsx` was measured frame by frame,
and the docstrings say why. In short: it holds at **4.20 s**, where the reveal finishes and
before the rings start moving; it plays at natural speed because that window is 2.94 s, which is
inside WCAG 2.2.2's five seconds and therefore needs **no pause control**; the served file is a
lossless `ffmpeg -t 4.24 -c copy` cut of the canvas master, 2.43 MB → 0.48 MB.

**Do not re-encode it.** A CRF 18 re-encode is indistinguishable in stills but decodes with a
ground of 231 against the master's 250 — Chrome ignores the range tag — and under the `multiply`
blend that paints a visibly darker rectangle across the hero.

---

## What to do next

**Increments 0–4 are closed. Milestone 1 is still held by S3.2.1's recall gate alone**
(ADR-0031): measured ~0.74 ± 0.02 against a 0.90 threshold set before anything was measured.
Carrying the honest figure with its variance into `REPORT.md` remains the more defensible story
than a number chased to 0.9 — decide that when S7.1 writes the report, not before.

For Increment 5, jump to *Starting Increment 5*. **Do one thing before S7.1:** re-record the
live bid baseline. `parse_docs` now embeds every tender document (ADR-0057), S5.2 now writes
`llm_usage`, and S5.3 now reviews flagged chunks — none of which the last recorded run
(2026-09-13: **$1.74, 243 s**, `de.live.json`; the 2026-09-11 figure was $1.38 / 290 s) ever
exercised. `REPORT.md` will quote cost and duration, so measure them on the code that ships.

---

## Increment 3, as it was finished (history)

The backend is done. What is left is `S4.5.2` and `S4.5.3`, which are independent of each
other, and then walking the round trip in a browser.

| Story | Size | What it is | state |
|---|---|---|---|
| **S3.4.1** | M | The rules-only scorer, explained in the bidder's language and tone | ✅ ADR-0024 |
| **S3.4.2** | M | The interrupt accepts a review; the scorer re-runs; a second submission is 409 | ✅ ADR-0025 |
| **S3.4.3** | M | Read-model writes at scoring and review, with a consistency test | ✅ ADR-0026 |
| **S3.4.4** | M | Resilience, and the two reviewer notices | ✅ ADR-0027 |
| **S4.5.2** | **L** | Reviewer edits a row's status, gives a reason, attaches a document, switches FR/DE per row; edits held locally until confirm, agent's original stays visible | in progress |
| **S4.5.3** | M | Confirm or override the verdict with a reason; submitted once, final state shown | in progress |

Wait-fillers for this increment: **S6.5, S7.3**, then S7.2.

### What the frontend has to work against

- **`POST /bids/{id}/review`** takes a `ReviewSubmission` and answers the finished
  `BidResponse` — **synchronously**, because nothing past the interrupt calls a model. There is
  no polling after a review. `frontend/lib/bids.ts` already exports `submitReview` and the
  types.
- **409** means the bid is not parked at `awaiting_review`, and it cannot distinguish "already
  reviewed" from "still running" — the claim is one conditional `UPDATE`. Do not offer a retry
  that will also 409; show the current state.
- **422** names a row the matrix does not have, a status the row cannot legally take (a
  `supported` row needs an evidence quote or an attachment), or a decision differing from the
  agent's with no `override_reason`. All three are checked *before* the graph is resumed, so a
  rejected review leaves the bid exactly where it was.
- `BidResponse.verdict` is the **agent's advisory** verdict while parked, and the **re-scored**
  one afterwards. The reviewer's own decision is not in it — it is on the dashboard's
  `BidSummary.decision`. Two answers to two questions (ADR-0025).

### You will need a parked bid to work against

There is none right now, and that is deliberate — Frankfurt is reset for a live demo take.
Recreate one in about three minutes: upload the three files in
`backend/tests/fixtures/tenders/fr/` as *Tender notice*, *Tender document* and *ESPD / DUME
request*, then start a bid on notice `618320-2026` in French. It parks at `awaiting_review`
with ~135 requirements, 30 of them DUME-sourced with eCertis evidence. **Delete it again
afterwards** if the demo has still not been recorded.

### The one process change the retro asks for

**Record the demo first, not last.** Every defect found in Increment 2 — unverified answer
keys, a wedge no run could light, a DUME no user could upload — was reachable only by walking
the product end to end. Increment 3 has now produced a fourth of exactly that shape: S3.4.2's
reviewer edits reached `complete` without ever reaching the database, and only writing
S3.4.3's consistency test found it. The walk is what finds these; a test that walks is the
cheap version of it.

---

## Increment 4, as it was finished (history)

*Kept as written for Increment 4's start; everything below it landed. How it went: 17 stories in
two calendar days with parallel subagents on mutually independent stories, integrated by one
session that regenerated `api.ts`, wrote the ADRs and split shared files per commit. One red CI
(`60367fa`): an enum member added after the client was regenerated — see the traps under
Increment 5. Three "the docstring says it happens" gaps found and closed (see the top).*


**Increment 4 is 17 stories, not the plan's original 18**: S4.4.1 moved into Increment 3
(ADR-0030). Every dependency is satisfied except one chain, and the two external services were
probed on 2026-09-14 before this was written.

### The order, and why

| # | Story | Size | Why here |
|---|---|---|---|
| 1 | **S6.5** | S | Three adversarial PDFs with planted instructions. **No dependencies, and it is the only thing blocking anything** — S2.3.1 needs it and S5.3 needs S2.3.1. One small story unblocks two. It was an Increment 3 wait-filler that never got picked up. |
| 2 | **S0.3.1** | M | Magic-link sign-in, backend half. The longest chain in the increment starts here, so it starts first. `SUPABASE_ANON_KEY` and `DEVELOPER_EMAILS` are **already in `.env`** — `settings.py` has no fields for them and `auth.py` still answers 501 for `AUTH_MODE=supabase`, which is exactly this story's work. |
| 3 | **S4.1.1 → S4.2.1, S4.3.1** | M each | The frontend of sign-in, then the company form and the TED-search start step. S4.2.1 and S4.3.1 are independent of each other once S4.1.1 lands. |
| 4 | **S2.3.1 → S5.3** | M, S | The injection guard, unblocked by step 1. |
| — | **S1.2.1 → S1.2.2, S3.2.2** | M, S, S | TED search. Independent of everything above; can run in parallel from day one. See the warning below. |
| — | **S1.3.1, S2.3.3, S4.6.3** | S each | No dependencies at all. Good filler whenever something upstream is in flight. |
| — | **S5.1** | M | Needs S1.4.1 ✅ (Increment 2). Independent. |
| — | **S5.2 → S4.6.2** | M, M | Cost per node, then the model picker. `S5.2` needs S0.3.2 ✅. |
| — | **S3.5.1 → S4.6.1** | M, M | "Ask the tender". Needs S2.4.2 ✅ and S3.4.3 ✅ — both landed in Increment 3. |

Wait-filler for the increment: **S7.2**.

### What S1.2.1 will actually get from TED

Re-probed live on 2026-09-14; the full findings are in `CLAUDE.md`'s verified-facts section.
The one that changes the story's shape:

**TED's `deadline-receipt-tender-date-lot` is a list, one entry per lot, carrying a DATE with a
UTC offset and no time of day** — zero of 58 sampled lot deadlines had an hour. So TED can fill
`bids.deadline_utc_offset_minutes` (migration 0007) and the date, but **never the hour**. The
start form's date-and-time input is therefore *richer* than TED, not redundant with it: S1.2.1
should fill what it has and leave the hour to the bidder rather than overwrite it with midnight.

Also: a CPV value must be the full eight digits (`IN (72)` is a 400), sorting goes inside the
query string rather than beside it, `buyer-name` is a language-keyed dict rather than a string,
and the deadline fill rate is **84 % among `cn-standard` contract notices** but only 44 % across
a mixed sample, because award notices have no deadline by nature.

### The CI was red for three days and the code was never the reason

Fixed on 2026-09-14. Every push from 2026-09-11 reported a failed run while **every real check
was green** — backend, frontend, `dependencies.txt`, `api.ts` all passed. The `generated files
are current` job backgrounds the API to regenerate `api.ts` and nothing ever stopped it;
`astral-sh/setup-uv`'s post-job `Pruning cache...` then blocked on what the live interpreter
held and was killed after exactly five minutes with `exit code 2`, after which the runner logged
`Terminate orphan process: pid (uv)` and `pid (uvicorn)` and named the cause itself. A
`Stop the API` step with `if: always()` is the fix; it also takes about five minutes off the run.

**Still outstanding, and a warning rather than a failure today:** `actions/checkout@v4`,
`setup-node@v4`, `setup-python@v5` and `astral-sh/setup-uv@v5` all target Node 20, which is
deprecated and is being forced onto Node 24. That becomes a hard failure when the runners drop
the shim. Bumping them is a separate change and was deliberately not bundled with the fix above.

---

## Starting Increment 5 — read this first

**Increment 5 is the submission line (Milestone 5): evidence for the grader.** Five stories plus
one left over — none of them changes the product, all of them prove it. The plan's rows: S7.1,
S7.7, S7.4, S7.5, S7.6, with S7.2 (an ADR per decision) continuous. **S7.3, the architecture
document, was Increment 3's wait-filler and was never picked up** — `docs/` has no
`architecture.md`, and the increment table names "architecture doc" as submission evidence, so
it belongs here.

### The order, and why

| # | Story | Size | Why here |
|---|---|---|---|
| 0 | **Re-record the live baseline** | — | See *What to do next*. One deliberate `make test-live` run on the shipping code, before any number is quoted. |
| 1 | **S7.1** DeepEval suite + `REPORT.md` | M | The critical path (2 days in the Gantt). Recall, citation faithfulness, translation adequacy on the three golden tenders; judge from a different vendor. **Most of it exists**: `crossbid/eval/{matching,recall,report}.py` and `scripts/recall.py` are S3.2.3's matcher and recall — the plan says S7.1 *reuses* them, not reimplements. `make eval` already expects `backend/scripts/run_eval.py` and fails with a clear message until it exists. |
| 2 | **S7.3** `docs/architecture.md` | M | Outer graph, the `check_reqs` fan-out, one paragraph naming what is a deterministic workflow and what is agentic (CLAUDE.md's conventions say how to describe it). Independent; can run alongside S7.1. |
| 3 | **S7.7** Playwright smoke | M | Sign in → start a bid on the DE fixture → wait for `awaiting_review` → confirm → assert the verdict on the dashboard. Depends on the E4 Must stories, all landed. |
| 4 | **S7.4** user guide | M | Three walkthroughs — German domestic, French cross-border, a no-go — with screenshots. `docs/demo-runbook.md` is the shot list and says where its stills come from. |
| 5 | **S7.5** `docs/critique.md`, **S7.6** README / `project.md` / CLAUDE.md | S, S | Last, because the critique should see the finished thing and the README should describe it. |

### What each story will actually find

**S7.1.** DeepEval is named in the plan's tech stack (line 32) and so pre-approved — but it is
**not installed**: `pyproject.toml` has no `deepeval`. Adding it is a dependency change, so
`make deps` afterwards (CLAUDE.md). The judge is `anthropic/claude-haiku-4.5` through OpenRouter
via DeepEval's OpenAI-compatible custom model; `claude-sonnet-5` 404s on this account (ADR-0005).
The extraction results to score are already saved: `backend/tests/fixtures/extractions/{de,de.live,en,fr}.json`
— `de.live.json` is a real run (`source: live_run`, 2026-09-13); **read each file's `source`
field before quoting it**, the others may be SP.1-derived. The golden keys live at
`backend/tests/fixtures/tenders/{de,fr,en}/golden.yaml` with a `VERIFICATION.md` beside each,
**not** at the plan's `evaluations/golden/` path — do not move them; write `REPORT.md` where
`make eval` writes it and let the plan's tree be the thing that is wrong. Faithfulness and
translation are the two metrics with no code yet; recall is done.

**S7.7.** Playwright is in the plan (pre-approved) and **not installed** — no dependency, no
config, no `e2e/` directory. `make deps` after adding it. Two decisions the story forces:
*how it signs in* — password sign-in needs no email (ADR-0038; the built-in mailer allows two
messages an hour and there is no email `test_otp`, R7), and `AUTH_MODE=dev` with `X-Dev-Company`
is the fully offline route; and *whether it runs the real graph* — "waits for `awaiting_review`"
on the DE pack is a real bid, ~4 minutes and ~$1.74 per test run, so decide whether the smoke
test spends that or runs against a seeded parked bid. The seed scripts are
`scripts/seed_demo_company.py` and `scripts/seed_dev_company.py`.

**S7.4.** Frankfurt currently holds the demo company (owned by your live account since
2026-09-14 — it had been orphaned by a deleted user) with ten evidence documents, and one
**completed FR bid `618320-2026`** (144 requirements). The runbook says reset before following
it from the top; for a no-go walkthrough you will need a bid that fails, which nothing in the
fixtures produces by default.

**S7.5.** Ask a model that is not the extraction model — the judge, or `google/gemini-2.5-flash`.
Feed it the accepted risks so it can agree or disagree with them on the record: user enumeration
via `signInWithOtp` (ADR-0053, supabase/auth#1955, no toggle exists); no route reads the chat
thread back, so a reload loses the visible log while the agent remembers (ADR-0058);
last-write-wins on the `app_settings` row (ADR-0059); on the phone, a citation tap drops focus
to `body` (inherited from S4.5.1); the frontend has **no test runner** — every screen this
increment is typecheck/lint-verified only.

**S7.6.** The README's *Status* says "Increment 1 of 7"; CLAUDE.md's *State of the repo* says
the same and its command table still says `make eval` is not built. Both are false and both are
what a grader reads first. `project.md` is to be trimmed to what was built.

### Traps that cost time this increment, so they do not cost it again

- **`api.ts` goes stale the moment a response model's enum changes.** `60367fa` added
  `INDEXING_FAILED` after the client had been regenerated; CI's generated-files job caught it.
  Regenerate after the **last** schema-touching change, and `git diff HEAD -- frontend/lib/api.ts`
  before every push. Never regenerate from a working tree with agents mid-edit: `git archive` the
  commit or use a worktree, and boot with CI's two placeholders
  (`OPENROUTER_API_KEY=ci-placeholder-not-a-real-key`, `APP_ENCRYPTION_KEY=` same) — the schema
  does not depend on their values, only on their presence.
- **Never run `npm run build` while `next dev` serves this project, and never delete `.next`
  under a running server** — stop it first. Both were done this increment; the second turned
  every page into a downloaded "Internal Server Error" (a 500 with no `Content-Type` under our
  own `nosniff`). `NEXT_DIST_DIR=.next-verify npm run build` is the safe verification build.
- **`uvicorn --reload` can wedge with the socket bound and nothing answering.**
  `curl -sm5 -o /dev/null -w "%{http_code}" localhost:8000/health` → `000` means wedged, not
  free; Ctrl+C will not clear it (the lifespan never finished); `pkill -9 -f "uvicorn crossbid.main:app"`.
  Errno 48 on restart is the same thing. Twice this increment; root cause not pinned — the last
  line your terminal prints before it goes quiet is the evidence that was missing.
- **`insert_tender_chunks` is dead and flagged** in its docstring; `replace_tender_chunks` is
  the writer. A deletion candidate, deliberately not removed in the fix commit.
- **The backend is 100 % covered; the frontend is 0 % tested.** Nothing frontend-side runs in
  CI beyond `tsc`, `eslint`, `prettier` and `next build`. S7.7 is the first browser test the
  repository will have.

Wait-filler for the increment: **S7.2** — every ADR through 0059 is written; keep it that way.

---

## Reproducing the state

```bash
make install && make lint && make test          # 4 871 tests, 100 % coverage, all offline
make migrate                                    # 0008 is the newest in the repo; run this — the 2026-09-15 probe found it NOT applied to Frankfurt
uv run scripts/recall.py                        # scores the committed fixtures
uv run scripts/recall.py tests/fixtures/extractions/de.live.json   # the real DE figure; exits 1
make test-live                                  # costs money; the DE bid run alone was $1.74 on 2026-09-13, and will change (ADR-0057)
```

`VERIFICATION.md` sits beside each of the three golden keys and records what a human
adjudicated, separately from what the tests already prove.
