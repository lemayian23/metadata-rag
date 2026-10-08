"""Integration smoke tests. Hits the running app over HTTP.

Run inside the app container:
    docker compose exec app pytest -v

Requires the stack to be up (docker compose up -d) with data already ingested.
Tests that need real data will skip if the corpus is empty.
"""
import httpx
import pytest

BASE = "http://localhost:8000"
SLOW = 300.0  # LLM-heavy endpoints


async def _get(path: str, timeout: float = 30.0) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout) as c:
        return await c.get(f"{BASE}{path}")


async def _post(path: str, body: dict, timeout: float = 30.0) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout) as c:
        return await c.post(f"{BASE}{path}", json=body)


@pytest.mark.asyncio
async def test_health():
    r = await _get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_query_vector_mode():
    """#02, #03 — vector retrieval + optional rerank, no LLM answer."""
    r = await _post("/query", {
        "query": "digital services tax",
        "top_k": 3,
        "rerank": False,
        "answer": False,
        "search_mode": "vector",
    })
    assert r.status_code == 200
    body = r.json()
    assert "citations" in body
    assert isinstance(body["citations"], list)


@pytest.mark.asyncio
async def test_query_keyword_mode():
    """#01 — Postgres full-text path, keyword_score populated."""
    r = await _post("/query", {
        "query": "digital services tax",
        "top_k": 3,
        "rerank": False,
        "answer": False,
        "search_mode": "keyword",
    })
    assert r.status_code == 200
    body = r.json()
    for cit in body["citations"]:
        assert cit["keyword_score"] is not None


@pytest.mark.asyncio
async def test_query_hybrid_mode_has_rrf_fields():
    """#01 — RRF merge populates rrf_score and rank fields."""
    r = await _post("/query", {
        "query": "digital services tax",
        "top_k": 3,
        "rerank": False,
        "answer": False,
        "search_mode": "hybrid",
    })
    assert r.status_code == 200
    body = r.json()
    if not body["citations"]:
        pytest.skip("corpus empty")
    top = body["citations"][0]
    assert top["rrf_score"] is not None
    # at least one rank must be set
    assert top["vector_rank"] is not None or top["keyword_rank"] is not None


@pytest.mark.asyncio
async def test_ask_sql_mode():
    """#05 — SQL branch with count question."""
    r = await _post("/ask", {
        "question": "How many documents are in the database?",
        "force_mode": "sql",
    }, timeout=SLOW)
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "sql"
    assert body["sql"] is not None


@pytest.mark.asyncio
async def test_ask_vector_mode_has_support():
    """#08 — Self-RAG populates support on the vector branch."""
    r = await _post("/ask", {
        "question": "What is the digital services tax rate in Kenya?",
        "force_mode": "vector",
        "corrective": False,
    }, timeout=SLOW)
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "vector"
    assert body["support"] is not None
    assert "supported" in body["support"]


@pytest.mark.asyncio
async def test_ask_graph_mode():
    """#06 — Graph branch matches entities and returns an answer."""
    r = await _post("/ask", {
        "question": "Who introduced the Digital Services Tax?",
        "force_mode": "graph",
    }, timeout=SLOW)
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] in ("graph", "vector")  # graph may fall back if empty
    assert body["answer"]


@pytest.mark.asyncio
async def test_agent_returns_steps():
    """#10 — Agent produces a plan and at least one evidence item."""
    r = await _post("/agent", {
        "question": "What is the digital services tax rate in Kenya?",
        "max_steps": 3,
    }, timeout=SLOW)
    assert r.status_code == 200
    body = r.json()
    assert "steps" in body
    assert isinstance(body["steps"], list)
    assert len(body["steps"]) >= 1


@pytest.mark.asyncio
async def test_image_modality_filter():
    """#09 — Modality filter restricts results to image chunks."""
    r = await _post("/query", {
        "query": "test",
        "top_k": 5,
        "rerank": False,
        "answer": False,
        "modality": "image",
    })
    assert r.status_code == 200
    for cit in r.json()["citations"]:
        assert cit["modality"] == "image"