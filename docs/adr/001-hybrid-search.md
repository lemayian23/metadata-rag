# ADR-001 — Hybrid retrieval via Postgres tsvector + RRF

## Status
Accepted

## Context
Pure vector retrieval misses exact-term matches. This was flagged at the
project kickoff and deferred; the deferral was a mistake. Reranking (#3)
reorders candidates but cannot recover a chunk the vector search never
returned. Codes, dates, exact phrases, and proper nouns are affected.

## Decision
Run two retrievals in parallel — dense (pgvector HNSW) and sparse (Postgres
ts_rank_cd) — and merge with Reciprocal Rank Fusion (k=60). Expose
`search_mode` on /query and /ask with a configurable default (`hybrid`).

## Alternatives considered
- Add Elasticsearch / OpenSearch with real BM25: rejected — heavyweight, one
  more service to run, and Postgres ts_rank_cd is close enough for the corpus
  sizes this system targets.
- Add a sparse-vector retriever (SPLADE) through a second embedding model:
  rejected — another model to run, another index, no clear win over plain FTS.
- Weight the merge with learned weights: rejected — RRF needs no training and
  no normalization, and performs on par with tuned linear fusion in the
  literature for the two-way case.

## Consequences
- (+) Exact-term queries hit the right chunk.
- (+) Zero new dependencies or services.
- (+) search_mode is per-request, so callers can A/B vector vs hybrid.
- (+) The merge is inspectable — every citation carries its rank in each list.
- (-) One extra DB round trip per hybrid request.
- (-) English-language analyzer baked into the tsvector column.
- (-) RRF ignores score magnitudes; a chunk ranked #1 by a huge margin gets
  the same RRF contribution as one ranked #1 by a whisker.
- (-) Requires a migration (tsvector column + GIN index).

## Notes
`_clean_arg`, `_rrf_merge`, and the query parser are all local to
`app/retrieval.py`. No external library beyond SQLAlchemy.