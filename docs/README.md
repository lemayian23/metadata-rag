# Metadata-RAG — System Documentation

A modular RAG platform built incrementally. Each capability is documented in `docs/capabilities/`. Architectural decisions are logged in `docs/adr/`.

## Capabilities

| # | Capability | Status | Doc |
|---|-----------|--------|-----|
| 01 | Hybrid Search RAG | done | capabilities/01_hybrid_search.md |
| 02 | Metadata-Filtered RAG | done | capabilities/02_metadata_filter.md |
| 03 | Reranking RAG | done | capabilities/03_reranking.md |
| 04 | Contextual Chunking RAG | done | capabilities/04_contextual_chunking.md |
| 05 | SQL + Vector RAG | done | capabilities/05_sql_vector_rag.md |
| 06 | Knowledge Graph + Vector RAG | done | capabilities/06_kg_vector_rag.md |
| 07 | Corrective RAG | done | capabilities/07_corrective_rag.md |
| 08 | Self-RAG | done | capabilities/08_self_rag.md |
| 09 | Multimodal RAG | done | capabilities/09_multimodal_rag.md |
| 10 | Agentic RAG | done | capabilities/10_agentic_rag.md |

## Stack

- FastAPI + SQLAlchemy async + asyncpg
- PostgreSQL 16 + pgvector (HNSW index)
- Ollama for embeddings (nomic-embed-text, 768-d) and chat (qwen2.5:1.5b)
- sentence-transformers CrossEncoder for reranking (ms-marco-MiniLM-L-6-v2)
- Docker Compose (db + app + huggingface cache volume)

## Data Flow

    POST /ingest
      content -> chunk_text() -> embed_texts() -> Chunk rows (pgvector)

    POST /query
      query -> [optional] extract_filters()
            -> retrieve_chunks()   # cosine similarity + SQL filters
            -> [optional] rerank() # cross-encoder
            -> generate_answer()   # Ollama chat
            -> citations
