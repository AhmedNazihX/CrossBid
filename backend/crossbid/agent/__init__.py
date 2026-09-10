"""The agent: everything LangGraph.

`state.py` holds the state channels, `nodes/` one module per node, `prompts/` the versioned
`.md` prompts, and `graph.py` (S3.1.1) wires them into the outer run. `tools/` (F3.3) is the
only place the model touches the outside world.

The shape of the graph is worth stating once, because it decides where new work belongs: the
**outer graph is a deterministic workflow** — parse, extract, check, score, interrupt for a
human, apply the review, finalise — and the **agentic part is inside `check_reqs`**, a small
ReAct loop per requirement with a bounded tool budget. Extraction is workflow: a fixed number
of calls over a fixed set of sections, fanned out for latency and nothing else.
"""
