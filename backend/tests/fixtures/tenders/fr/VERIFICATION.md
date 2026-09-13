# S6.4 — human verification worksheet (FR)

Tender 618320-2026. 47 labels, **34 scored** (mandatory + bid_eligibility). Generated 2026-09-13.

**There is no recall report for this tender.** The live test is DE-only, so nothing scored these
labels against a real extraction. They are verified by reading, which is what S6.4 asks for.

The machine half is already enforced and is not what you are checking:
`test_golden_labels.py` re-opens every cited PDF and asserts every quote appears verbatim on its
cited page, every criterion id is a real member of the generated enum, and
`documents_scanned`/`documents_excluded` partition the pack exactly.

**The four rulings you made on DE were applied as patterns to this file.** Only one thing
matched, below. That is a real result: this key is cleaner than DE's.

---

## 1. The four banded selection criteria — 1 decision

FR-021 … FR-024, all on page 13, all of the form *"Critère n°N : … Ce critère est noté sur 3
comme suit"* with scoring bands beneath:

| | criterion | scored |
|---|---|---|
| FR-021 | Chiffre d'affaires annuel HT | out of 3 |
| FR-022 | Effectifs intervenants dans le domaine | out of 3 |
| FR-023 | Nombre de références de moins de trois ans | out of 3 |
| FR-024 | Processus ou certification qualité | out of 2 |

These are the exact analogue of the DE `Kriterienkatalog Leistung` criteria you ruled on:
**scored, not pass/fail.** Missing one costs points; it does not by itself eliminate.

recommend: **change all four to `optional`**, consistent with the DE ruling. Denominator 34 → 30.

decision: **applied 2026-09-13 — all four are now `optional`.** Denominator 34 → 30.

## 2. FR-025 stays mandatory — confirm only

> "La note finale est obtenue par la somme des critères. Elle est exprimée sur 10. Les candidats
> n'ayant pas obtenu la note de **5/10** … sont éliminés."

This is the elimination gate, exactly like the 11 DE A-Kriterien you kept mandatory: a threshold
*on* points that excludes a candidate. It stays `mandatory`.

Known limitation, recorded by the labeller: `ThresholdUnit` has no `POINTS` member and `PERCENT`
would misrepresent a 5-of-10 sum, so this label carries **no typed threshold**. The rule is in
the quote and the summary only — a scorer cannot check it numerically.

decision: **confirmed 2026-09-13.** No change; FR-025 stays `mandatory`, and its missing typed
threshold is recorded in the file header as a known limitation.

## 3. The eCertis ids are the strong part — confirm only

8 labels carry a criterion id, and **every one was read off the buyer's published
`DUME_acheteur.xml`, not inferred.** All 30 `ccv:Criterion` UUIDs in that file are members of the
generated `EcertisCriterionId` enum, which independently confirms ADR-0007. This is the opposite
of the DE situation, where the key's ids were inferred and the extractor is forbidden to produce
them.

**This is the tender to demo the cross-border wedge on.** DE will never show an eCertis card.

decision: **confirmed 2026-09-13.** No change.

## 4. Spot-check three — open the PDF at the page and confirm each is a real obligation

| Label | Page | The clause |
|---|---|---|
| FR-001 | 3 | "Les plis parvenant après la date et l'heure limites … ne seront pas admis." |
| FR-023 | 13 | "Critère n°3 : Nombre de références datées et chiffrées de moins de trois ans …" |
| FR-046 | 19 | "Les formats de signature sont XAdES, CAdES ou PAdES …" |

all three real requirements? **confirmed 2026-09-13.**

## 5. Closed

**Done 2026-09-13.** Header set to `labelled_by: llm_assisted_human_verified`,
`verified_by: Ahmed Nazih Ali`, `verified_on: 2026-09-13`. This file is closed.
