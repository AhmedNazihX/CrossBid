"""Ingestion: documents in, page-cited chunks out.

`parser` owns the contract (S2.1.1), `pymupdf_parser` the default implementation, and
`chunker` turns a parsed document into ~800-token chunks that each name a page (S2.1.3).
Nothing here talks to the network or the database.
"""
