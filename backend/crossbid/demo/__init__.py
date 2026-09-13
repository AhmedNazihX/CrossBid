"""The demo tenant: who it is, and how it gets into a database. Story S2.4.3.

Nothing here runs in a request, which is why the package sits beside `routers/` rather than
under it, as `eval/` does. `company.py` reads S6.3's generated evidence pack and pins the
tenant's deterministic ids; `seed.py` drives that pack through the *production* ingestion
pipeline so a seeded document is indistinguishable from an uploaded one — same state machine,
same chunks, same vectors, so `company_rag_search` finds the same evidence in the walkthrough
as it would after a real upload.

`scripts/seed_demo_company.py` is the CLI over it and holds nothing but assembly.
"""
