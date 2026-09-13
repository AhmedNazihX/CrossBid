# S6.4 — human verification worksheet (DE)

Generated 2026-09-13 from the live run of 2026-09-12
(`tests/fixtures/extractions/de.live.json`, 279 rows, $1.47) scored by
`uv run scripts/recall.py tests/fixtures/extractions/de.live.json`.

**Current figure: recall 0.77 — 168 of 219 mandatory bid-eligibility labels — against a 0.90
threshold. FAIL.**

S6.4 says labels are "produced with LLM assistance and each verified by a human". The machine
half is already enforced: `test_golden_labels.py` re-opens every cited PDF and asserts every
quote appears verbatim on its cited page, that every criterion id is a real enum member, and
that no document was skipped silently. **Nothing below is about typos or page numbers** — those
cannot be wrong. What is left is judgement.

Mark each decision inline. When all four sections are done, flip the header (last section).

---

## 1. Two arguable non-matches — 2 decisions

The matcher rejected 27 label/row pairs on the same page. 25 share under half their text and are
plainly different requirements. These two are not:

### DE-001 — recommend: ACCEPT the rejection (the label stays a miss)
```
LABEL     "Mit dem Angebot sind folgende Dokumente einzureichen: Angebotsformular"
EXTRACTED "Angebotsformular"   (same document, same page)
```
The extractor found the right place but quoted 16 characters — below the matcher's 20-character
floor. It is a real find. **But a 16-character quote is not a citation a reviewer could act on**,
which is the product's whole promise, so counting it as a hit would flatter the extractor. The
honest reading is that extraction produced an unusable citation here.

decision: ____________  (accept / overturn — overturn credits it as found)

### DE-484 — recommend: ACCEPT the rejection (genuinely different requirements)
```
LABEL     "mindestens eine Referenz für IPv6-Migrationseinzelprojekten ..."
EXTRACTED "- mindestens drei verschiedene Referenzen für IPv6-Migrationseinzelprojekten ..."
```
60% shared text, but **one reference versus three**. Different thresholds are different
requirements.

decision: ____________

---

## 2. The 16 eCertis criterion disagreements — 1 decision, not 16

Every one runs the same way: the key carries an id, the extraction carries none. **Zero of 279
extracted rows carry a criterion id, and that is correct behaviour.** `prompts/extract.md` says
the id is "null unless the section itself prints an ESPD criterion UUID — never derive one from
the wording", which is ADR-0007's rule that a wrong id is worse than none. The DE pack publishes
no DUME, so there are no ids to read.

The key's 27 ids were *inferred* — exactly what the extractor is forbidden to do. So this is one
question, not sixteen:

**Should the answer key carry criterion ids the extractor is not permitted to produce?**

- Keep them: the key records what is true, and the disagreement stands as a permanent, explained
  gap. Recall is unaffected (it does not score criterion ids).
- Drop them: the key only claims what a correct extraction could find. Loses real information.

Recommend **keep, and treat the 16 as expected rather than as defects** — the report already
lists them separately from misses.

decision: ____________

**Consequence you should know either way:** S3.3.1 looks up eCertis only when a requirement
carries a criterion id. On the DE tender none will, so **the eCertis equivalence card never
appears in a DE walkthrough**. The cross-border wedge only lights up for tenders that publish a
DUME — which the FR fixture does (30 criteria, 8 labelled). **Demo the wedge on FR, not DE.**

---

## 3. The 25 `kind` disagreements — spot-check, then accept in bulk

Golden `kind` versus extracted `kind` on matched pairs (`optional` vs `mandatory`, and so on).
These do not move recall — the denominator uses the key's own `kind` — but a wrong `kind` in the
key is still wrong. They cluster in `Vordruck_Referenzen` and `Kriterienkatalog_Leistung`.

Full list: section `DISAGREEMENTS` of the report.

decision: ____________  (accept the key's values / list the ids to change)

---

## 4. Spot-check the bulk — confidence, not exhaustion

Not every item needs an individual decision; these are the populations behind the number.

- **24 misses with no extracted row within a page** — genuine extraction failures. 13 are in
  `Leistungsbeschreibung_VV2_V1.pdf` and 7 in the notice PDF. Sample a few to confirm they are
  real requirements.
- **25 clearly-different non-matches** — sampled above; the two arguable ones are in section 1.
- **20 remaining candidates** — already adjudicated as correct rejections (restatements, a
  `Rechtsbehelfsbelehrung` that grants a right rather than imposing a duty, section headings).

sampled: ____________   looks right? ____________

---

## 5. Close it

When sections 1–4 are settled, set in **each** of `de/`, `fr/`, `en/` `golden.yaml`:

```yaml
  labelled_by: llm_assisted_human_verified
  verified_by: <your name>
  verified_on: 2026-09-__
```

`GoldenMeta._verification_is_consistent` enforces this as all-or-nothing, so a partial flip
fails the suite. That closes **S6.4**, and with it **S3.2.1** — and with the still-unrecorded
end-to-end demo, **Milestone 1**.

Note FR and EN have no live extraction yet (the live test is DE-only), so their labels are
verified by reading, not by scoring.
