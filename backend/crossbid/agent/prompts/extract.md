# Extract the requirements of one tender section

You are reading one section of a public procurement pack — five to eight pages of a single
document — and listing every obligation the bidder must satisfy, declare, or submit.

The section is handed to you as a delimited data block. How to read it is stated in your
system prompt and repeated immediately before and after the block itself, by the wrapper in
`crossbid/guards/wrap.py`; it is not restated here. Two of those rules decide whether your
answer is usable at all: **quote verbatim**, and take the page **from the DOCUMENT header the
quote sat under**, never from anything the document says about itself.

Return one entry per obligation. Do not invent an obligation, do not merge two distinct
obligations into one entry, and return an empty list when the section states none. A section
of standard terms or of pure background can legitimately yield nothing.

## Fields

- `source_text` — the obligation in the document's own language, copied character for
  character out of the block and trimmed to the sentence or clause that states the duty.
  Every entry is checked against the page it cites, and one whose quote is not found there is
  thrown away, so a paraphrase or a tidied-up quote costs you the entry.
- `translation` — the same obligation in {bidder_language}: one or two sentences, plain enough
  for a reader who does not speak the tender's language, and carrying every number, currency
  and date the quote carries. Say what the bidder must do, not what the clause is about.
- `page` — the page number of the DOCUMENT header the quote sat under.
- `kind` — `mandatory` when non-compliance can exclude the bid, `optional` when it only
  scores points, `informational` when the text states no duty at all.
- `category` — `formal` for procedural and document-submission duties; `economic_financial`
  for turnover, insurance and balance-sheet conditions; `technical_professional` for
  references, staff, equipment and qualifications; `exclusion_ground` for integrity,
  convictions, taxes, sanctions and social-security duties (§123/§124 GWB and their
  equivalents in other member states); `other` when none of those fit.
- `stage` — see below. This is the field that decides whether the entry is used at all.
- `checkable` — `company_property` when compliance can be judged from facts about the bidding
  company: turnover figures, staff numbers, held certificates, past references, the absence of
  convictions. `document_submission` when it can only be judged by seeing whether a form was
  filled in and attached. `neither` otherwise.
- `ecertis_criterion_id` — **null unless the section itself prints an ESPD criterion UUID.**
  A tender that publishes a DUME or ESPD form prints them, and then the mapping is a fact
  rather than a guess. Never derive one from the wording of a criterion: an id that is not on
  the official list is discarded and the entry loses its mapping.

## The `stage` field

You are feeding a go/no-go qualification matrix. It answers one question, asked *before* the
company decides whether to bid: may we participate, and can we prove it? It does not track
delivery duties.

- `bid_eligibility` — a condition on the bidder that decides whether the bid is admissible:
  selection criteria, exclusion grounds, the declarations that attest to them, documents that
  must accompany the offer, and the formal rules for submitting it (deadline, language,
  signature, lot rules).
- `contract_performance` — a duty that binds whoever *wins*, once the contract runs: service
  levels, delivery and acceptance, reporting, invoicing and payment terms, price adjustment,
  liability and warranty, data-processing duties, confidentiality during delivery,
  termination, governing law, how subcontractors are managed after award.

The test: would a company still have to do this if it never won the contract? If no, it is
`contract_performance`. Standard terms (AGB, EVB-IT, VOL/B), the framework agreement and the
data-processing agreement are almost entirely `contract_performance`, even though every
sentence in them is phrased as an obligation. Being required to **sign or submit** such a
document with the offer is `bid_eligibility`; the duties written inside it are not.

Getting this wrong in the safe-looking direction is not safe. Marking contract duties
`bid_eligibility` buried the real selection criteria under 484 spurious rows when this was
measured on a real German pack.
