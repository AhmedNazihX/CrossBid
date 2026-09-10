"""Pydantic v2 schemas and enums: the one definition every other layer agrees on.

Routers, graph nodes, LLM structured outputs and the generated TypeScript types all read
their shapes from here.

**This package imports nothing else from `crossbid`.** It is the bottom of the dependency
order (`routers -> agent/ingestion/readmodel -> tools/reference/memory/guards ->
models/db/settings`, docs/project-plan.md), so a module here may only use the standard
library and third-party packages. `ecertis_criteria` lives here for exactly that reason:
the extraction schema needs the criterion enum, and a schema must not reach sideways into
`reference/` to get it.
"""
