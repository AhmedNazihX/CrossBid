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

## 3. The 25 `kind` disagreements — 3 decisions, one per cluster

`kind` is `mandatory` / `optional` / `informational`. It matters because **recall scores only
the key's `mandatory` + `bid_eligibility` labels** — so the key's `kind` decides what is counted.
The extractor's `kind` never affects the score; only changing the *key* would.

They fall into three clean clusters. Decide one line per cluster, not per label.

### Cluster A — key says MANDATORY, extractor says OPTIONAL (12 labels)
All from `Kriterienkatalog_Leistung` — the *performance* catalogue. Examples:
- DE-183 "Beherrschung der deutschen Sprache … Niveau C1"
- DE-455 "mindestens sechs Jahre Berufserfahrung, davon mindestens vier Jahre …"
- DE-456 "Mindestens ein Weiterbildungszertifikat: IPv6 Forum … (CNE6) Silver"
- DE-460 "Die zu bewertende Referenz muss mindestens drei der … Inhalte …"

**The real question: are the *Leistung* criteria pass/fail, or are they scored?** If a bidder
who misses them is excluded, the key is right (`mandatory`). If they only lose points, the
extractor is right (`optional`) and they should leave the scored set. `Eignung` = suitability
(pass/fail); `Leistung` = performance (points) — which is why the extractor read them as scored.

**This does not rescue the number.** All 12 are currently *matched*, so reclassifying them
removes 12 from both sides: **0.77 → 0.75**. Decide it on what the tender actually means.

decision: ____________  (keep mandatory / change to optional)

### Cluster B — key says OPTIONAL, extractor says MANDATORY (8 labels) — recommend KEEP
Conditional escape clauses and formatting notes: "**Sofern** Sie aus berechtigten Gründen die
Unterlagen nicht beibringen können, teilen Sie diese Gründe mit" (DE-063, DE-438, DE-536),
"**Soweit** Sie mehr als drei Referenzen aufführen, benutzen Sie bitte die Folgeseiten"
(DE-535). These bind only if a condition applies; the extractor reads "bitte + imperative" as an
unconditional duty. The key looks right.

decision: ____________  (keep / change to mandatory)

### Cluster C — key says INFORMATIONAL, extractor says MANDATORY (5 labels) — recommend KEEP
Statements of consequence rather than actions the bidder takes: "Referenzen, die … nicht
erfüllen, gelten nicht" (DE-161), "Noch nicht realisierte Leistungsstände können nicht
berücksichtigt werden" (DE-441), "Sie ist nicht gesondert zu unterschreiben" (DE-132). The
arguable one is DE-477 "Weitere Fragen … sind nicht gestattet", which is a prohibition and so
arguably a duty.

decision: ____________  (keep / change DE-477 only / change all)

---

## 4. Spot-check three misses — 10 minutes, builds confidence in the 0.77

24 labels have no extracted row anywhere near them: the extractor simply did not produce these.
You do not need to check all 24. Open these three in the PDF at the page given and confirm each
is a real obligation that a bidder would have to satisfy. If all three hold, the population is
sound and 0.77 is a fair figure.

| Label | Document | Page | The clause |
|---|---|---|---|
| DE-107 | `Eigenerklaerung_Ausschlussgruende_VV2.pdf` | 6 | "…seinen Verpflichtungen zur Zahlung von Steuern, Abgaben oder Beiträgen zur Sozialversicherung…" — non-payment of taxes as an exclusion ground |
| DE-228 | `614251-2026.notice.de.pdf` | 5 | "Quellen der Eignungskriterien: Bekanntmachung, Auftragsunterlagen…" — the notice's own reference criterion |
| DE-363 | `Eigenerklaerung_Ausschlussgruende_VV2.pdf` | 6 | "…die öffentlichen Auftraggeber auf sonstige geeignete Weise die Verletzung…" — the buyer proving non-payment by other means |

all three are real requirements? ____________  (yes / no — say which)

The other two populations need no action: the 25 clearly-different non-matches were sampled in
section 1, and the 20 remaining candidates were already adjudicated as correct rejections.

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
