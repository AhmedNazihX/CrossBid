"""S3.2.3 — scoring extraction against the golden answer keys, and verifying those keys.

Nothing here runs in a request. This is the maintainer's half of E3's done-when: a matcher
that decides when an extracted `Requirement` and a golden label describe the same
obligation, a recall score over the mandatory labels of one tender, and a report a person
adjudicates. `scripts/recall.py` is a thin CLI over it, and S7.1's DeepEval suite reuses the
*same* matcher rather than growing a second one — a second definition would drift, and the
two numbers would stop being comparable.
"""
