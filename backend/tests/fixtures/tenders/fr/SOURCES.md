# FR tender fixture — sources

Story: **S6.1** (French half). Retrieved **2026-09-10**. Real documents, unmodified.

## The tender

| Field | Value |
|---|---|
| TED publication number | `618320-2026` |
| OJ S issue | 173/2026, published 2026-09-08 |
| Buyer's internal reference | MEN-SG-AOO-26023 (`26023-AOO` in the RC) |
| Title | Prestations de conseil en architecture d'entreprise et d'expertise technique — pour les ministères de l'éducation nationale, des sports, de la jeunesse et de la vie associative |
| Buyer | Ministère de l'éducation nationale (with the Ministère de l'enseignement supérieur, de la recherche et de l'innovation) |
| Procedure | Appel d'offres ouvert, accord-cadre à bons de commande, mono-attributaire (Directive 2014/24/UE) |
| CPV | 72000000 — Services de technologies de l'information, conseil, développement de logiciels, internet et appui |
| Lots | 1 (`LOT-0001`) |
| Official language | FRA |
| Submission language | FRA |
| Value | €3 900 000 HT estimated, framework maximum €7 800 000 HT |
| Tender deadline | 2026-10-09 16:00 (UTC+02:00) |
| Notice type | `cn-standard` |
| Award criteria | Valeur technique 65 % / Prix 25 % / Qualité environnementale 10 % |

## Provenance

| Artefact | Source |
|---|---|
| Notice discovery | `POST https://api.ted.europa.eu/v3/notices/search` (documented API, no key) |
| `618320-2026.notice.fr.pdf` | `https://ted.europa.eu/fr/notice/618320-2026/pdf` (from the notice's `links.pdf.FRA`) |
| `documents/26023_AOO_Conseil_Architecure_SI_RC_v1.pdf` | `https://www.marches-publics.gouv.fr/index.php?page=Entreprise.EntrepriseDownloadReglement&id=MzA2MTU2NA==&orgAcronyme=f0g` |
| `documents/DUME_acheteur.xml` | `https://www.marches-publics.gouv.fr/entreprise/consultation/contenus_transmis/dume/telechargement/zip/577664/3061564/f0g/xml` |
| Platform page (the notice's `document-url-lot`) | `https://www.marches-publics.gouv.fr/entreprise/consultation/3061564?orgAcronyme=f0g` — PLACE, the French state procurement platform |

Both documents were fetched **once, by hand, to create this fixture**, with the user's explicit
authorisation on 2026-09-10, and both are plain `GET` links published on the public consultation
page — no account, no login, no form. Access is anonymous by design, not by loophole: French buyers
above the formalised-procedure threshold must publish the documents de la consultation on a profil
d'acheteur with free, direct and complete access (Code de la commande publique, articles R.2132-1
and following — the exact article was not verified against Légifrance, so treat this as the
principle rather than as a citation). PLACE served both files to an unauthenticated `curl` with
nothing but a cookie round-trip, the same shape as the DE fixture (ADR-0001).

**The application never does this.** The "no scraping anywhere" rule in `CLAUDE.md` stands: at run
time Crossbid reads TED, eCertis and Frankfurter through their documented APIs, and the bidder
uploads procurement documents by hand. This directory is build-time content, not a run-time code
path.

## Why the whole pack is not here

PLACE lists three pieces for this consultation and exposes **two** of them as ordinary links:

| Piece | Size on PLACE | Committed? |
|---|---|---|
| Règlement de consultation | 410,62 Ko | **yes** |
| DUME Acheteur | 145,32 Ko | **yes** |
| Dossier de consultation (the full DCE) | 14,7 Mo | **no** |

The full DCE — CCAP, CCTP, cadre de réponse, BPU, acte d'engagement — sits behind PLACE's
`EntrepriseDemandeTelechargementDce` page. That page offers a genuinely anonymous route ("*Je
souhaite télécharger anonymement le Dossier de Consultation des Entreprises*", no account, no
identification), but reaching it means **submitting a form**, which this fixture's acquisition
rules forbid. So the DCE was not fetched. It is not a registration wall and it is not an access
control; it is one radio button and a submit that a human can click in ten seconds at the URL
above, and the file is 14,7 Mo, which fits the 15 MB ceiling on its own. If the golden set later
needs the CCTP, a human should download it and drop it in `documents/`.

The size total is therefore **766 KB** (783 765 bytes including this file), far under the 15 MB ceiling — the opposite problem from the
DE fixture, which had to be curated down from 42 MB.

## Where the requirements actually live

The eForms notice states **no criteria at all**:

```
2.1.6. Motifs d'exclusion   → Sources des motifs d'exclusion: Document de marché
5.1.9. Critères de sélection → Sources des critères de sélection: Document de marché
```

That is not an accident of this notice. Of 457 French CPV-72 `cn-standard` notices sampled through
the TED Search API on 2026-09-10, only **65 (14 %)** populated `selection-criterion-description-lot`
at all. **The notice is never enough for a French tender** — which is the whole argument for the
upload-the-pack design, and the reason this fixture carries the RC and the DUME rather than the
notice alone.

The two committed documents carry, between them, **30 named criteria**:

- **Règlement de consultation, article 15.1** — four *scored* selection criteria with hard numeric
  thresholds, marked out of 10, eliminating any candidate below 5/10:

  | # | Criterion | Thresholds |
  |---|---|---|
  | 1 | Chiffre d'affaires annuel HT (dernier exercice) | > €1 950 000 → 3/3 · €1 460 000–1 950 000 → 2/3 · < €1 460 000 or unstated → 0/3 |
  | 2 | Effectifs intervenant dans le domaine | > 12 → 3/3 · 7–12 → 2/3 · ≤ 6 or unstated → 0/3 |
  | 3 | Références datées et chiffrées de moins de trois ans | ≥ 4 → 2/2 · 2–3 → 1/2 · < 2 or unstated → 0/2 |
  | 4 | Processus ou certification qualité | certified or own documented process → 2/2 · none or unstated → 0/2 |

- **DUME Acheteur (`DUME_acheteur.xml`)** — the buyer's pre-filled ESPD request: 148 811 bytes,
  root element `espd-req:ESPDRequest` (ESPD exchange format v1, `ESPDRequest-1`), holding exactly
  **30 `ccv:Criterion` elements and 97 distinct criterion UUIDs**: 6 selection criteria (chiffre d'affaires annuel général, ratios financiers, assurance
  contre les risques professionnels, effectifs moyens annuels, principaux services fournis
  antérieurement, détail des certificats établis par des organismes indépendants concernant les
  normes d'assurance de la qualité) and 24 exclusion grounds (participation à une organisation
  criminelle, corruption, fraude, infraction terroriste, blanchiment, travail des enfants, impôts,
  cotisations sociales, droit environnemental / social / du travail, faillite, insolvabilité,
  conciliation, situation analogue, liquidateur, cessation d'activités, faute professionnelle
  grave, entente, conflit d'intérêt, association à la préparation, résiliation, fausses
  déclarations, and *motifs d'exclusion purement nationaux*).

## Why this fixture is a fair test of the core bet

25 pages, 65 026 characters of French legal prose, **zero text-free pages**, so `pymupdf4llm`
reads all of it and the OCR the plan cut is not needed. The XML parses clean with
`xml.etree.ElementTree`.

Three properties make it a real test rather than a second copy of the DE fixture:

1. **The rule shape is different.** Germany's `Kriterienkatalog Eignung` is pass/fail against
   absolute minima (turnover ≥ €3 000 000, ≥ 29 VZÄ). France scores capacity out of 10 with banded
   thresholds and a 5/10 pass mark. An extractor that only knows "minimum X" will mangle article
   15.1; the matrix has to represent a banded score, not a boolean.
2. **It states the cross-border problem in its own words.** RC §14.4.1: "*Le candidat non établi en
   France produit les attestations et certificats équivalents dans son pays d'origine ou, à défaut,
   une déclaration sur l'honneur ou sous serment, selon le pays considéré.*" And RC §17.1 names the
   French national evidence the winner must produce — attestation URSSAF (art. L.243-15 CSS), the
   tax certificate from the administration fiscale, the SIREN number from INSEE, the nominative
   list of foreign employees under art. D.8254-2 Code du travail. A German bidder has none of those
   documents and must map each to its national equivalent. **That mapping is eCertis's job and
   Crossbid's wedge**, stated by the tender itself rather than inferred by us.
3. **The DUME gives the eCertis join key for free.** The buyer's ESPD request carries the criterion
   UUIDs directly, so `criteria/{uuid}?countryFilter=de` can be called without guessing which of
   the ~56 ESPD criteria a passage refers to. This is the cleanest available test of the
   criterion-centric model recorded in `CLAUDE.md`.

Note for the demo: against the fictional demo GmbH's profile (about €2.8m turnover, 21–25 staff),
article 15.1 scores criterion 1 at 3/3 and criterion 2 at 3/3, i.e. **6/10 before references and
quality process are even counted — a pass**. The DE fixture yields a `no_go`; this one yields a
`go` or `conditional_go` on the same company. Between them S7.3 and S7.4 get both walkthroughs
from real tenders, with no profile tuning.

## Filenames

No transliteration was needed — both original names are already ASCII. Contents are untouched.

| File (committed) | Original name | Pages | Size |
|---|---|---|---|
| `618320-2026.notice.fr.pdf` | TED-generated, no filename | 5 | 129 KB |
| `documents/26023_AOO_Conseil_Architecure_SI_RC_v1.pdf` | — same — (inside `26023_AOO_Conseil_Architecture_SI_RC_pub_v1/` in the served zip; note the buyer's own typo, *Architecure*) | 20 | 479 KB |
| `documents/DUME_acheteur.xml` | `aautad4x.xml` — a random name generated by PLACE per download, renamed for legibility | — | 146 KB |

## Candidates considered and rejected

| TED number | Buyer | Why not |
|---|---|---|
| `607725-2026` | 6 agences de l'eau, TMA of business applications | The runner-up, and close. Richest RC found (24 pages, 67 057 chars) and a computed threshold ("*chiffre d'affaires annuel dans le domaine d'au moins la moitié du montant maximum du lot*"), but its DUME Acheteur was still "en cours de publication", so no criterion UUIDs. |
| `625910-2026` | Centre national de la musique, TMA | Good DUME (29 criteria) and an explicit walk through DUME part III sections A–D, but a thinner RC (19 pages) and no quantified selection threshold. |
| `453517-2026` | Ministère de l'éducation nationale, "Mon Master" TMA | Comparable RC, but deadline 2026-09-23 — closest to expiry of the shortlist. |
| `588251-2026` | Ministère de l'Intérieur, immersive police training | Dense RC (29 pages), but VR training rather than IT services, so a weaker fit for an IT-services SME. |
| `605981-2026` | COFIROUTE | The single richest `selection-criterion-description-lot` in the whole FR sample (26 110 chars, 15 items), but the subject is motorway flood-vulnerability engineering (CPV 71311220) — no IT-services SME would bid. |
| `507176-2026` | Enedis | 24 criteria items in the notice, but no `document-url-lot` at all. |
| `522021-2026` | Toulouse Métropole, SI security consulting | 16 criteria items, but deadline 2026-08-07 (already closed) and the platform URL is a `dematEnt.login` endpoint. |
| `527301-2026` | Brest en vue GIE, territorial marketplace | Its `document-url-lot` was the only genuinely promising *plain-GET* DCE route in the sample — `centraledesmarches.com/…/consulterDCEHorsIdentification.jsp?iIdAffaire=85702`, literally "consult the DCE without identification" — but it now returns HTTP 404, the consultation having closed. |
| `561900-2026`, `562874-2026` | DIGITAL AFRICA | The only FR CPV-72 notices in the sample pointing at direct file URLs (Google Drive). Deadlines already passed 2026-09-06. |

Platform routes probed and rejected, all because the DCE sits behind a form:
`achatpublic.com` (`telechargerDCE.action`), `marches-publics.info` / AWS-Achat
(`dematEnt.relocateDCE`), `e-marchespublics.com` (`timideenregistrementEntrepriseDce`).
None asked for an account; all asked for a POST.

## Reserve candidate

`607725-2026` (6 agences de l'eau, tierce maintenance applicative, 2 lots, deadline 2026-10-08) is
the natural second French tender if the golden set needs one. Its RC is longer and more structured
than the committed one — separate sections for *motifs d'exclusion*, *niveaux minimaux de
participation*, *tâches essentielles* and *vérification des conditions de participation* — and its
minimum turnover is expressed as a **formula over another section of the same document** ("at least
half the lot maximum stated in article 3.4"), which is a harder extraction problem than any
absolute figure in either committed fixture. Not committed; re-downloadable from
`https://www.marches-publics.gouv.fr/entreprise/consultation/3055779?orgAcronyme=d4t`.
