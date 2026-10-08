# Capability 07 — Corrective RAG

## Goal
Stop trusting retrieval unconditionally. Grade the retrieved context before answering.
If retrieval is weak, rewrite the query and retry. If still weak, fall back to web
search. If still weak, refuse honestly instead of hallucinating.

## Pipeline (vector branch)
    retrieve -> rerank -> grade_by_rerank
      ok   -> answer from context
      weak -> rewrite_query -> retrieve -> rerank -> grade
                ok   -> answer
                weak -> web_search -> answer from web
                          empty -> "I do not know..."

## Endpoint
POST /ask with corrective: true (default). force_mode="vector" to guarantee the
corrective branch runs (otherwise the router may send entity questions to graph).

## Grading
grade_by_rerank(chunks, threshold) uses the top rerank_score.
- If rerank_score present: ok iff top >= threshold (default 0.0).
- If missing (rerank off): falls back to cosine, threshold 0.5.
Rerank scores are logits, so threshold=0.0 is "any positive signal". Retune for
different corpora.

## Query rewriting
rewrite.py calls the chat model with a strict prompt: keep intent, expand acronyms,
add synonyms, one-line output. If the model returns the input unchanged, we skip
the retry to save cost.

## Web fallback
web_search.py uses duckduckgo-search (free, no API key). If the package isn't
installed or returns nothing, we return []. Note: DDG frequently returns empty
from inside containers due to rate-limiting; swap in Tavily/SerpAPI for production.

## Response
AskResponse now includes:
- source: one of {initial, rewrite, web, refuse, sql, graph, vector, hybrid}
- corrective_trace: list of strings describing each step

## Observed results
Weak query ("1987 Uruguay Round of GATT"):
    initial_retrieve:      top=-11.25  x
    rewrote_query:         "...Uruguay Round of the General Agreement on Tari..."
    retry_after_rewrite:   top=-10.29  x
    retrieval_weak -> web_fallback
    web_empty -> refuse
Strong query ("penalty if a company fails to remit"):
    initial_retrieve:      top=5.69   ok
    answered, cited chunk 70f405db

## Trade-offs
- (+) No more confident hallucinations from garbage retrieval.
- (+) Trace is transparent — every decision is auditable.
- (+) Rewrite is free when unneeded; only triggers on weak grades.
- (-) Weak query path costs 2 extra LLM calls (rewrite + web synthesis).
- (-) Corrective loop only runs on the vector branch; graph and sql are exempt.
- (-) DDG fallback is unreliable from containers.
- (-) Refusal is honest but not "helpful" — no escalation to human, no alternative source.

## Known issues
- graph mode answers are terse ("1.5 percent" with no citation). Future work:
  attach source chunk_ids from graph edge provenance.
- Vector fallback from sql branch still returns the failed SQL string.

## Files
- app/grader.py (new)
- app/rewrite.py (new)
- app/web_search.py (new)
- app/main.py (_run_vector_corrective, source + corrective_trace in AskResponse)
- app/schemas.py (corrective field, source, corrective_trace)
- app/config.py (corrective_threshold)
- requirements.txt (duckduckgo-search==6.3.5)