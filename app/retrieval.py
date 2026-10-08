from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.embeddings import embed_query
from app.filters import build_filter_conditions
from app.models import Chunk, Document
from app.schemas import MetadataFilter


RRF_K = 60


async def _retrieve_vector(
    session: AsyncSession,
    query: str,
    filters: MetadataFilter | None = None,
    top_k: int | None = None,
    modality: str | None = None,
):
    top_k = top_k or settings.default_top_k
    query_embedding = await embed_query(query)

    conditions = build_filter_conditions(filters)
    if modality:
        conditions.append(Chunk.modality == modality)

    stmt = (
        select(
            Chunk,
            Document,
            Chunk.embedding.cosine_distance(query_embedding).label("distance"),
        )
        .join(Document, Chunk.document_id == Document.id)
        .where(*conditions)
        .order_by(Chunk.embedding.cosine_distance(query_embedding))
        .limit(top_k)
    )

    result = await session.execute(stmt)
    rows = result.all()

    chunks = []
    for chunk, document, distance in rows:
        chunks.append({
            "chunk": chunk,
            "document": document,
            "score": 1 - distance,
        })
    return chunks


async def _retrieve_keyword(
    session: AsyncSession,
    query: str,
    filters: MetadataFilter | None = None,
    top_k: int | None = None,
    modality: str | None = None,
):
    top_k = top_k or settings.default_top_k

    conditions = build_filter_conditions(filters)
    if modality:
        conditions.append(Chunk.modality == modality)

    ts_query = func.websearch_to_tsquery("english", query)
    rank_expr = func.ts_rank_cd(Chunk.content_tsv, ts_query)

    stmt = (
        select(Chunk, Document, rank_expr.label("rank"))
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.content_tsv.op("@@")(ts_query))
        .where(*conditions)
        .order_by(rank_expr.desc())
        .limit(top_k)
    )

    result = await session.execute(stmt)
    rows = result.all()

    chunks = []
    for chunk, document, rank in rows:
        chunks.append({
            "chunk": chunk,
            "document": document,
            "keyword_score": float(rank),
        })
    return chunks


def _rrf_merge(vector_hits: list[dict], keyword_hits: list[dict], top_k: int) -> list[dict]:
    scores: dict = {}
    by_id: dict = {}

    for rank, item in enumerate(vector_hits):
        cid = item["chunk"].id
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
        by_id.setdefault(cid, item)
        by_id[cid]["vector_rank"] = rank + 1

    for rank, item in enumerate(keyword_hits):
        cid = item["chunk"].id
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
        if cid not in by_id:
            by_id[cid] = item
        by_id[cid]["keyword_rank"] = rank + 1

    ordered = sorted(scores.keys(), key=lambda c: scores[c], reverse=True)
    merged = []
    for cid in ordered[:top_k]:
        item = by_id[cid]
        item["rrf_score"] = scores[cid]
        merged.append(item)
    return merged


async def _retrieve_hybrid(
    session: AsyncSession,
    query: str,
    filters: MetadataFilter | None = None,
    top_k: int | None = None,
    modality: str | None = None,
):
    top_k = top_k or settings.default_top_k
    vector_hits = await _retrieve_vector(session, query, filters, top_k, modality)
    keyword_hits = await _retrieve_keyword(session, query, filters, top_k, modality)
    return _rrf_merge(vector_hits, keyword_hits, top_k)


async def retrieve_chunks(
    session: AsyncSession,
    query: str,
    filters: MetadataFilter | None = None,
    top_k: int | None = None,
    modality: str | None = None,
    search_mode: str | None = None,
):
    """Dispatcher. search_mode: 'vector' | 'keyword' | 'hybrid'."""
    mode = search_mode or settings.search_mode
    if mode == "vector":
        return await _retrieve_vector(session, query, filters, top_k, modality)
    if mode == "keyword":
        return await _retrieve_keyword(session, query, filters, top_k, modality)
    return await _retrieve_hybrid(session, query, filters, top_k, modality)