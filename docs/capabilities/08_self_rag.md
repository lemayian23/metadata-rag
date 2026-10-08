# Capability 08 — Self-RAG

## Goal
Two questions the pipeline couldn't answer before:
1. Did we need retrieval at all, or does the LLM already know?
2. Is the generated answer actually supported by the retrieved context, or did the LLM
   blend in parametric memory?

## Endpoint changes
POST /ask gains:
- self_rag: bool = true        # toggle both steps
- needed_retrieval: bool        # in response
- support: {supported, unsupported_claims}  # in response
- mode: "direct"                # new mode when no retrieval was needed

## Step 1 — Retrieval decision (decide.py)
An entity-first short-circuit runs before the LLM classifier:
- If the question contains any entity known to the graph -> needs_retrieval = True
  (skips the LLM decision entirely).
- Otherwise, if self_rag is on and no force_mode was given, the chat model answers
  YES/NO on whether retrieval is needed.
- If NO, answer directly with mode="direct", no retrieval, no citations.

Rationale: a 1.5B model is unreliable as a binary classifier. The entity check
provides a hard floor — anything about a known entity always retrieves.

## Step 2 — Support verification (verify.py)
Only runs on the vector branch (graph and sql are grounded by construction).
The chat model receives question + answer + retrieved chunk text and returns:
    {"supported": true|false, "unsupported_claims": ["...", "..."]}
- If supported: pass through.
- If unsupported: expose the claims so the caller decides. We do NOT auto-refuse,
  because the 1.5B verifier sometimes produces false positives (see below).

## Branch policy
- direct  : no support check, no citations.
- sql     : support = supported by construction (rows came from the DB).
- graph   : support = supported by construction (facts came from extracted triples).
- vector  : verify with the LLM. support is authoritative here.
- hybrid  : verify only the vector sub-answer.

## Observed results
"2 + 2"                                    -> mode=sql, answer=4 (works via SELECT)
"What penalty if a company fails to remit?" -> mode=graph, support.supported=True
"Rate in Kenya + what did OECD say in 2023?" -> mode=vector,
    support.supported=False, unsupported_claims=["The OECD recommended..."]

## Trade-offs
- (+) No confident hallucination without a flag.
- (+) Honest "direct" path for questions the corpus shouldn't answer.
- (+) Verifier exposes exactly which claims lack evidence.
- (-) Two extra LLM calls when self_rag=true and retrieval is needed.
- (-) The verifier is imperfect at 1.5B params: earlier it flagged "penalty_of"
  as an unsupported claim that wasn't in the answer at all. Mitigation: only verify
  the vector branch, where the signal is meaningful.
- (-) The decide step frequently classifies arithmetic as "needs retrieval" on
  small models. It routes to sql and gets a correct answer anyway, so no harm.

## Known issues
- Graph answers can be shallow when the graph contains noisy triples. The extractor
  at 1.5B params sometimes creates wrong relations (e.g. "penalty_of -> taxes").
  Future work: rank graph facts by rerank score before synthesis, or use a bigger
  extraction model.
- Verifier false positives on edge cases with verbose unsupported_claims.
  Workaround: only act on support.supported when the response is not graph/sql.

## Files
- app/decide.py (new)
- app/verify.py (new)
- app/main.py (entity-first short-circuit, mode=direct, support attached per branch)
- app/schemas.py (AskRequest.self_rag, AskResponse.needed_retrieval, AskResponse.support)