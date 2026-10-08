"""Agent tools. Each returns {"tool": name, "ok": bool, "text": str, "data": dict}."""
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.graph_retrieve import find_entities_in_query, neighbors, format_facts
from app.llm import generate_answer
from app.models import Chunk
from app.rerank import rerank
from app.retrieval import retrieve_chunks
from app.sql_tool import generate_sql, run_sql
from app.db import ReadonlySessionLocal
from app.web_search import web_search, format_web_results


async def vector_search(session: AsyncSession, query: str, top_k: int = 5) -> dict:
    try:
        candidates = await retrieve_chunks(
            session=session, query=query, filters=None, top_k=settings.rerank_candidates
        )
        chunks = await rerank(query, candidates, top_k=top_k)
        if not chunks:
            return {"tool": "vector_search", "ok": False, "text": "no chunks found", "data": {"chunks": []}}
        answer = await generate_answer(query, chunks)
        snippets = []
        for item in chunks[:3]:
            c = item["chunk"]
            snippets.append(f"[{c.id}] {(c.raw_content or c.content)[:200]}")
        return {
            "tool": "vector_search",
            "ok": True,
            "text": answer or "",
            "data": {"chunks": chunks, "snippets": snippets},
        }
    except Exception as e:
        return {"tool": "vector_search", "ok": False, "text": f"error: {e}", "data": {}}


async def graph_query(query: str) -> dict:
    try:
        entities = await find_entities_in_query(query)
        if not entities:
            return {"tool": "graph_query", "ok": False, "text": "no entities matched", "data": {}}
        facts = await neighbors(entities, max_hops=2)
        if not facts:
            return {"tool": "graph_query", "ok": False, "text": "no facts found", "data": {}}
        text = format_facts(facts)
        return {
            "tool": "graph_query",
            "ok": True,
            "text": text,
            "data": {"entities": entities, "facts": facts},
        }
    except Exception as e:
        return {"tool": "graph_query", "ok": False, "text": f"error: {e}", "data": {}}


async def sql_query(query: str) -> dict:
    try:
        async with ReadonlySessionLocal() as session:
            sql = await generate_sql(query)
            result = await run_sql(session, sql)
            if not result.get("ok"):
                return {
                    "tool": "sql_query",
                    "ok": False,
                    "text": result.get("error", "sql failed"),
                    "data": {"sql": result.get("sql_generated", sql)},
                }
            rows = result.get("rows", [])
            return {
                "tool": "sql_query",
                "ok": True,
                "text": json.dumps(rows[:10], default=str),
                "data": {"sql": result.get("sql"), "rows": rows},
            }
    except Exception as e:
        return {"tool": "sql_query", "ok": False, "text": f"error: {e}", "data": {}}


async def web_search_tool(query: str) -> dict:
    try:
        results = await web_search(query, max_results=5)
        if not results:
            return {"tool": "web_search", "ok": False, "text": "no web results", "data": {}}
        return {
            "tool": "web_search",
            "ok": True,
            "text": format_web_results(results),
            "data": {"results": results},
        }
    except Exception as e:
        return {"tool": "web_search", "ok": False, "text": f"error: {e}", "data": {}}


async def direct_answer(query: str) -> dict:
    try:
        from app.decide import answer_direct
        text = await answer_direct(query)
        return {"tool": "direct_answer", "ok": True, "text": text, "data": {}}
    except Exception as e:
        return {"tool": "direct_answer", "ok": False, "text": f"error: {e}", "data": {}}


TOOL_REGISTRY = {
    "vector_search": vector_search,
    "graph_query": graph_query,
    "sql_query": sql_query,
    "web_search": web_search_tool,
    "direct_answer": direct_answer,
}