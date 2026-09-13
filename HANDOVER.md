# Handover — end of the Increment 2 session (2026-09-13, extended 2026-09-14)

Written for whoever picks this up next, including a future me with no memory of the session.
`CLAUDE.md` is still the standing brief; `docs/project-plan.md` is still the source of truth for
scope. This file only covers what changed, what it cost, and what is genuinely open.

---

## Where the project stands

**Increment 2 is code-complete.** Every story built and committed: S1.1.2, S1.4.1, S2.4.1,
S2.4.2, S3.3.1, S3.3.2, S4.5.1's matrix criterion, plus the wait-fillers S6.3, S6.4 and S3.2.3.

**3 996 tests, 100 % coverage, `make lint` clean, working tree clean.** ADR-0015 through
ADR-0023 record the decisions, and the Increment 2 retro and re-forecast close the sprint.

**Added 2026-09-14.** The DUME work landed and the cross-border wedge now runs where a person
can reach it (ADR-0022, ADR-0023): the demo company is seeded in Frankfurt, the FR pack
including `DUME_acheteur.xml` is uploaded, and a finished FR bid sits at `awaiting_review` with
**135 requirements, 30 of them from the DUME, and 30 of 30 eCertis lookups resolved**. The only
thing left for Milestone 1 besides S3.2.1 is pressing record — `docs/demo-runbook.md` is the
script.

The product runs end to end: a tender pack goes in, requirements come out cited and translated,
each is checked against the company's documents by a per-requirement ReAct loop with eCertis
equivalence where a criterion id exists, and the matrix renders read-only in the browser.

### The two milestones

| | state | what actually holds it open |
|---|---|---|
| **Milestone 1** | in progress | S3.2.1 (below) **and** a recorded end-to-end demo, which has never been made |
| **Milestone 2** | in progress | all seven stories built; closes with Milestone 1's demo |

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
  **This affects S7.4's user guide and Milestone 1's recorded demo.**
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

Three options, in the order I would take them.

1. **Record the end-to-end demo.** It is the only thing besides S3.2.1 holding Milestone 1 open,
   it needs no new code, and it doubles as the user guide's screenshots (S7.4).
   **`docs/demo-runbook.md` is the script** — the take shot by shot, the numbers to quote, and
   the three things not to do. The state it assumes is already in Frankfurt: seeded company, FR
   pack uploaded including `DUME_acheteur.xml`, and a finished FR bid at `awaiting_review`. Show
   the wedge on **FR with the DUME**; the PDFs on their own leave the card dark. The retro's one
   recommendation is to do this *first* next sprint, not last.
2. **Start Increment 3 — the review round-trip.** S3.4.1–S3.4.4, S4.5.2, S4.5.3 (**S2.4.3 is
   done** — `make seed-demo` landed early because the demo needed it): the
   verdict, the human interrupt, and the reviewer editing rows. This is the product's safety
   boundary and the last substantial work before the submission line at Milestone 5.
3. **Keep attacking recall** — only with repeated runs per configuration, and knowing the noise
   floor. The plan time-boxes this (R6) for good reason.

Carrying ~0.74 with its variance into `REPORT.md` as an honest measured figure is a more
defensible story for the grader than a number chased to 0.9.

---

## Starting Increment 3 — read this first

Increment 3 is the **review round-trip**: the verdict, the human interrupt that accepts a
reviewer's edits, and the workspace UI for making them. It is the product's safety boundary and
the last substantial work before the submission line at Milestone 5.

### The stories, and why the order is forced

`S3.4.1 → S3.4.2 → {S3.4.3, S3.4.4} → {S4.5.2, S4.5.3}`

| Story | Size | What it is | `needs` |
|---|---|---|---|
| **S3.4.1** | M | The scorer: mandatory row `unsupported` or an unmet exclusion ground → `no_go`; mandatory `partially_supported` → `conditional`; a mandatory row with no evidence is **never** `go` | S3.3.1 ✅ |
| **S3.4.2** | M | The interrupt accepts a review: rows + decision come back, the scorer re-runs on the reviewer's statuses, bid ends `done`; a second submission is **409** | S3.4.1 |
| **S3.4.3** | M | Read-model writes at scoring and at review; `GET /bids` reads only from them, with a consistency test against the checkpoint | S3.4.2 |
| **S3.4.4** | M | Resilience: unread pages listed, LLM timeout → one retry → smaller model, schema violation → one re-ask → `partially_supported`, no eCertis entry flagged, expired certificate warned with its date | S3.4.2 |
| **S4.5.2** | **L** | Reviewer edits a row's status, gives a reason, attaches a document, switches FR/DE per row; edits held locally until confirm, agent's original stays visible | S3.4.3, S4.0.1 ✅ |
| **S4.5.3** | M | Confirm or override the verdict with a reason; submitted once, final state shown | S3.4.2, S4.0.1 ✅ |

**Nothing parallelises until S3.4.1 lands** — every other story depends on it directly or
transitively. After S3.4.2, S3.4.3 and S3.4.4 are independent of each other, and so are S4.5.2
and S4.5.3 once their backend dependency is in. S4.5.2 is the only **L** in the increment.

Wait-fillers for this increment: **S6.5, S7.3**, then S7.2.

### What already exists, so you do not rebuild it

- **The graph is built for this.** `crossbid/agent/graph.py`'s module docstring already names
  `score_verdict`, `apply_review` and `finalize` as "later stories", and decision 2 explains why
  the interrupt is a **node calling `interrupt()`** rather than `interrupt_after=`: a static
  interrupt on the last node leaves `aget_state().next == ()` with no `interrupts`, which is
  indistinguishable from a finished run. The node parks with `next == ("await_review",)` and
  continues on `Command(resume=review)`, **which is exactly the mechanism S3.4.2 needs.** That
  was measured on langgraph 1.2.11 before being chosen — do not re-litigate it.
- **`_request_review` is the seam.** It currently returns `{}` and its docstring says so:
  "S3.4.2 replaces the return with the review payload `interrupt()` hands back."
- **One documented caveat you will hit:** on resume the node re-runs from its top, so the
  `awaiting_review` status write happens twice. The value is identical both times and
  `apply_review`'s stage overwrites it immediately. This is known, not a bug to chase.
- **`stage()` wraps every node** — status on entry, projection on exit, `StageError` naming the
  stage and never the document (ADR-0008). New nodes go through it; do not write the read model
  directly from a node.
- **The vocabulary is settled (ADR-0013)**, and the UI already speaks it: rows are
  `supported` / `partially_supported` / `unsupported` / `not_applicable`; verdicts are
  `go` / `conditional` / `no_go` / `insufficient_evidence`. `/verdicts` is a placeholder route
  that names its story.
- **A real parked bid is waiting for you.** Bid `7c3869f9-d285-41f5-a7d5-2b2fa5876840` (FR,
  notice 618320-2026) sits at `awaiting_review` with 135 requirements and 135 matrix rows, 30 of
  them DUME-sourced with eCertis evidence. It is the fixture for every resume path you write.

### The one process change the retro asks for

**Record the demo first, not last.** Every defect found in Increment 2 — unverified answer keys,
a wedge no run could light, a DUME no user could upload — was reachable only by walking the
product end to end, and each was found when the walkthrough was finally attempted. Increment 3's
demo is the review round-trip; walking it early is how S3.4.2's 409 and S4.5.2's local-edit
state get exercised before they are called done.

---

## Reproducing the state

```bash
make install && make lint && make test          # 3 996 tests, 100 % coverage, all offline
uv run scripts/recall.py                        # scores the committed fixtures
uv run scripts/recall.py tests/fixtures/extractions/de.live.json   # the real DE figure; exits 1
make test-live                                  # costs money; the DE bid run alone is ~$1.60
```

`VERIFICATION.md` sits beside each of the three golden keys and records what a human
adjudicated, separately from what the tests already prove.
