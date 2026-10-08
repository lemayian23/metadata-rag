# Capability 03 — Reranking RAG

## Goal
Improve precision of the top-K by rescoring a large candidate set with a cross-encoder before sending to the LLM.

## Pipeline
    query -> retrieve_chunks(top_k=50) -> CrossEncoder -> top 5 -> LLM

## Why it matters
- Bi-encoder (vector search) encodes query and chunk independently -> fast but approximate.
- Cross-encoder sees (query, chunk) jointly -> slow but precise.
- The gap is biggest when embeddings blur exact-term matches (proper nouns, numbers, dates).

## Endpoint
`POST /query` with `rerank: true | false` and optional `rerank_candidates`.

## Model
cross-encoder/ms-marco-MiniLM-L-6-v2 (~80 MB, CPU, ~300 ms for 50 pairs).
Cached in Docker volume `hf_cache` — downloaded once.

## Response fields
- score: cosine similarity from pgvector (bi-encoder).
- rerank_score: cross-encoder logit. Higher = more relevant. Not bounded.

## Cost
- First query after rebuild: +30-60 s (model download).
- Subsequent queries: +200-500 ms on CPU.

## Failure modes
- If rerank_candidates is too small, reranking has nothing to reorder.
- Cross-encoder is English-centric; quality drops on other languages.

## Files
- app/rerank.py (new)
- app/main.py (query handler branches on rerank)
- app/config.py (RERANK_MODEL, RERANK_CANDIDATES, RERANK_TOP_K)
