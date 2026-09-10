# eCertis test fixtures

Recorded from the live service on **2026-09-10**, base
`https://ec.europa.eu/growth/tools-databases/ecertisrest/` (GET only, no key, spec v0.6).
Kept small on purpose: the committed cache under `crossbid/reference/data/ecertis/` is the
full data set, and these are only enough to exercise the client and the normaliser.

| File | Request | Trimming |
|---|---|---|
| `criteria_list.json` | `GET criteria?lang=en` | 3 of 56 criteria kept: Payment of taxes, Corruption, General yearly turnover. Otherwise verbatim — note it carries `CriteriaTypeID` but **no** `CriteriaTypeName`, which is why the taxonomy has to come from a second call. |
| `criteria_list_taxonomy.json` | `GET criteria?nationalEntity=eu&lang=en` | 2 of 58 criteria kept: Payment of taxes and Corruption. *General yearly turnover is deliberately absent* so the "no label for this name" fallback is covered. The `Id` values differ from `criteria_list.json` — that is the real behaviour, not a mistake. |
| `criterion_detail_de_taxes.json` | `GET criteria/b61bbeb7-690e-4a40-bc68-d6d4ecfaa3d4?countryFilter=de&lang=en` | Verbatim, untrimmed. 3 national sub-criteria, 7 evidences. |
| `criterion_detail_edge_cases.json` | **Hand-built, not recorded.** | Collects every awkward shape observed in the live payloads into one criterion: empty `{}` scalars, `description` as an object *and* as a list, an evidence in two `RequirementGroup`s, an evidence with no issuer party, an evidence with no `Id`, a sub-criterion with no `Id`, a sub-criterion with no `RequirementGroup`, whitespace to collapse, and an unknown future field that must be ignored. |

Reproduce with `curl -s "<base><path>" | python3 -m json.tool`.
