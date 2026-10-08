# ADR-007 — Add a corrective loop around vector retrieval

## Status
Accepted

## Context
Before this capability, /ask returned an answer regardless of retrieval quality.
When the corpus had nothing relevant, the LLM would still produce confident prose
from unrelated chunks (or from parametric memory). Examples in the wild include
the 1.5B model hallucinating tax details from a loosely-related Nigeria VAT chunk.

## Decision
Add a corrective loop on the vector branch:
1. Grade retrieval by top rerank_score.
2. If weak, rewrite the query via the chat model and retry once.
3. If still weak, fall back to DuckDuckGo web search.
4. If still weak, refuse honestly.
Expose the whole path via corrective_trace in the response.

## Alternatives considered
- Always refuse below threshold, skip rewrite/web: too brittle — good queries
  get rejected when rerank scores are low but chunk content is still usable.
- Use an LLM grader per chunk: more accurate but 5x more LLM calls per query.
  Rerank score is a free, already-computed signal.
- Skip corrective, rely on prompt engineering: does not fix retrieval gaps.

## Consequences
- (+) No more confident hallucinations from weak retrieval.
- (+) Query rewriting sometimes surfaces documents that the original phrasing missed.
- (+) Web fallback rescues questions the corpus can't answer (when the network allows).
- (-) Latency: worst case is 4 LLM calls (grade is free, rewrite + retry grade + web synthesis).
- (-) DDG from inside a container is unreliable; production needs a keyed provider.
- (-) Corrective only applies to the vector branch. Graph and SQL are treated as
  either right (they return rows/facts) or wrong (they return empty). We may extend
  the corrective loop to graph later.