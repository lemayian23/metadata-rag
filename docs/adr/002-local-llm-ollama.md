# ADR-002 — Use Ollama for embeddings and chat

## Status
Accepted

## Context
Original stack assumed OpenAI API. No credits available. Need a fully free, fully local stack that runs on Windows + Docker Desktop.

## Decision
Run Ollama on the Windows host. Containers reach it via host.docker.internal:11434.
- Embeddings: nomic-embed-text (768-d, ~274 MB)
- Chat: qwen2.5:1.5b (Q4, ~1 GB, CPU-friendly)

## Consequences
- (+) Zero cost, zero network, private.
- (+) Same interface as OpenAI — swap required only embeddings.py and llm.py.
- (-) Slower: 5-30 s per answer on CPU vs ~2 s for gpt-4o-mini.
- (-) Embedding dim changed 1536 -> 768, forcing a DB wipe.
- (-) Quality lower than frontier models; acceptable for learning and most retrieval tasks.
