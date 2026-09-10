"""Read-only external reference data: eCertis criteria and evidence, ECB rates.

Nothing in this package mutates its inputs, and the run-time half never opens a
socket -- see `ecertis_client` for the build-time / run-time split.
"""
