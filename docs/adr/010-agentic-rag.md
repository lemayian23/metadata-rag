# ADR-010 — Agentic RAG with heuristic plan seeding

## Status
Accepted

## Context
The router in #5 picks ONE branch (sql, vector, graph, or hybrid) per question.
Multi-part questions ("how many X, and what does the policy say about Y?") get
half-answered because the router commits to a single tool.

A pure LLM planner was tried first: ask the chat model to output
"TOOL: <name>(<arg>)" step by step. At 1.5B parameters, the planner:
- Hallucinated queries unrelated to the question.
- Looped on failing tools.
- Selected web_search (unavailable) first.
- Produced key=value syntax that the parser had to strip.

## Decision
Seed the plan with a deterministic heuristic, then let the LLM refine:

1. Split the question into sub-questions on "and" and ", <lowercase>".
2. Classify each sub-question with regex patterns:
   - Count/list questions -> sql_query
   - Content questions -> vector_search
   - Entity mentions -> graph_query
3. Execute the plan in order.
4. Then let the LLM suggest up to 2 additional steps if evidence is still missing
   (web_search blocked).

## Alternatives considered
- Pure LLM planner: rejected — unreliable at 1.5B, loops on failures.
- Pure heuristic, no LLM refinement: rejected — misses follow-ups when the
  sub-question splitter mis-parses.
- LangGraph: rejected for this stage — the dependency and abstraction cost
  outweighed the gain over ~150 lines of plain Python.

## Consequences
- (+) Multi-part questions work: verified on "how many docs + penalty".
- (+) Plan is deterministic and auditable (steps[]).
- (+) LLM is used where it is strong (tool arg selection, synthesis), not where it
  is weak (global planning).
- (-) Coverage limited to what the regex patterns recognize. Exotic phrasing may
  fall through to vector_search.
- (-) Fixed ordering can be suboptimal; SQL-then-vector is fine for the current
  patterns, less so for questions that need graph first.
- (-) Two extra LLM calls per /agent (refine + synthesis) on top of the tool calls.

## Future work
- Replace regex patterns with a small fine-tuned classifier.
- Add a proper graph first-class plan path for entity-centric questions.
- Streaming synthesis for long answers.
- Add human-in-the-loop approval before any mutating tool (none exist yet).