from app.config import settings


def grade_by_rerank(chunks: list[dict], threshold: float = 0.0) -> dict:
    """Fast, deterministic grading using rerank scores."""
    if not chunks:
        return {"ok": False, "reason": "no chunks", "top_score": None}
    top = chunks[0].get("rerank_score")
    if top is None:
        top = chunks[0].get("score", 0.0)
        threshold = 0.5
    ok = top >= threshold
    return {
        "ok": ok,
        "reason": f"top rerank_score={top:.3f} threshold={threshold}",
        "top_score": top,
    }