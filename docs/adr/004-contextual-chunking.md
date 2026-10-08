# ADR-004 — Contextualize chunks before embedding

## Status
Accepted

## Context
Chunks lose document-level meaning when they are embedded in isolation. A chunk that says "the rate shall not exceed 1.5%" is not retrievable by a query that asks about "the Kenyan digital tax" because the country and subject are in an earlier chunk.

## Decision
Prepend an LLM-generated 1-2 sentence context to every chunk before embedding. Store both versions: content (enriched) and raw_content (original). Controlled by CONTEXTUAL_CHUNKING env var.

## Alternatives considered
- Larger chunks with more overlap: rejected — increases embedding cost and dilutes meaning.
- Overlapping sliding windows only: rejected — still cannot reference the parent document.
- Generate one summary per document (not per chunk): deferred — cheaper but coarser. Consider if ingest latency becomes a bottleneck.

## Consequences
- (+) Retrieval quality improves markedly on queries with pronouns and implicit references.
- (+) Citations now include document-level context, improving LLM answer quality.
- (-) Ingest latency grows linearly with chunk count.
- (-) Storage roughly doubles per chunk.
- (-) Requires the chat model to be available at ingest time.
