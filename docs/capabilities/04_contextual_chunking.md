# Capability 04 — Contextual Chunking RAG

## Goal
Make each chunk self-contained by prepending an LLM-generated summary of its parent document before embedding.

## Why
A chunk like "The rate shall not exceed 1.5%..." is ambiguous on its own. Without context, its embedding is diluted and the LLM cannot resolve pronouns or implicit references.

## Technique
Based on Anthropic Contextual Retrieval. Adapted to run locally via Ollama.
For each chunk:
  1. Take the parent document + document metadata + the chunk.
  2. Ask the chat model for 1-2 sentences situating the chunk in the document.
  3. Prepend as "[prefix]\n\n<chunk>" before embedding.

## Storage
- chunks.content       = enriched text (used for embedding and citation)
- chunks.raw_content   = original chunk (kept for display / debugging)

## Endpoint
No new endpoint. Behaviour is controlled by env var CONTEXTUAL_CHUNKING.

## Config
- CONTEXTUAL_CHUNKING=true|false (default true)
- Uses CHAT_MODEL (qwen2.5:1.5b) for the prefix generation.

## Cost
- Ingest: +5-20 s per chunk (one chat call per chunk).
- Storage: ~2x text per chunk (raw + enriched).
- Query: unchanged.

## Fallback
If the chat call fails for any chunk, contextualize.py silently falls back to the raw chunk. Ingest never breaks because of a bad LLM call.

## Observed results
Query: "What happens if a company fails to remit this tax?"
- Enriched chunk: rerank_score = -1.48 (rank 1)
- Un-enriched old chunk: rerank_score = -9.76 (rank 2)
The cross-encoder strongly prefers the contextualized version.

## Known issue
The chat model occasionally cites the wrong chunk_id in its answer text (picks a different context block ID than the one containing the answer). Retrieval is correct; only the citation string is off. Tracked for a later citation-fidelity pass.

## Files
- app/contextualize.py (new)
- app/config.py (contextual_chunking flag)
- app/models.py (raw_content column)
- app/main.py (ingest calls contextualize_chunks)
- migrations/002_contextual_chunking.sql
