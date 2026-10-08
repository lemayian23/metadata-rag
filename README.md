# metadata-rag

A fully local 10-capability RAG platform built from scratch. No OpenAI, no
LangChain, no cloud. Runs on Ollama + PostgreSQL + pgvector + Neo4j inside
Docker on a laptop with 8 GB RAM.

## Capabilities

| #  | Capability                                                    | Endpoint                    |
|----|---------------------------------------------------------------|-----------------------------|
| 01 | Hybrid search (vector + tsvector + RRF)                       | `/query?search_mode=hybrid` |
| 02 | Metadata-filtered retrieval                                   | `/query`                    |
| 03 | Cross-encoder reranking                                       | `/query`                    |
| 04 | Contextual chunking                                           | `/ingest`                   |
| 05 | SQL + vector routing                                          | `/ask`                      |
| 06 | Knowledge graph + vector                                      | `/ask`, `/ask/graph`        |
| 07 | Corrective retrieval (grade -> rewrite -> web -> refuse)      | `/ask`                      |
| 08 | Self-RAG (retrieval decision + support verification)          | `/ask`                      |
| 09 | Multimodal ingest (image -> caption -> embed)                 | `/ingest/image`             |
| 10 | Agentic multi-tool planning                                   | `/agent`                    |

## Status

- **v1.0.0** - frozen, tested, documented
- **Golden suite:** 17/18 passed, 3 documented model-quality failures
- **Smoke tests:** 9 passed
- **Docs:** [ARCHITECTURE.md](docs/ARCHITECTURE.md) | [capabilities/](docs/capabilities) | [ADRs](docs/adr)

## Quick start

    docker compose up -d --build

    # in another window, pull the local models once:
    ollama pull nomic-embed-text
    ollama pull qwen2.5:1.5b
    ollama pull moondream

    curl http://localhost:8000/health

Full guide: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Why this exists

Most "RAG tutorials" stop at "retrieve a chunk and send it to an LLM." This
project implements the ten capabilities that separate that demo from a
production-grade pipeline: hybrid retrieval, reranking, contextual chunking,
metadata filters, structured + graph + semantic routing, corrective loops,
self-verification, multimodal ingest, and multi-tool agents. Each capability
has an ADR explaining what was tried and rejected, and a capability doc
describing its interface, trade-offs, and failure modes.

## Stack

FastAPI - PostgreSQL 16 + pgvector - Neo4j 5 - Ollama (nomic-embed-text,
qwen2.5:1.5b, moondream) - sentence-transformers - Docker Compose

## Tests

    docker compose exec app python -m pytest -v
    docker compose exec app python tests/run_golden.py

## License

MIT