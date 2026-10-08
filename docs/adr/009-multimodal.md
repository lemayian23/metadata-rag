# ADR-009 — Multimodal RAG via caption-then-embed, not multimodal embeddings

## Status
Accepted

## Context
Documents contain images, charts, tables, and scanned pages. We need to retrieve
over them alongside text. Two mainstream approaches exist:

A. Multimodal embedding models (CLIP, ImageBind, jina-clip) produce vectors in a
   shared space with text — one index, native cross-modal retrieval.
B. Caption images at ingest with a vision LLM, then embed the caption and reuse
   the existing text pipeline.

## Decision
Approach B. Caption with moondream (local, 828 MB) at ingest, embed the caption
with nomic-embed-text, store as a chunk with modality="image".

## Alternatives considered
- Approach A (CLIP): rejected for this stage. It requires a separate embedding
  model, a separate index (or a much larger one with cross-modal alignment), and
  the retrieval quality on our tiny corpus doesn't justify the operational cost.
- Skip images entirely: rejected — real documents mix modalities.
- Store bytes and use a dedicated vision retrieval path at query time: rejected —
  blows up latency (vision model on every query) and duplicates the retrieval index.

## Consequences
- (+) Zero new infrastructure. Same pgvector index, same reranker, same filters.
- (+) Same API shape: an image citation looks like a text citation, with caption
  as content.
- (+) Fits 8 GB RAM machines.
- (+) Multimodal retrieval automatically inherits #2-#8 (metadata filters,
  reranking, corrective loop, self-RAG).
- (-) Retrieval is bounded by caption quality. Nuanced visual questions
  ("show me the rising trend") do not work as well as with native cross-modal
  embeddings.
- (-) Image bytes are discarded after captioning; the original is not stored.
- (-) modality filter does not imply a relevance floor; callers may want a
  min_score check.

## Future
- Add asset BYTEA for image display.
- Swap moondream for llava:7b if quality becomes a bottleneck.
- Consider a table-specific extractor (Docling) rather than relying on captions.
- Add min_score parameter to /query.