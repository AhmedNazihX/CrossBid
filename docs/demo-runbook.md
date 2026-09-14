# Demo runbook — the end-to-end walkthrough

**No milestone depends on a recording any more** (ADR-0031, 2026-09-14). This file is kept
because the walk itself is worth having and the script is already written: it is the route
through the product that found four separate defects across Increments 2 and 3, and it is where
**S7.4's screenshots** come from — the user guide needs stills, not video.

Follow it as a walkthrough. If you do decide to record a take, it still works as a shot list.

**State as of 2026-09-14: NOT reset.** Frankfurt holds a completed FR bid (`618320-2026`) with
144 requirements, 144 matrix rows and three tender documents — kept deliberately after the
walkthrough of ADR-0029. The clean first-run state this file used to assume is gone, so **reset
before following the script from the top**: delete the bid (documents, requirements and matrix
rows cascade) and remove the three tender objects from Storage. The whole flow has been
performed twice against this build, so nothing below is untested; ADR-0023 and ADR-0029 record
what those runs proved.

---

## Before you press record

```bash
# 1. API on :8000 — restart it if it has been running since before the DUME work
cd backend && uv run uvicorn crossbid.main:app --port 8000

# 2. Web on :3000 — `npm run dev`, NEVER `npm start` (output: 'standalone')
cd frontend && npm run dev

# 3. Confirm the seed is in place (idempotent; a second run spends nothing)
make seed-demo
```

Then check, in the browser — this is the **clean first-run state** the take starts from:

- `/company` lists **exactly 10 documents, all Ready**, all of type _Company evidence_. No
  tender documents, no duplicates, no `Failed`.
- `/bids` shows its empty state with the "What to do next" panel.
- `/bids/new` shows "No tender documents are waiting for a bid".

If tender documents or a bid are present, a previous take was not reset. The reset is: delete
the bid (documents, requirements and matrix rows cascade from it) and remove the three tender
objects from Storage.

If any screen 401s, `frontend/.env.local` is missing — see `HANDOVER.md`. If uploads fail,
the Storage bucket is wrong — also `HANDOVER.md`. Neither is a code problem.

---

## The take

### 1. The landing page (~20 s) — `/`

Open cold so the hero reveal plays from its first frame. Do not scrub or reload mid-reveal;
it holds at 4.20 s by design and has no pause control because the window is under WCAG's five
seconds. Say what the product is: **you find out whether you can win a cross-border EU tender
before you write a word.**

### 2. The company (~30 s) — `/company`

The demo GmbH is a fictional German IT services company. Scroll the ten evidence documents:
certificates, accounts, insurance, references. Point out **Ready** — each has been read page by
page and indexed, so the agent can quote it rather than paraphrase it.

This is the half competitors do not do. Say so once: TenderWolf and the rest analyse the
tender. The evidence mapping is bidder-side.

### 3. Upload the tender (~40 s) — `/company`

This is a live upload — the table is empty of tender documents when you start. All three files
are in the repo at `backend/tests/fixtures/tenders/fr/`; have that folder open in the file
picker before you start recording, so the take is not a hunt through directories.

| File   | Path                                                      |
| ------ | --------------------------------------------------------- |
| notice | `fr/618320-2026.notice.fr.pdf`                            |
| RC     | `fr/documents/26023_AOO_Conseil_Architecure_SI_RC_v1.pdf` |
| DUME   | `fr/documents/DUME_acheteur.xml`                          |

Upload each one, choosing its type first — **the type select drives what the file picker will
accept**, so changing it after choosing a file is the one way to get a refusal on camera:

| File                                         | Type to choose          |
| -------------------------------------------- | ----------------------- |
| `618320-2026.notice.fr.pdf`                  | Tender notice           |
| `26023_AOO_Conseil_Architecure_SI_RC_v1.pdf` | Tender document         |
| `DUME_acheteur.xml`                          | **ESPD / DUME request** |

**Pause on the third.** Selecting **ESPD / DUME request** changes the file picker to XML and
the hint to "the buyer's published ESPD request (DUME)". This is the whole wedge in one control:
where a buyer publishes a DUME, the EU criteria are stated outright and nothing has to be
inferred from prose.

Each file goes `Uploaded, reading… → Read, indexing… → Ready` on its own, a few seconds each.
Wait for all three to read **Ready** before moving on — the start screen will not let you tick a
document that is not ready. Note the DUME lands on `—` in both page columns while the two PDFs
show 5 and 20: an XML form has no pages, and the product says so rather than printing a `0`.

### 4. Start the run (~20 s) — `/bids/new`

Notice number `618320-2026`, tender language **French**, tick all three documents.

Note what the checklist says under the DUME: its type and nothing else — no page count, because
an XML form has no pages. Everything in this product either cites a page or admits it has none.

Press **Start analysis**.

### 5. Watch it work (~60 s) — `/bids/{id}`

Do not cut away. The interesting part is the order things appear:

- Within seconds: **30 requirements, 24 of them exclusion grounds.** These are the DUME's, read
  structurally by a prefix table over the ESPD type codes. No model was asked, which is why they
  arrive before anything else — and why that 30 is the same every run.
- Then the counter climbs to **around 135** as the RC and the notice are extracted section by
  section. That total comes from the model, so treat it as approximate on the day and read the
  number off the screen rather than quoting this one.
- Then matrix rows fill in as each requirement is checked against the company's documents.
- It parks at **Review verdict** — `awaiting_review`. About two minutes for this 25-page pack.

Say the thing that matters: **it stops here on purpose.** The agent never submits and never
issues a verdict without a person. That is the product's safety boundary, not a missing feature.

### 6. A requirement from the tender text (~30 s)

Filter to any category and expand a row sourced from the RC. Show:

- the requirement in **German** — the bidder's language — beside the **French** original,
- the citation `26023_…RC_v1 p. 17`, which opens that page in the source panel,
- the agent's one-sentence rationale and the evidence it leaned on.

Every row either cites something or is marked partially supported. There is no third option.

### 7. The eCertis card — **the money shot** (~60 s)

Filter to **Exclusion** and expand any row whose source reads
`DUME_acheteur.xml · ESPD criterion`. **Do not go looking for a specific REQ number** — ids are
assigned by position and will differ from run to run. The DUME rows are the ones citing the XML;
on the last run they sat together partway down the Exclusion list.

Three things to point at, in this order:

1. **The citation is a label, not a link.** There is no page to open, and the product says so
   rather than offering a link that lands nowhere.
2. **The criterion came from the buyer's own file.** "Avez-vous fait l'objet d'une
   condamnation…" is the ESPD's text, carrying the EU criterion UUID.
3. **The eCertis card answers the cross-border question.** _Terrorist offences or offences
   linked to terrorist activities_ — "In Germany this criterion is evidenced by Auszug aus dem
   Bundeszentralregister / Führungszeugnis, Amtliches Verzeichnis AVPQ, …" A German bidder
   reading a French tender is told which German paper satisfies it.

Then expand **Professional risk indemnity insurance**, where the agent has gone one step
further and matched the demo company's own policy — €5 000 000 cover — against the criterion.

That is the wedge: _the tender is French, the bidder is German, and the mapping between the two
is the product._

### 8. Close (~20 s)

Return to the top of the workspace. Say what is deliberately not there yet: the reviewer
editing rows and the verdict itself are Increment 3. What is there is the promise —
**every cell carries a citation or admits it cannot.**

---

## Say these numbers, and only these

- **~135 requirements** from a 25-page French pack, **exactly 30** of them straight from the
  DUME. The 30 is deterministic; the total is not — read it off the screen.
- **30 of 30** eCertis lookups resolved.
- **~2 minutes** for this pack. The 191-page German pack takes about five.
- Recall on the German golden tender is **~0.74 ± 0.02**, against a 0.90 target. **Say this if
  extraction quality comes up.** Four identical runs scored 128–135 of 177, so the measurement
  noise is four points of recall; quoting 0.72 or 0.76 as precise would be wrong in both
  directions. It is an honest measured number and the report treats it as one.

## Do not

- Do not demo the eCertis card on the **German** tender. That pack publishes no DUME, so no
  requirement carries a criterion id and the card never appears — correctly (ADR-0007: a wrong
  id is worse than none). This advice was wrong in an earlier `HANDOVER.md`; ADR-0022 corrects it.
- Do not run `npm run build` while the dev server is up. It breaks `:3000` mid-recording.
- Do not re-encode the hero clip to make the file smaller. It decodes darker and the blend
  paints a grey rectangle across the hero (`HANDOVER.md`).
