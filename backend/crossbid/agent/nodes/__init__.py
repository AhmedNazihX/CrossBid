"""One module per graph node, each a function of `(state, config)` returning a partial state.

`parse_docs` (S3.1.1), `extract_reqs` (S3.2.1) and `check_reqs` (S3.3.1) are built;
`score_verdict`, `apply_review` and `finalize` arrive with their own stories, and nothing
here is created speculatively.

`check_loop.py` is the exception to "one module per node": it is `check_reqs`' inner ReAct
loop, split out because the node is two concerns — fanning out over a lane, and checking one
requirement against the bidder's documents — and one file holding both would be the longest
in the package. It is also the only agentic code in the repository; the graph around it is a
deterministic workflow.

A node never opens an HTTP connection or runs SQL itself. It calls `ingestion/`,
`reference/`, `memory/` and `readmodel/`, which is what keeps the layering in
`docs/project-plan.md` pointing one way.
"""
