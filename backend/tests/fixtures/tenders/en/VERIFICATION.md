# S6.4 — human verification worksheet (EN)

EASA tender 606362-2026. 48 labels, **40 scored** (mandatory + bid_eligibility). Generated
2026-09-13.

**There is no recall report for this tender.** The live test is DE-only, so nothing scored these
labels against a real extraction. They are verified by reading, which is what S6.4 asks for.

The machine half is already enforced and is not what you are checking:
`test_golden_labels.py` re-opens every cited PDF and asserts every quote appears verbatim on its
cited page, every criterion id is a real member of the generated enum, and
`documents_scanned`/`documents_excluded` partition the pack exactly.

**The four rulings you made on DE were applied as patterns.** One matched, and it needs a
different answer from the DE one — see §1.

---

## 1. EN-017, the exclusion-ground umbrella — 1 decision, and it is not the DE answer

> "The objective of the exclusion criteria is to assess whether the tenderer is in any of the
> exclusion situations listed in Article 138(1) of the Financial Regulation."

By the DE §4 ruling this quote is **narration** — it describes what the criteria are *for*
rather than stating a duty, so it would become `informational`.

**Recommend keeping it `mandatory` anyway**, because the situation is not the DE one. In DE the
bidder's actual duty was labelled separately (the Eigenerklärung), so dropping the statute lost
nothing. Here it is the opposite: **the nine lettered situations of Art. 138(1) and five further
declarations live in `Annex_2_*.docx`**, and the repo's parser is PDF-only, so none of them can
be page-anchored or labelled. EN-017 is the only representation in the key of **14 real
requirements**. Making it informational would leave this tender claiming *no* exclusion
requirements at all, which is false.

I looked for a better sentence on page 17 that states the duty rather than the objective; there
is none in the PDF.

decision: **keep mandatory — confirmed 2026-09-13.** No change. The reasoning, and why it is the
opposite of the DE answer, is recorded in the file header.

## 2. No eCertis ids, deliberately — confirm only

Zero labels carry a criterion id, and that is correct: EASA procures under Art. 138 of the
Financial Regulation, and Tender Specifications p.18 fn.12 says the ESPD may not be used here.
This fixture is the control case for "degrade honestly rather than invent an equivalence".

decision: **confirmed 2026-09-13.** No change.

## 3. The structural gap you should record, not fix

Per-ground EN exclusion recall is **not scorable** while the parser is PDF-only. Options, none
of them this story's job: add a `.docx` reader (S2.1.2 is the Docling stretch story), label the
annexes without page anchors (breaks the verbatim guarantee the whole key rests on), or accept
the umbrella row and say so in `REPORT.md`.

recommend: **accept and record.** It is one tender's exclusion grounds, and the DE fixture
covers exclusion grounds thoroughly (52 labels).

decision: **accepted and recorded 2026-09-13.** Written into the file header as a known
limitation; no label changed.

## 4. Spot-check three — open the PDF at the page and confirm each is a real obligation

| Label | Document | Page | The clause |
|---|---|---|---|
| EN-001 | `Invitation_to_tender_V1.pdf` | 1 | "Tenders must be submitted exclusively via the electronic submission system (eSubmission) …" |
| EN-026 | `Tender_Specifications_V1.pdf` | 20 | "All of the above-specified evidence of economic and financial capacity must be provided with the tender." |
| EN-046 | `Annex_9_Simulation_exercise_V1.pdf` | 1 | "The proposed mock-ups shall demonstrate, at a minimum, the following core functionalities:" |

all three real requirements? **confirmed 2026-09-13.**

## 5. Closed

**Done 2026-09-13.** Header set to `labelled_by: llm_assisted_human_verified`,
`verified_by: Ahmed Nazih Ali`, `verified_on: 2026-09-13`. This file is closed — and with DE and
FR, **S6.4 is closed outright**.
