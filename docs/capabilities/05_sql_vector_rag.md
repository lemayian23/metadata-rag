# Capability 05 — SQL + Vector RAG

## Goal
Answer questions that need structured data (counts, lists, filters, aggregations)
alongside questions that need semantic retrieval over text — through one endpoint.

## Endpoint
POST /ask  { question, force_mode? }
force_mode: "sql" | "vector" | "hybrid" | null (auto)

Response: AskResponse { mode, answer, sql, sql_rows, sql_error, citations }

## Pipeline
  question
    -> router.classify()          # LLM decides sql / vector / hybrid
    -> sql:     sql_tool.generate_sql() -> run_sql() as rag_ro
    -> vector:  retrieve + rerank + generate_answer (existing #2-#4 path)
    -> hybrid:  both, then merged into one answer

## Safety design (defense in depth)
1. Separate read-only Postgres role rag_ro — has only SELECT on documents, chunks.
2. Regex guard in _is_safe_select() — single SELECT statement, no DML keywords.
3. SET LOCAL statement_timeout = 5000 — 5 s cap per query.
4. Row cap — LIMIT 100 automatically added if missing.
5. Schema allowlist — only documents and chunks exposed to the LLM.

## Router
Router prompt lists concrete examples per label. Priority on extraction:
hybrid > vector > sql. Defaults to "vector" if the response is unparseable.

## SQL cleaner
The chat model frequently emits markdown-fenced SQL (```sql ... ```).
_clean_sql() strips fences, language tags, backticks, and trailing semicolons
BEFORE validation. Otherwise _is_safe_select() rejects valid queries.

## Trade-offs
- (+) One endpoint handles structured, unstructured, and mixed questions.
- (+) rag_ro ensures the LLM cannot damage the DB even if the regex fails.
- (-) Router accuracy depends on the chat model; small local models still misclassify.
- (-) Each /ask in sql or hybrid mode costs one extra LLM call for SQL generation.

## Failure modes observed
- LLM emits ```sql fences -> rejected as unsafe. Fixed in _clean_sql().
- Semantic questions routed to sql when the router prompt is vague. Fixed by
  adding concrete examples per label and extraction priority.

## Files
- app/router.py (new)
- app/sql_tool.py (new)
- app/db.py (added readonly_engine + ReadonlySessionLocal)
- app/main.py (added /ask endpoint + _run_sql_branch + _run_vector_branch)
- app/schemas.py (AskRequest, AskResponse)
- app/config.py (readonly_database_url, sql_max_rows)
- migrations/003_readonly_role.sql
