# Capability 01 — Hybrid Search RAG

## Goal
Combine dense vector search with exact-term retrieval (Postgres full-text
`tsvector`/`ts_rank_cd`) so that a query containing a rare token — a code, a
year, an exact phrase — is retrievable even when the embedding blurs it.

## Why
Vector search alone misses exact-term matches. A chunk containing "Finance Act
2024" can be ranked below a semantically-similar chunk that never mentions it.
Reranking cannot fix a retrieval *miss*; it only reorders what vector search
already returned. Keyword search closes that gap.

## Mechanism
1. `tsvector` generated column on chunks.content (english config).
2. `GIN` index on it.
3. `_retrieve_vector` — existing pgvector HNSW + filters.
4. `_retrieve_keyword` — `websearch_to_tsquery` + `ts_rank_cd`, top-K.
5. `_rrf_merge` — Reciprocal Rank Fusion, k=60:
       rrf(d) = Σ 1/(60 + rank_i(d))
   No score normalization needed; ranks live on a common ordinal scale.
6. `retrieve_chunks(..., search_mode=...)` dispatches to vector/keyword/hybrid.

## Endpoint
No new endpoint. `search_mode` on POST /query and POST /ask:
  - "vector"  : embeddings only
  - "keyword" : ts_rank_cd only
  - "hybrid"  : RRF merge (default; env DEFAULT_SEARCH_MODE)

## Response additions
Citation gains:
  - rrf_score (float) — RRF accumulation
  - vector_rank (int) — position in the vector list, 1-based
  - keyword_rank (int) — position in the keyword list, 1-based
  - keyword_score (float) — raw ts_rank_cd value (only in keyword mode)

## Observed results (query: "1.5 percent gross transaction value")
Hybrid:
  Kenya Tax Policy 2024           vector_rank=1  keyword_rank=2  rrf=0.0325
  Kenya Digital Services Tax 2024 vector_rank=3  keyword_rank=1  rrf=0.0323
  Nigeria VAT Guide               vector_rank=2  keyword_rank=-  rrf=0.0161
The keyword-#1 chunk climbs from rank 3 to rank 2 in hybrid — the merge is
doing exactly what it should.

## Trade-offs
- (+) Exact-term queries hit the right chunk even with no semantic overlap.
- (+) No new service (no Elasticsearch), no new model, no re-embedding.
- (+) RRF needs no tuning beyond k=60 (standard value).
- (-) One extra DB query per hybrid request.
- (-) `websearch_to_tsquery` uses the "english" config; non-English corpora
  need their own config or a per-row language column.

## Known issues / future work
- keyword_score is a raw ts_rank_cd value; not comparable across queries.
- The RRF k is hard-coded at 60. Parameterize if tuning becomes necessary.
- No BM25 per se; Postgres ts_rank_cd is a reasonable proxy.

## Files
- migrations/005_hybrid_search.sql
- app/retrieval.py (_retrieve_vector, _retrieve_keyword, _rrf_merge, dispatcher)
- app/models.py (Chunk.content_tsv generated column)
- app/schemas.py (Citation: rrf_score, vector_rank, keyword_rank, keyword_score;
  QueryRequest.search_mode; AskRequest.search_mode)
- app/main.py (search_mode plumbing through /query, /ask, vector branches)
- app/config.py (search_mode: str = "hybrid")