"""One module per graph node, each a function of `(state, config)` returning a partial state.

`extract_reqs` (S3.2.1) is the first. `parse_docs`, `check_reqs`, `score_verdict`,
`apply_review` and `finalize` arrive with their own stories; nothing here is created
speculatively.

A node never opens an HTTP connection or runs SQL itself. It calls `ingestion/`,
`reference/`, `memory/` and `readmodel/`, which is what keeps the layering in
`docs/project-plan.md` pointing one way.
"""
