# Capability 10 — Agentic RAG

## Goal
Replace single-branch routing with an agent that plans multiple tool calls, executes
them, and synthesizes the results. Hybrid questions that need structured AND semantic
AND graph evidence no longer get half-answered.

## Endpoint
POST /agent { question, max_steps=6 }
Response: { answer, evidence_count, steps[] }

## Architecture — two-phase plan-act-observe

### Phase 1: heuristic plan seeding
_split_subquestions() splits the question on "and" / ", <lowercase>".
_heuristic_plan() assigns a tool per sub-question using regex:

  - \b(how many|count|total|list|show all|which documents)\b -> sql_query
  - \b(what|why|how|explain|describe|summar|penalty|rate)\b   -> vector_search
  - entity match in graph                                      -> graph_query
  - fallback                                                    -> vector_search

Rationale: the local 1.5B planner is unreliable at choosing tools. We seed the plan
with a deterministic rule and let the LLM do what it is good at — calling tools and
synthesizing text.

### Phase 2: LLM refinement
After phase 1, REFINE_PROMPT gives the model up to 2 additional steps if evidence is
missing. web_search is blocked in this phase — it is unreliable from the container.

## Tools (app/tools.py)
- vector_search(query)   -> retrieve + rerank + generate_answer
- graph_query(entity)    -> find entities + neighbors + format facts
- sql_query(text)        -> generate_sql + run_sql as rag_ro
- web_search(query)      -> DuckDuckGo (fallback only, often empty in container)
- direct_answer(query)   -> chat model, no retrieval

Every tool returns { tool, ok, text, data } for uniform handling.

## Safety
- sql_query runs under the rag_ro read-only role with the same regex guard from #5.
- Step budget caps total tool calls at max_steps.
- Duplicate calls (same tool + same argument) are rejected.
- web_search blocked in the refine phase.

## Observed results
Q: "How many documents do I have in total, and what penalty applies if a company
    fails to remit Kenya's digital services tax?"
plan_heuristic = [sql_query(count), vector_search(penalty)]
step 1: sql_query -> {"count": 5}
step 2: vector_search -> "5 percent per month [chunk_id=...]"
answer: "You have 5 documents in total. If a company fails to remit Kenya's digital
        services tax, they will be penalized with 5 percent per month."
evidence_count: 2

Q: "What is the digital services tax rate in Kenya?"
plan_heuristic = [vector_search(rate)]
answer: "The digital services tax rate in Kenya is 1.5 percent of gross transaction value."
evidence_count: 1

## Trade-offs
- (+) Multi-part questions get multi-part answers.
- (+) Plan is inspectable (steps[]).
- (+) Heuristic seeding is fast and deterministic; LLM only refines.
- (+) Inherits every safety mechanism from #5, #7, #8.
- (-) Not truly autonomous — heuristic limits coverage to the patterns it knows.
- (-) Extra LLM call(s) for refinement + one for synthesis.
- (-) Tool ordering is fixed by regex patterns; unusual phrasing may miss a branch.
- (-) web_search is effectively disabled here — production needs a keyed provider.

## Known issues
- Subquestion splitter uses a simple regex; "X and Y and Z" works, but "X as well as Y"
  is not split. Wider patterns are a future improvement.
- The refine phase sometimes re-proposes a duplicate; we reject and move on.

## Files
- app/agent.py (new)
- app/tools.py (new)
- app/main.py (POST /agent)
- app/schemas.py (AgentRequest, AgentResponse)