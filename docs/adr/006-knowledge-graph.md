# ADR-006 — Add Neo4j as a knowledge graph store alongside pgvector

## Status
Accepted

## Context
Vector retrieval returns passages ranked by similarity. It cannot answer
questions that require traversing explicit relationships between entities:
"Who introduced X?", "What does Y apply to?", "What is connected to Z?".
Without a graph, these questions fall back to semantic search, which returns
topically-similar passages but cannot guarantee the relational fact is present.

## Decision
Add Neo4j Community as a second data store.
At ingest, extract (subject, relation, object) triples via the local chat model
and write them to Neo4j. Add a graph retrieval path and route relational
questions to it via the /ask router.

## Alternatives considered
- Store triples in Postgres as a relational table: rejected — Cypher is far
  more ergonomic for variable-depth traversal.
- Skip the graph, rely on the LLM to reason over retrieved chunks: rejected —
  the LLM cannot traverse relationships not present in the top-K.
- Use an embedded graph (networkx) with persistence to disk: rejected — no
  multi-process access, no transactional writes, no Cypher.

## Consequences
- (+) Multi-hop relational queries become possible.
- (+) Graph edges carry chunk_ids, so graph answers can be traced to source text.
- (+) Same /ask interface — the caller does not need to know about the graph.
- (-) One more service in docker-compose (Neo4j), 512 MB heap by default.
- (-) Ingest latency grows: one extraction LLM call per chunk.
- (-) Triple quality depends on the extractor model. At 1.5B params the
  output contains noise; larger models produce cleaner triples.
- (-) Entity matching is substring-based; entity linking/disambiguation is
  deferred to a future capability.
