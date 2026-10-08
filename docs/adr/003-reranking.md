# ADR-003 — Add cross-encoder reranking after vector retrieval

## Status
Accepted

## Context
Vector top-K frequently misses the best chunk when the query contains exact terms the embedding blurs (proper nouns, numbers, dates). Observed in practice: two near-identical Kenya chunks scored 0.908 and 0.902 — indistinguishable by cosine.

## Decision
Insert a cross-encoder reranker between retrieval and generation. Retrieve 50 candidates via pgvector, rerank to 5 via cross-encoder/ms-marco-MiniLM-L-6-v2 (local, CPU).

## Consequences
- (+) Top-1 precision improves most on queries with rare terms.
- (+) Local — no API cost, same model for dev and prod.
- (-) ~300 ms extra latency per query.
- (-) Extra 80 MB model in the image and a persistent HF cache volume.
- (-) Rerank scores are not directly comparable across queries (logits, not probabilities).
