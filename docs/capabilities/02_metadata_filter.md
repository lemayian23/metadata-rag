# Capability 02 — Metadata-Filtered RAG

## Goal
Retrieve semantically similar chunks AND respect structured filters (category, author, location, tags, date range, arbitrary JSONB keys).

## Endpoint
`POST /query` with a `filters` object.

## How it works
1. Query embedded via nomic-embed-text (768-d).
2. SQL WHERE clauses generated from MetadataFilter (see app/filters.py).
3. pgvector HNSW index returns top-K by cosine similarity, filtered.
4. Chunks joined to documents, returned with citation metadata.

## Schema
- documents: typed columns (category, author, location, published_at) + tags TEXT[] + meta JSONB.
- chunks: content, tokens, embedding vector(768), meta JSONB.
- Indexes: B-tree on typed columns, GIN on tags and meta, HNSW on embedding.

## Trade-offs
- (+) Precise scoping — "only 2024 Kenya finance docs".
- (-) Filters are exact match unless caller does extra work; no fuzzy matching.
- (-) Ingest is non-idempotent: same content twice = two documents.

## Failure modes observed
- Missing OpenAI key -> 401/500 on /ingest (resolved by moving to Ollama).
- Vector dim mismatch after model swap -> wipe DB volume (docker compose down -v).

## Files
- app/filters.py, app/retrieval.py, app/schemas.py (MetadataFilter)
- migrations/001_init.sql
