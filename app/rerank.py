import asyncio
from functools import lru_cache

from sentence_transformers import CrossEncoder

from app.config import settings


@lru_cache(maxsize=1)
def _load_model() -> CrossEncoder:
    return CrossEncoder(settings.rerank_model, device="cpu")


def _rerank_sync(query: str, chunks: list[dict], top_k: int) -> list[dict]:
    if not chunks:
        return []
    model = _load_model()
    pairs = [(query, item["chunk"].content) for item in chunks]
    scores = model.predict(pairs)
    for item, score in zip(chunks, scores):
        item["rerank_score"] = float(score)
    ranked = sorted(chunks, key=lambda x: x["rerank_score"], reverse=True)
    return ranked[:top_k]


async def rerank(query: str, chunks: list[dict], top_k: int) -> list[dict]:
    return await asyncio.to_thread(_rerank_sync, query, chunks, top_k)
