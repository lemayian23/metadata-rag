# ADR-008 — Add Self-RAG: retrieval decision and answer support verification

## Status
Accepted

## Context
Corrective RAG (#7) grades retrieval. It does not address two adjacent failure modes:

1. Retrieval happens for questions that don't need a corpus ("What is 2+2?").
   This wastes latency and can inject irrelevant context into an otherwise-correct answer.
2. The LLM can synthesize prose from parametric memory while presenting it as
   grounded in the chunks. Corrective RAG cannot detect this because it grades the
   retrieval, not the answer.

## Decision
Add two checks behind a self_rag flag (default on):
1. Retrieval decision: entity-first short-circuit + LLM classifier.
2. Support verification: LLM checks every claim in the answer against the retrieved text.
Expose needed_retrieval and support in the response. Do not auto-refuse on unsupported
claims — surface them and let the caller decide.

## Alternatives considered
- Do the retrieval decision with keyword heuristics only (e.g. "if it has a number,
  retrieve"): rejected — brittle, misses entity-bearing questions phrased differently.
- Always retrieve, skip decide: rejected — the whole point is not paying for retrieval
  when it isn't needed.
- Always refuse on unsupported: rejected — the verifier is imperfect at 1.5B, and
  false-positive refusals are worse than exposed warnings.
- Verify every branch, not just vector: rejected — sql and graph answers are grounded
  by construction. The verifier flagged "penalty_of" (which wasn't even in the answer)
  for a correct graph answer in testing.

## Consequences
- (+) Honest "no retrieval needed" path.
- (+) Verifiable answers on the vector branch.
- (+) Support is exposed in the API response, so downstream consumers can enforce
  their own policy (block, warn, retry).
- (-) Up to 2 extra LLM calls per /ask when self_rag=true.
- (-) Small models produce both false positives (verifier says unsupported when
  actually supported) and false negatives. Treated as advisory, not authoritative.
- (-) Branch policy is now more nuanced; documented in the capability file.