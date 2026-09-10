"""GENERATED FILE — do not hand-edit.

Written by `scripts/build_ecertis_cache.py` from `crossbid/reference/data/ecertis/criteria.json`
(eCertis REST, spec v0.6). Regenerate with

    uv run python scripts/build_ecertis_cache.py

Any manual change is lost on the next run, and `--check` fails in the meantime.

These are the **EU-level** ESPD criterion ids. eCertis also issues a separate UUID per
country for the same criterion (`criteria?nationalEntity=de` returns those), but those ids
mean nothing outside their own country, so they are useless as an extraction enum for a
cross-border tool. The national ids and their evidence live in
`crossbid/reference/data/ecertis/evidence_*.json`, keyed on the ids below.

`models/` imports nothing else from `crossbid`, which is why this enum is generated into
the contract layer rather than read out of `reference/` at import time.

Source date: 2026-09-10 · 56 criteria
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, Literal

EcertisCriterionId = Literal[
    "005eb9ed-1347-4ca3-bb29-9bc0db64e1ab",
    "07301031-2270-41af-8e7e-66fe0c777107",
    "074f6031-55f9-4e99-b9a4-c4363e8bc315",
    "166536e2-77f7-455c-b018-70582474e4f6",
    "1f49b3f0-d50f-43f6-8b30-4bafab108b9b",
    "297d2323-3ede-424e-94bc-a91561e6f320",
    "3293e92b-7f3e-42f1-bee6-a7641bb04251",
    "396f288a-e267-4c20-851a-ed4f7498f137",
    "3a18a175-1863-4b1d-baef-588ce61960ca",
    "3aaca389-4a7b-406b-a4b9-080845d127e7",
    "47112079-6fec-47a3-988f-e561668c3aef",
    "499efc97-2ac1-4af2-9e84-323c2ca67747",
    "4bf996d9-439c-40c6-9ab9-980a48cb55a1",
    "514d3fde-1e3e-4dcd-b02a-9f984d5bbda3",
    "56d13e3d-76e8-4f23-8af6-13e60a2ee356",
    "5e506c16-26ab-4e32-bb78-b27f87dc0565",
    "612a1625-118d-4ea4-a6db-413184e7c0a8",
    "61874050-5130-4f1c-a174-720939c7b483",
    "6346959b-e097-4ea1-89cd-d1b4c131ea4d",
    "63adb07d-db1b-4ef0-a14e-a99785cf8cf6",
    "68918c7a-f5bc-4a1a-a62f-ad8983600d48",
    "696a75b2-6107-428f-8b74-82affb67e184",
    "6ee55a59-6adb-4c3a-b89f-e62a7ad7be7f",
    "73f10e36-ed7a-412e-995c-aa76463e3776",
    "7604bd40-4462-4086-8763-a50da51a869c",
    "7662b7a9-bcb8-4763-a0a7-7505d8e8470d",
    "77f481ce-ffb6-483f-8e2b-c78db5e68292",
    "7d85e333-bbab-49c0-be8d-c36d71a72f5e",
    "87b3fa26-3549-4f92-b8e0-3fd8f04bf5c7",
    "8ed65e48-fd0d-444f-97bd-4f58da632999",
    "8fda202a-0c37-41bb-9d7d-de3f49edbfcb",
    "90a2e100-44cc-45d3-9970-69d6714f1596",
    "9460457e-b43d-48a9-acd1-615de6ddd33e",
    "9eeb6d5c-0eb8-48e8-a4c5-5087a7c095a4",
    "a261a395-ed17-4939-9c75-b9ff1109ca6e",
    "a34b70d6-c43d-4726-9a88-8e2b438424bf",
    "a7669d7d-9297-43e1-9d10-691a1660187c",
    "a80ddb62-d25b-4e4e-ae22-3968460dc0a9",
    "ab0e7f2e-6418-40e2-8870-6713123e41ad",
    "b16cb9fc-6cb7-4585-9302-9533b415cf48",
    "b1b5ac18-f393-4280-9659-1367943c1a2e",
    "b61bbeb7-690e-4a40-bc68-d6d4ecfaa3d4",
    "bdf0601d-2480-4250-b870-658d0ee95be6",
    "c27b7c4e-c837-4529-b867-ed55ce639db5",
    "c599c130-b29f-461e-a187-4e16c7d40db7",
    "c8809aa1-29b6-4f27-ae2f-27e612e394db",
    "cc18c023-211d-484d-a32e-52f3f970285f",
    "cdd3bb3e-34a5-43d5-b668-2aab86a73822",
    "d3732c09-7d62-4edc-a172-241da6636e7c",
    "d3dfb714-f558-4512-bbc5-e456fa2339de",
    "d486fb70-86b3-4e75-97f2-0d71b5697c7d",
    "d726bac9-e153-4e75-bfca-c5385587766d",
    "d789d01a-fe03-4ccd-9898-73f9cfa080d1",
    "daffa2a9-9f8f-4568-8be8-7b8bf306d096",
    "dc12a151-7fdf-4733-a8f0-30f667292e66",
    "e4d37adc-08cd-4f4d-a8d8-32b62b0a1f46",
]
"""Every criterion eCertis knows. An extraction schema typed on this rejects anything else."""

CRITERION_NAMES: Final[Mapping[EcertisCriterionId, str]] = MappingProxyType(
    {
        "005eb9ed-1347-4ca3-bb29-9bc0db64e1ab": "Participation in a criminal organisation",
        "07301031-2270-41af-8e7e-66fe0c777107": "Educational and professional qualifications",
        "074f6031-55f9-4e99-b9a4-c4363e8bc315": "Specific yearly turnover",
        "166536e2-77f7-455c-b018-70582474e4f6": "Business activities are suspended",
        "1f49b3f0-d50f-43f6-8b30-4bafab108b9b": "Average annual manpower",
        "297d2323-3ede-424e-94bc-a91561e6f320": "Fraud",
        "3293e92b-7f3e-42f1-bee6-a7641bb04251": (
            "Early termination, damages or other comparable sanctions"
        ),
        "396f288a-e267-4c20-851a-ed4f7498f137": "Insolvency",
        "3a18a175-1863-4b1d-baef-588ce61960ca": (
            "For supply contracts: performance of deliveries of the specified type"
        ),
        "3aaca389-4a7b-406b-a4b9-080845d127e7": (
            "Technicians or technical bodies for quality control"
        ),
        "47112079-6fec-47a3-988f-e561668c3aef": "Money laundering or terrorist financing",
        "499efc97-2ac1-4af2-9e84-323c2ca67747": "General yearly turnover",
        "4bf996d9-439c-40c6-9ab9-980a48cb55a1": (
            "Technical facilities and measures for ensuring quality"
        ),
        "514d3fde-1e3e-4dcd-b02a-9f984d5bbda3": "Guilty of grave professional misconduct",
        "56d13e3d-76e8-4f23-8af6-13e60a2ee356": (
            "Agreements with other economic operators aimed at distorting competition"
        ),
        "5e506c16-26ab-4e32-bb78-b27f87dc0565": (
            "For service contracts: performance of services of the specified type"
        ),
        "612a1625-118d-4ea4-a6db-413184e7c0a8": "Subcontracting proportion",
        "61874050-5130-4f1c-a174-720939c7b483": (
            "Direct or indirect involvement in the preparation of this procurement procedure"
        ),
        "6346959b-e097-4ea1-89cd-d1b4c131ea4d": "Number of managerial staff",
        "63adb07d-db1b-4ef0-a14e-a99785cf8cf6": "Purely national exclusion grounds",
        "68918c7a-f5bc-4a1a-a62f-ad8983600d48": "Arrangement with creditors",
        "696a75b2-6107-428f-8b74-82affb67e184": (
            "Guilty of misrepresentation, withheld information, unable to provide required "
            "documents and obtained confidential information of this procedure"
        ),
        "6ee55a59-6adb-4c3a-b89f-e62a7ad7be7f": "Enrolment in a relevant professional register",
        "73f10e36-ed7a-412e-995c-aa76463e3776": (
            "For service contracts: membership of particular organisation needed"
        ),
        "7604bd40-4462-4086-8763-a50da51a869c": "Professional risk indemnity insurance",
        "7662b7a9-bcb8-4763-a0a7-7505d8e8470d": (
            "For supply contracts: samples, descriptions or photographs with certification of "
            "authenticity"
        ),
        "77f481ce-ffb6-483f-8e2b-c78db5e68292": "Set up of economic operator",
        "7d85e333-bbab-49c0-be8d-c36d71a72f5e": "Payment of social security contributions",
        "87b3fa26-3549-4f92-b8e0-3fd8f04bf5c7": "Enrolment in a trade register",
        "8ed65e48-fd0d-444f-97bd-4f58da632999": (
            "Certificates by independent bodies about environmental management systems or "
            "standards"
        ),
        "8fda202a-0c37-41bb-9d7d-de3f49edbfcb": "Assets being administered by liquidator",
        "90a2e100-44cc-45d3-9970-69d6714f1596": "Study and research facilities",
        "9460457e-b43d-48a9-acd1-615de6ddd33e": "Environmental management measures",
        "9eeb6d5c-0eb8-48e8-a4c5-5087a7c095a4": (
            "For service contracts: authorisation of particular organisation needed"
        ),
        "a261a395-ed17-4939-9c75-b9ff1109ca6e": (
            "Breaching of obligations in the fields of social law"
        ),
        "a34b70d6-c43d-4726-9a88-8e2b438424bf": (
            "Breaching of obligations in the fields of labour law"
        ),
        "a7669d7d-9297-43e1-9d10-691a1660187c": (
            "For supply contracts: certificates by quality control institutes"
        ),
        "a80ddb62-d25b-4e4e-ae22-3968460dc0a9": (
            "Breaching of obligations in the fields of environmental law"
        ),
        "ab0e7f2e-6418-40e2-8870-6713123e41ad": "Other economic or financial requirements",
        "b16cb9fc-6cb7-4585-9302-9533b415cf48": "Average yearly turnover",
        "b1b5ac18-f393-4280-9659-1367943c1a2e": (
            "Conflict of interest due to its participation in the procurement procedure"
        ),
        "b61bbeb7-690e-4a40-bc68-d6d4ecfaa3d4": "Payment of taxes",
        "bdf0601d-2480-4250-b870-658d0ee95be6": (
            "For supply contracts: samples, descriptions or photographs without certification "
            "of authenticity"
        ),
        "c27b7c4e-c837-4529-b867-ed55ce639db5": "Corruption",
        "c599c130-b29f-461e-a187-4e16c7d40db7": (
            "For works contracts: technicians or technical bodies to carry out the work"
        ),
        "c8809aa1-29b6-4f27-ae2f-27e612e394db": "Allowance of checks",
        "cc18c023-211d-484d-a32e-52f3f970285f": "Tools, plant or technical equipment",
        "cdd3bb3e-34a5-43d5-b668-2aab86a73822": (
            "For works contracts: performance of works of the specified type"
        ),
        "d3732c09-7d62-4edc-a172-241da6636e7c": "Bankruptcy",
        "d3dfb714-f558-4512-bbc5-e456fa2339de": "Specific average turnover",
        "d486fb70-86b3-4e75-97f2-0d71b5697c7d": (
            "Terrorist offences or offences linked to terrorist activities"
        ),
        "d726bac9-e153-4e75-bfca-c5385587766d": (
            "Certificates by independent bodies about quality assurance standards"
        ),
        "d789d01a-fe03-4ccd-9898-73f9cfa080d1": (
            "Child labour and other forms of trafficking in human beings"
        ),
        "daffa2a9-9f8f-4568-8be8-7b8bf306d096": (
            "Analogous situation like bankruptcy under national law"
        ),
        "dc12a151-7fdf-4733-a8f0-30f667292e66": "Supply chain management",
        "e4d37adc-08cd-4f4d-a8d8-32b62b0a1f46": "Financial ratio",
    }
)
"""Criterion id to its English ESPD name, for prompts and for the requirement table."""

CRITERION_IDS: Final[tuple[EcertisCriterionId, ...]] = tuple(CRITERION_NAMES)
"""The same ids as a tuple, in the order they appear above (sorted by id)."""
