# Metadata-RAG — System Architecture

A production-shaped, fully local RAG platform. Nine documented capabilities
(#2–#10) layered on a shared core, running on Ollama + PostgreSQL + pgvector +
Neo4j, all inside Docker.

## 1. System at a glance

    Client
      |
      v
    FastAPI (app/main.py)
      |
      +-- /ingest             text  ingest      -> chunk -> context -> embed -> pgvector
      +-- /ingest/image       image ingest      -> caption -> embed -> pgvector
      +-- /query              retrieval only    -> filter -> retrieve -> rerank -> answer
      +-- /ask                routed pipeline   -> decide -> route -> branch -> answer
      +-- /agent              multi-tool agent  -> plan -> tools -> synthesize
      +-- /graph/backfill     one-shot graph population from existing chunks
      +-- /health

    Data stores
      - PostgreSQL 16 + pgvector   (documents, chunks, embeddings)
      - Neo4j 5                    (entities, relations, provenance)
      - Ollama                     (embeddings + chat + vision models)
      - HuggingFace cache volume   (cross-encoder reranker)

## 2. Model stack (all local)

| Purpose       | Model                                    | Size    | Dims |
|---------------|------------------------------------------|---------|------|
| Embeddings    | nomic-embed-text                         | 274 MB  | 768  |
| Chat / LLM    | qwen2.5:1.5b                             | 986 MB  |  -   |
| Reranker      | cross-encoder/ms-marco-MiniLM-L-6-v2     | ~80 MB  |  -   |
| Vision        | moondream                                | 1.7 GB  |  -   |

Everything runs on CPU. 8 GB RAM works; 16 GB is comfortable.

## 3. Data model

    documents
      id, source, title, author, category, location,
      published_at, tags[], meta JSONB, created_at

    chunks
      id, document_id, chunk_index,
      content       (enriched, embedded)
      raw_content   (original, for display)
      modality      (text | image | table | page)
      token_count, embedding vector(768), meta JSONB

    Neo4j
      (:Entity {name}) -[:REL {type, chunk_ids[], document_ids[]}]-> (:Entity)

Indexes:
  - B-tree on (category, author, location, published_at, modality)
  - GIN on tags and meta
  - HNSW on embedding (cosine)
  - Unique constraint on Entity.name in Neo4j

## 4. Capabilities — what each adds

| #  | Capability                | Adds                                                        | Files |
|----|---------------------------|-------------------------------------------------------------|-------|
| 02 | Metadata-Filtered RAG     | SQL WHERE clauses on top of vector similarity               | filters.py, retrieval.py |
| 03 | Reranking RAG             | Retrieve 50, cross-encoder rerank to 5                      | rerank.py |
| 04 | Contextual Chunking RAG   | LLM-generated doc summary prefix per chunk                  | contextualize.py |
| 05 | SQL + Vector RAG          | /ask router + read-only role + SQL safety guard             | router.py, sql_tool.py |
| 06 | Knowledge Graph + Vector  | Neo4j + triple extraction + graph retrieval                 | graph_*.py |
| 07 | Corrective RAG            | Grade -> rewrite -> web fallback -> refuse loop             | grader.py, rewrite.py, web_search.py |
| 08 | Self-RAG                  | Retrieval decision + support verification                   | decide.py, verify.py |
| 09 | Multimodal RAG            | Image ingest via caption-then-embed                         | vision.py |
| 10 | Agentic RAG               | Heuristic plan + multi-tool execution + synthesis           | agent.py, tools.py |

## 5. Request flow — the four entry points

### 5.1 /ingest (text)
    content
      -> chunk_text (tiktoken, 800/150)
      -> contextualize_chunks (chat model per chunk, prefixed to each chunk)
      -> embed_texts (nomic-embed-text, batched)
      -> INSERT chunks
    Notes: contextualization can be disabled via CONTEXTUAL_CHUNKING=false.
    Idempotent: no. Same content twice -> two documents.

### 5.2 /ingest/image
    image_base64
      -> vision.caption_image (moondream)
      -> embed caption
      -> INSERT chunks with modality="image"
    No image bytes stored. Only the caption.

### 5.3 /query (retrieval only)
    query + optional filters + optional modality
      -> [optional] extract_filters (LLM)
      -> retrieve_chunks (pgvector HNSW + SQL filters)
      -> rerank (cross-encoder)
      -> generate_answer (grounded prompt)
    Returns answer + citations with score and rerank_score.

### 5.4 /ask (routed)
    question
      -> decide: entity-first short-circuit, then LLM retrieval decision
      -> route: LLM classifier -> sql | vector | graph | hybrid
                 (override: entity match flips sql -> graph, vector -> hybrid)
      -> branch execution
           sql     : generate_sql + run_sql as rag_ro
           vector  : corrective loop (grade -> rewrite -> web -> refuse)
           graph   : find entities + neighbors + synthesize from facts
           hybrid  : run all three
      -> verify support (vector branch only; graph/sql are grounded by construction)
    Returns mode, source, answer, needed_retrieval, support, citations,
    corrective_trace.

### 5.5 /agent (multi-tool)
    question
      -> heuristic plan: split on "and" / ", <lc>", classify each part
      -> execute plan (sql, vector, graph) in order
      -> LLM refinement: up to 2 extra steps if evidence missing (web blocked)
      -> synthesize from all evidence
    Returns answer, evidence_count, steps[] with full audit trail.

## 6. Safety model

| Layer               | Mechanism                                            |
|---------------------|------------------------------------------------------|
| SQL execution       | Dedicated role `rag_ro` (SELECT only) + regex guard + 5 s timeout + row cap |
| SQL cleaning        | _clean_sql strips markdown fences before validation  |
| Filter injection    | SQLAlchemy parameter binding, no string concatenation |
| Corrective refuse   | If grade < threshold, rewrite then web then refuse  |
| Support verification| Only on vector branch; graph/sql marked supported by construction |
| Agent budget        | max_steps caps tool calls; duplicates rejected      |
| Agent web_search    | Blocked before step 3 and in the refine phase       |

## 7. Failure modes and mitigations

| Failure                                  | Capability | Mitigation |
|------------------------------------------|-----------|------------|
| Vector search misses exact-term queries  | 03        | Cross-encoder reranking |
| Chunk loses meaning out of context       | 04        | Contextual prefix |
| LLM hallucinates from garbage retrieval  | 07, 08    | Grade + refuse, support verification |
| Semantic question routed to SQL          | 05        | Evidence-based override (entity match) |
| Numeric/count question routed to vector  | 05        | Router examples for "how many" patterns |
| Small model plans poorly                 | 10        | Heuristic plan seeding |
| Small model invents missing facts        | 08, 10    | Strict synthesis prompt; honest "not in evidence" |
| DDG blocked from container               | 07, 10    | Refusal path; web_search blocked in agent |

## 8. Configuration surface (.env)

    DATABASE_URL, READONLY_DATABASE_URL
    OLLAMA_BASE_URL
    EMBEDDING_MODEL, CHAT_MODEL, VISION_MODEL, EMBEDDING_DIM
    RERANK_MODEL, RERANK_CANDIDATES, RERANK_TOP_K
    CHUNK_SIZE, CHUNK_OVERLAP, DEFAULT_TOP_K, MAX_CONTEXT_TOKENS
    CONTEXTUAL_CHUNKING
    SQL_MAX_ROWS
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, GRAPH_ENABLED
    CORRECTIVE_THRESHOLD
    MULTIMODAL_ENABLED

## 9. Deployment

    docker compose up -d --build
    Services: app, db (pgvector), neo4j

    First run:
      ollama pull nomic-embed-text
      ollama pull qwen2.5:1.5b
      ollama pull moondream

    Post-ingest (only once, if graph was enabled after data existed):
      POST /graph/backfill

    Ports: 8000 (app), 5432 (pg), 7474/7687 (neo4j)

## 10. What would come next

- Auth + API keys + rate limiting
- Alembic migrations instead of raw SQL
- Structured logging + OpenTelemetry
- Eval harness: golden Q/A pairs, regression on every capability change
- min_score threshold on /query to prevent low-relevance returns
- Table extractor (Docling) for modality="table"
- Streaming agent synthesis for long answers
- Real web search provider (Tavily/SerpAPI) behind a key
- Entity linking beyond substring match
- Fine-tuned planner to replace the heuristic in #10

## 11. Reference — all docs

Capabilities: `docs/capabilities/02..10`
ADRs:          `docs/adr/002..010`
This file:     `docs/ARCHITECTURE.md`