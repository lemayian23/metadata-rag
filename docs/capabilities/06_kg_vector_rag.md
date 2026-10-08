# Capability 06 — Knowledge Graph + Vector RAG

## Goal
Answer questions about relationships between named entities that vector search
cannot traverse: "Who introduced the Digital Services Tax?",
"What does the Finance Act 2024 introduce?", "What is connected to Kenya Revenue Authority?"

## Architecture
  Postgres + pgvector  ->  text + embeddings (existing)
  Neo4j               ->  entity/relation graph (new)
  /ask router         ->  decides between sql, vector, graph, hybrid

## Endpoints
  POST /graph/backfill   extract triples for existing chunks, write to Neo4j
  POST /ask/graph        entities matched + facts + formatted graph text
  POST /ask              now supports mode: graph (auto-routed or via force_mode)

## Ingest pipeline addition
  chunk -> extract_triples()  (LLM, JSON-array output)
        -> write_triples()    (MERGE on entity names, append chunk_ids)

## Graph schema
  (:Entity {name}) -[:REL {type, chunk_ids, document_ids}]-> (:Entity)
  Unique constraint on Entity.name.
  Relations are merged; chunk_ids and document_ids accumulate across ingestions.

## Retrieval
  1. find_entities_in_query(): case-insensitive substring match against all Entity names.
  2. neighbors(): 1-2 hop traversal from matched entities.
  3. format_facts(): prints "subject --[relation]--> object" lines.
  4. _answer_from_graph(): feeds facts to the chat model with a grounded prompt.

## Router behaviour (evidence-based override)
After the LLM classifier picks a mode, /ask applies two heuristics:
- If the question contains a known entity AND the classifier said sql -> use graph.
- If the question contains a known entity AND the classifier said vector -> use hybrid.
This compensates for small-model router drift without hard-coding rules.

## Fallbacks
- sql fails on auto-route -> fall back to vector (preserves the failed SQL in the response for debugging).
- graph matches no entities -> fall back to vector.
- force_mode="sql" is respected strictly: no fallback, error is returned to the caller.

## Trade-offs
- (+) Multi-hop questions work that pure vector misses.
- (+) Graph facts carry provenance (chunk_ids), so we can link graph nodes back to source text.
- (+) Same router, same endpoint — the caller asks a natural question.
- (-) Ingest cost grows: one extra LLM call per chunk for triple extraction.
- (-) Small local models produce noisy triples ("penalty_of -> taxes"). Bigger extractor model improves quality.
- (-) Entity matching is exact substring; a proper linker is future work.

## Observed results
Backfill on 4 chunks: 19 triples written.
"What is connected to the Digital Services Tax?" -> 9 facts, ranked neighbours.
"Who introduced the Digital Services Tax?" -> routed to graph, answer "Kenya introduced the Digital Services Tax."

## Known issues
- Vector-fallback responses include the failed SQL string even when the answer succeeded.
  Tracked for a future "response hygiene" pass.
- Entity linker is substring-based; entities like "Kenya" match "Kenya Revenue Authority" too.
  Acceptable for now; a proper linker is future work.

## Files
- app/graph_extract.py (new)
- app/graph_store.py (new)
- app/graph_retrieve.py (new)
- app/main.py (graph ingest hook, /graph/backfill, /ask/graph, graph branch in /ask)
- app/router.py (fourth label: graph)
- app/config.py (neo4j_uri, neo4j_user, neo4j_password, graph_enabled)
- docker-compose.yml (neo4j service + neo4jdata volume)
- requirements.txt (neo4j==5.27.0)
