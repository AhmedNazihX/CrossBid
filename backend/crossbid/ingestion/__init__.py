"""Ingestion: documents in, page-cited chunks out, and the two stores they end up in.

`parser` owns the contract (S2.1.1), `pymupdf_parser` the default implementation, and
`chunker` turns a parsed document into ~800-token chunks that each name a page (S2.1.3).
Those three are pure and offline. `embeddings` (S2.2.1) is the OpenRouter embeddings client
plus the pgvector insert and search over `company_chunks` / `tender_chunks`, always scoped by
`company_id`; `storage` (S2.2.2) puts the original file in Supabase Storage under the
company's prefix and hands out ten-minute signed URLs. Both take their network and database
dependencies as arguments, so the unit suite never opens a socket.
"""
