# Handover — end of the Increment 2 session (2026-09-13)

Written for whoever picks this up next, including a future me with no memory of the session.
`CLAUDE.md` is still the standing brief; `docs/project-plan.md` is still the source of truth for
scope. This file only covers what changed, what it cost, and what is genuinely open.

---

## Where the project stands

**Increment 2 is code-complete.** Every story built and committed: S1.1.2, S1.4.1, S2.4.1,
S2.4.2, S3.3.1, S3.3.2, S4.5.1's matrix criterion, plus the wait-fillers S6.3, S6.4 and S3.2.3.

**3 853 tests, 100 % coverage, `make lint` clean, working tree clean.** ADR-0015 through
ADR-0021 record the decisions.

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

- **The eCertis card can only be demonstrated on the FR tender.** DE extraction carries **zero**
  criterion ids, and correctly so: the pack publishes no DUME and `prompts/extract.md` forbids
  inferring one (ADR-0007 — a wrong id is worse than none). `check_reqs` only looks up eCertis
  when an id is present, so a DE walkthrough will never show the cross-border wedge. FR's eight
  ids were read off the buyer's published `DUME_acheteur.xml`. **This affects S7.4's user guide
  and Milestone 1's recorded demo**, which both assume DE is the showcase.
- **Any scorer must filter the DE key on `stage: bid_eligibility`.** Rows deliberately sit in
  `requirements` that are `contract_performance`, so the stage filter can be scored in both
  directions (ADR-0015). `scored_labels` does this; anything new must too.
- **`next start` cannot serve this app.** `next.config` sets `output: 'standalone'` for the
  Docker image. Use `make dev-web` (`npm run dev`) locally, and `node .next/standalone/server.js`
  in production. Starting it the wrong way yields a working-looking server whose chunks 404 and
  a "client-side exception" in the browser. This cost time twice.
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
   it needs no new code, and it doubles as the user guide's screenshots (S7.4). Demo the eCertis
   wedge on **FR**.
2. **Start Increment 3 — the review round-trip.** S3.4.1–S3.4.4, S2.4.3, S4.5.2, S4.5.3: the
   verdict, the human interrupt, and the reviewer editing rows. This is the product's safety
   boundary and the last substantial work before the submission line at Milestone 5.
3. **Keep attacking recall** — only with repeated runs per configuration, and knowing the noise
   floor. The plan time-boxes this (R6) for good reason.

Carrying ~0.74 with its variance into `REPORT.md` as an honest measured figure is a more
defensible story for the grader than a number chased to 0.9.

---

## Reproducing the state

```bash
make install && make lint && make test          # 3 853 tests, 100 % coverage, all offline
uv run scripts/recall.py                        # scores the committed fixtures
uv run scripts/recall.py tests/fixtures/extractions/de.live.json   # the real DE figure; exits 1
make test-live                                  # costs money; the DE bid run alone is ~$1.60
```

`VERIFICATION.md` sits beside each of the three golden keys and records what a human
adjudicated, separately from what the tests already prove.
