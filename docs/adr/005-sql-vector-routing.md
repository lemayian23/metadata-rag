# ADR-005 — SQL + Vector routing via a single /ask endpoint

## Status
Accepted

## Context
Users ask two kinds of questions:
  - Structured: "How many docs from Kenya?", "List categories."
  - Semantic:   "What is the tax rate?", "Why was it introduced?"
Forcing everything through vector search wastes retrieval on questions
that a COUNT(*) answers exactly.

## Decision
Add POST /ask. It routes each question via an LLM classifier to sql,
vector, or hybrid, and runs the appropriate path. SQL runs under a
dedicated read-only role rag_ro, with a regex guard and a 5 s statement timeout.

## Alternatives considered
- Always run both and merge: rejected — doubles latency and cost for simple questions.
- Keyword-based router (if "how many" -> sql): rejected — brittle; real questions mix modes.
- Separate /sql and /vector endpoints: rejected — forces the caller to know the mode;
  the router exists precisely to spare the caller that decision.

## Consequences
- (+) One interface for all question types.
- (+) SQL is safely sandboxed — regex guard, read-only role, timeout, row cap.
- (-) Router is an LLM call; on small local models it sometimes misclassifies.
  Mitigation: force_mode override in the request for testing and critical paths.
- (-) Two DB roles to manage: rag (read-write) and rag_ro (read-only).
- (-) SQL generation needs the chat model to be available at query time.
