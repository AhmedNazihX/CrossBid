# Critique — an outside model on Crossbid

**S7.5.** A model that did not write this system was asked what is wrong with it, on three
axes: prompt engineering, security, and usability. Every finding below was then **checked
against the code before it was believed**, and each one is either fixed or declined with the
evidence for declining it.

| | |
|---|---|
| **Critic** | `google/gemini-2.5-flash` |
| **Run** | 2026-09-16, `uv run python scripts/run_critique.py` |
| **Raw output** | [`critique.raw.json`](critique.raw.json), unedited |
| **Findings** | 5, plus 1 disagreement with an accepted risk |
| **Outcome** | 2 accepted and fixed (both in `1eafa50`) · 3 declined · 1 disagreement recorded |

**Why the critic is not an OpenAI model.** Extraction, checking and chat all run on OpenAI
slugs through OpenRouter, so a critic from the same family is not an outside opinion — the
same rule S7.1 applies to the eval judge.

**What it was shown, and therefore what it can speak to.** The three agent prompts verbatim,
the security surfaces (the untrusted-data block wrapper, the injection heuristics, the guard
that decides what is withheld, authentication, rate limits), and the user guide. It did **not**
see the running UI. Its usability findings are about copy, flow and what the guide has to
explain — which is where usability problems surface in writing — and say nothing about layout,
contrast or interaction. Those are covered by the Playwright journeys and the design canvas
instead.

**It was given the accepted risks up front**, so it could disagree with them on the record
rather than rediscover them. It disagreed with one.

---

## Accepted and fixed

### F4 · HIGH · usability — "Ready" implies a document is fully searchable, and it may not be

> *"The user guide states: 'Wait for each to read **Ready**…' This implies that 'Ready' means
> the document is fully processed and available for RAG. However … documents can be flagged
> for injection and withheld from the RAG corpus."*

**Verified and correct.** `ingestion/pipeline.py:401-405` either returns the record
unchanged or records `flagged_chunks` on it — neither path fails the document, so a flagged
upload still reaches `ready`. The read model already knew this
mattered and says so in its own field docstring: *"a document whose text was partly kept out of
the corpus is something a reviewer has to be told about, because it changes what 'no evidence
found' means for it."* The guide was the one place a bidder would read about `Ready`, and it
said the opposite.

The sharp edge is not the withholding — that is ADR-0049's design and it is right. It is that
**"no evidence found" means two different things** depending on whether anything was withheld,
and nothing told the bidder which they were looking at.

**Fixed in [`1eafa50`](../../commit/1eafa50)** (`docs/user-guide.md`) — the evidence-pack section
now states that a document can be Ready with passages withheld, what that does to a "not found" result, and what to check when a
document you know proves something comes back as not proving it.

**What is still open, and is a product debt rather than a doc one:** the per-document flagged
count reaches the API (`flagged_chunk_count`, "for a badge") and **no screen renders it**. The
guide can now tell a bidder the situation exists; the app still cannot tell them it has
happened to *this* document. Recorded in `HANDOVER.md`; not fixed here because it is a UI
change, not an Increment 5 one.

### F5 · MEDIUM · usability — the guide does not say why the DUME matters

> *"the user guide does not explain to the user why this field is important or how it impacts
> the cross-border functionality."*

**Partly correct.** The guide already told a bidder to upload the DUME and that without it "the
cross-border evidence mapping stays dark", but it never said what the mapping is keyed on, nor
what happens to the rest of the bid without one — leaving a reader who skipped the upload
unsure whether they had broken something.

**Fixed in [`1eafa50`](../../commit/1eafa50)** (`docs/user-guide.md`): the criterion id is named as
the thing the evidence lookup is keyed on, the refusal to infer one is explained as a choice (a wrong id maps you to the wrong
national document, which is worse than none), and it now says plainly that without a DUME
everything else still works.

---

## Declined

### F1 · HIGH · prompt engineering — "conflicting instructions on `stage`"

> *"the general rule is `contract_performance` … however it immediately follows with an
> exception for 'statement of work' documents."*

**Declined: the prompt resolves this, in the sentence after the passage quoted.**
`prompts/extract.md` ends that section with:

> *"The test still holds and settles it: a company that never won the contract would still have
> had to* have *those staff to be allowed to bid."*

There is no conflict. Staff qualifications a bidder must already hold are a precondition for
bidding, so the "never won the contract" test returns `bid_eligibility` for them, exactly as it
does for every other selection criterion. The critic stopped reading one sentence early.

**The kernel worth keeping:** a reader — and therefore a model — got 25 lines into that section
and missed the resolution. Moving the resolving sentence above the worked example would read
better. It was **not** done, and the reason is measurement, not laziness: that passage was added
on direct evidence (ADR-0021 — pages 9–12 of a real `Leistungsbeschreibung` carry seventeen
personnel minimums that a run without it returned nothing for), extraction recall has a noise
floor of about four points across runs, and a single $1.68 run cannot tell a prompt improvement
from noise. Reordering measured prompt text on an unmeasured hunch is how a repository loses a
result it already paid for.

### F2 · MEDIUM · prompt engineering — "ambiguous instruction when the tool budget is spent"

> *"it's unclear whether it should default to `partially_supported` …"*

**Declined: it is stated, in the section immediately below the one quoted.** `prompts/check.md`
defines the status:

> *"`partially_supported` — the honest answer whenever the documents do not settle it: **nothing
> was found**, what was found is close but not conclusive, it has expired …"*

"Budget spent, nothing conclusive" is "nothing was found", which the prompt names explicitly.
The instruction the critic quoted — *"not a reason to guess, and not a reason to call the
requirement unmet either"* — is what rules out the two wrong answers (`supported` and
`unsupported`); the status list supplies the right one.

### F3 · HIGH · security — "information leakage in the injection excerpt"

> *"If the `excerpt` is logged or displayed to a user without further sanitization, a
> sophisticated attacker could craft a tender document …"* with a suggested fix of HTML entity
> encoding.

**Declined: the excerpt never reaches a user.** Traced every consumer:

- `ingestion/pipeline.py:399,440`, `ingestion/tender_index.py:124`, `injection_review.py:166` —
  all **log lines**, server-side.
- The only injection result that crosses the API is `DocumentResponse.flagged_chunks`, typed
  `list[int]` (`routers/documents.py:176`). **Chunk indices. No text.**

So there is no HTML sink to encode for, and the suggested fix would protect a path that does
not exist. The finding names a real *class* of bug and the wrong instance of it.

**What is true and worth stating:** attacker-controlled text does reach the server log, and
that is deliberate — a maintainer looking at a false positive needs to see what matched. It is
bounded rather than unbounded: `EXCERPT_CONTEXT` is 60 characters either side of the match, and
`_around` collapses all whitespace, so a planted payload cannot forge log lines with newlines
or run to an unbounded length. That is the mitigation the finding was reaching for, and it was
already there.

---

## Disagreement with an accepted risk

### ADR-0058 — the chat log is lost on reload

> *"the user losing visibility of the conversation is a significant usability issue that can
> lead to frustration, repeated questions, or a lack of trust in the system's memory."*

**Agreed in substance, and still deferred.** The critic is right that the asymmetry is the
problem: the agent remembers the thread and the bidder does not, so a reload makes the product
look as though it forgot, and the bidder's natural response — ask it again — spends money to be
told something they were already told.

It stays deferred because closing it properly means a route that reads the thread back, which
is a persistence change in Increment 5, the increment that is explicitly about evidence rather
than product. The critic's own cheaper suggestion — keep the visible log in browser storage —
was considered and is **not** the fix: it would put a second, per-browser copy of the
conversation beside the authoritative one on the thread, and the two would disagree the first
time anything went wrong.

Recorded here so the next person inherits the argument rather than the conclusion.

---

## What this critique did not cover

Stated so nobody reads the table above as a clean bill of health:

- **The running UI.** No layout, contrast, focus-order or keyboard finding is in scope; the
  critic saw prose, not pixels.
- **Most of the codebase.** Nine files and one document went in, chosen for the three axes.
- **The graph and the read model.** Neither the LangGraph wiring nor the SQL was reviewed here;
  the 2026-09-15 audit covered those, and `tests/integration/test_read_model_round_trip.py`
  executes the statements against a real Postgres.
- **One critic, one run.** A second model would find a different set. This is evidence that the
  obvious gaps were looked for, not proof that none remain.
