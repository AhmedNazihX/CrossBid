"""Tests that reach real services. Every one is `live`-marked and excluded by default.

`pyproject.toml` sets `addopts = "-m 'not live'"`, so `make test` never opens a socket and
never spends money; `make test-live` is the deliberate opt-in. Nothing here may be the only
cover for a line of production code -- the offline suite in `tests/unit/` carries that.
"""
