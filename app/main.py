from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import run_agent
from app.chunking import chunk_text, count_tokens
from app.config import settings
from app.contextualize import contextualize_chunks
from app.db import get_session, ReadonlySessionLocal
from app.decide import needs_retrieval, answer_direct
from app.embeddings import embed_texts
from app.filter_extractor import extract_filters
from app.graph_extract import extract_triples
from app.graph_retrieve import find_entities_in_query, neighbors, format_facts
from app.graph_store import ensure_constraints, write_triples
from app.grader import grade_by_rerank
from app.llm import generate_answer
from app.models import Chunk, Document
from app.rerank import rerank
from app.retrieval import retrieve_chunks
from app.rewrite import rewrite_query
from app.router import classify
from app.sql_tool import generate_sql, run_sql
from app.verify import verify_support
from app.vision import caption_image
from app.web_search import web_search, format_web_results
from app.schemas import (
    AgentRequest,
    AgentResponse,
    AskRequest,
    AskResponse,
    Citation,
    ImageIngestRequest,
    ImageIngestResponse,
    IngestRequest,
    IngestResponse,
    QueryRequest,
    QueryResponse,
    SupportInfo,
)

import re as _re

_RETRIEVAL_HINT = _re.compile(
    r"\b(image|picture|photo|diagram|chart|table|record|document|file|policy|act|"
    r"tax|rate|penalty|company|country|organisation|organization|who|when|where|"
    r"which|what)\b",
    _re.IGNORECASE,
)


def _should_retrieve_first(question: str) -> bool:
    if _re.search(r"\d", question):
        return True
    return bool(_RETRIEVAL_HINT.search(question))


app = FastAPI(title="Metadata-RAG + Hybrid + Reranking + Contextual + SQL + Graph + Corrective + Self-RAG + Multimodal + Agentic")


@app.on_event("startup")
async def _startup_graph():
    try:
        await ensure_constraints()
    except Exception as e:
        print(f"[graph] constraint setup skipped: {e}")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/ingest", response_model=IngestResponse)
async def ingest(payload: IngestRequest, session: AsyncSession = Depends(get_session)):
    document = Document(
        source=payload.source,
        title=payload.title,
        author=payload.author,
        category=payload.category,
        location=payload.location,
        published_at=payload.published_at,
        tags=payload.tags,
        meta=payload.meta,
    )
    session.add(document)
    await session.flush()

    raw_chunks = chunk_text(payload.content)
    if not raw_chunks:
        raise HTTPException(status_code=400, detail="No content to ingest")

    enriched_chunks = await contextualize_chunks(
        document_text=payload.content,
        chunks=raw_chunks,
        title=payload.title,
        category=payload.category,
        location=payload.location,
        author=payload.author,
    )

    embeddings = await embed_texts(enriched_chunks)

    for index, (raw, enriched, embedding) in enumerate(zip(raw_chunks, enriched_chunks, embeddings)):
        session.add(Chunk(
            document_id=document.id,
            chunk_index=index,
            content=enriched,
            raw_content=raw,
            modality="text",
            token_count=count_tokens(enriched),
            embedding=embedding,
            meta=payload.meta,
        ))

    await session.commit()
    return IngestResponse(document_id=document.id, chunks_created=len(raw_chunks))


@app.post("/ingest/image", response_model=ImageIngestResponse)
async def ingest_image(payload: ImageIngestRequest, session: AsyncSession = Depends(get_session)):
    import base64
    try:
        image_bytes = base64.b64decode(payload.image_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="image_base64 is not valid base64")

    caption = await caption_image(image_bytes, hint=payload.caption_hint)
    if not caption:
        raise HTTPException(status_code=502, detail="vision model returned empty caption")

    document = Document(
        source=payload.source,
        title=payload.title or "Uploaded image",
        author=payload.author,
        category=payload.category,
        location=payload.location,
        published_at=payload.published_at,
        tags=payload.tags,
        meta=payload.meta,
    )
    session.add(document)
    await session.flush()

    embeddings = await embed_texts([caption])
    chunk = Chunk(
        document_id=document.id,
        chunk_index=0,
        content=caption,
        raw_content=caption,
        modality="image",
        token_count=count_tokens(caption),
        embedding=embeddings[0],
        meta=payload.meta,
    )
    session.add(chunk)
    await session.commit()

    return ImageIngestResponse(
        document_id=document.id,
        chunk_id=chunk.id,
        modality="image",
        caption=caption,
    )


@app.post("/query", response_model=QueryResponse)
async def query(payload: QueryRequest, session: AsyncSession = Depends(get_session)):
    filters = payload.filters
    if payload.extract_filters:
        filters = await extract_filters(payload.query)

    final_k = payload.top_k or settings.default_top_k

    if payload.rerank:
        candidate_k = payload.rerank_candidates or settings.rerank_candidates
        chunks = await retrieve_chunks(
            session=session,
            query=payload.query,
            filters=filters,
            top_k=candidate_k,
            modality=payload.modality,
            search_mode=payload.search_mode,
        )
        chunks = await rerank(payload.query, chunks, top_k=final_k)
    else:
        chunks = await retrieve_chunks(
            session=session,
            query=payload.query,
            filters=filters,
            top_k=final_k,
            modality=payload.modality,
            search_mode=payload.search_mode,
        )

    if not chunks:
        return QueryResponse(
            answer="I do not know. No relevant context was found.",
            citations=[],
            used_filters=filters,
        )

    answer = await generate_answer(payload.query, chunks) if payload.answer else None

    citations = [
        Citation(
            chunk_id=item["chunk"].id,
            document_id=item["document"].id,
            title=item["document"].title,
            source=item["document"].source,
            content=item["chunk"].content,
            modality=item["chunk"].modality,
            score=item.get("score"),
            rerank_score=item.get("rerank_score"),
            rrf_score=item.get("rrf_score"),
            vector_rank=item.get("vector_rank"),
            keyword_rank=item.get("keyword_rank"),
            keyword_score=item.get("keyword_score"),
        )
        for item in chunks
    ]

    return QueryResponse(answer=answer, citations=citations, used_filters=filters)


# ---------- branch helpers ----------

async def _run_sql_branch(question: str) -> dict:
    async with ReadonlySessionLocal() as session:
        try:
            sql = await generate_sql(question)
        except Exception as e:
            return {"ok": False, "error": f"sql generation failed: {e}", "rows": []}
        result = await run_sql(session, sql)
        result["sql_generated"] = sql
        return result


async def _run_vector_branch(question: str, session, search_mode: str | None = None) -> dict:
    candidates = await retrieve_chunks(
        session=session,
        query=question,
        filters=None,
        top_k=settings.rerank_candidates,
        search_mode=search_mode,
    )
    chunks = await rerank(question, candidates, top_k=settings.default_top_k)
    answer = await generate_answer(question, chunks) if chunks else None
    return {"chunks": chunks, "answer": answer, "trace": [], "source": "vector"}


async def _run_vector_corrective(question: str, session, search_mode: str | None = None) -> dict:
    trace: list[str] = []

    candidates = await retrieve_chunks(
        session=session, query=question, filters=None,
        top_k=settings.rerank_candidates, search_mode=search_mode,
    )
    chunks = await rerank(question, candidates, top_k=settings.default_top_k)
    grade = grade_by_rerank(chunks, threshold=settings.corrective_threshold)
    trace.append(f"initial_retrieve: {grade['reason']}")

    if grade["ok"]:
        answer = await generate_answer(question, chunks) if chunks else None
        return {"chunks": chunks, "answer": answer, "trace": trace, "source": "initial"}

    rewritten = await rewrite_query(question)
    if rewritten != question:
        trace.append(f"rewrote_query: {rewritten[:120]}")
        candidates2 = await retrieve_chunks(
            session=session, query=rewritten, filters=None,
            top_k=settings.rerank_candidates, search_mode=search_mode,
        )
        chunks2 = await rerank(rewritten, candidates2, top_k=settings.default_top_k)
        grade2 = grade_by_rerank(chunks2, threshold=settings.corrective_threshold)
        trace.append(f"retry_after_rewrite: {grade2['reason']}")
        if grade2["ok"]:
            answer = await generate_answer(question, chunks2) if chunks2 else None
            return {"chunks": chunks2, "answer": answer, "trace": trace, "source": "rewrite"}
        chunks = chunks2
    else:
        trace.append("rewrite_skipped: no change")

    trace.append("retrieval_weak -> web_fallback")
    web = await web_search(question, max_results=5)
    if web:
        web_text = format_web_results(web)
        answer = await _answer_from_web(question, web_text)
        trace.append(f"web_results: {len(web)}")
        return {"chunks": chunks, "answer": answer, "trace": trace, "source": "web"}

    trace.append("web_empty -> refuse")
    return {
        "chunks": chunks,
        "answer": "I do not know. Retrieval was weak and web search found nothing relevant.",
        "trace": trace,
        "source": "refuse",
    }


async def _run_graph_branch(question: str) -> dict:
    entities = await find_entities_in_query(question)
    if not entities:
        return {"entities": [], "facts": [], "text": ""}
    facts = await neighbors(entities, max_hops=2)
    return {"entities": entities, "facts": facts, "text": format_facts(facts)}


async def _answer_from_graph(question: str, graph_data: dict) -> str:
    if not graph_data["facts"]:
        return "No graph facts found for that question."
    import httpx
    prompt = (
        "Use ONLY the facts below to answer the question. "
        "If the facts do not contain the answer, say so. Be concise.\n\n"
        f"Facts:\n{graph_data['text']}\n\n"
        f"Question: {question}\n\nAnswer:"
    )
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.chat_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0},
            },
        )
        response.raise_for_status()
        return response.json()["message"]["content"].strip()


async def _answer_from_web(question: str, web_text: str) -> str:
    import httpx
    prompt = (
        "Answer the question using ONLY the web search results below. "
        "Cite URLs in brackets. If the results do not answer, say so.\n\n"
        f"Search results:\n{web_text}\n\n"
        f"Question: {question}\n\nAnswer:"
    )
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.chat_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0},
            },
        )
        response.raise_for_status()
        return response.json()["message"]["content"].strip()


def _vector_citations(chunks) -> list[Citation]:
    return [
        Citation(
            chunk_id=item["chunk"].id,
            document_id=item["document"].id,
            title=item["document"].title,
            source=item["document"].source,
            content=item["chunk"].content,
            modality=item["chunk"].modality,
            score=item.get("score"),
            rerank_score=item.get("rerank_score"),
            rrf_score=item.get("rrf_score"),
            vector_rank=item.get("vector_rank"),
            keyword_rank=item.get("keyword_rank"),
            keyword_score=item.get("keyword_score"),
        )
        for item in chunks
    ]


def _context_text_from_chunks(chunks) -> str:
    parts = []
    for item in chunks:
        c = item["chunk"]
        parts.append(c.raw_content or c.content)
    return "\n---\n".join(parts)


async def _attach_support(question: str, answer: str | None, chunks) -> SupportInfo | None:
    if not answer or not chunks:
        return None
    context_text = _context_text_from_chunks(chunks)
    result = await verify_support(question, answer, context_text)
    return SupportInfo(
        supported=result.get("supported", True),
        unsupported_claims=result.get("unsupported_claims", []),
    )


# ---------- /ask ----------

@app.post("/ask", response_model=AskResponse)
async def ask(payload: AskRequest, session: AsyncSession = Depends(get_session)):
    trace: list[str] = []
    graph_entities_early = await find_entities_in_query(payload.question) if settings.graph_enabled else []
    if graph_entities_early:
        needed = True
        trace.append("decide: entity_match -> needs_retrieval=True")
    elif _should_retrieve_first(payload.question):
        needed = True
        trace.append("decide: heuristic_hint -> needs_retrieval=True")
    elif payload.self_rag and not payload.force_mode:
        needed = await needs_retrieval(payload.question)
        trace.append(f"decide: needs_retrieval={needed}")
        if not needed:
            direct = await answer_direct(payload.question)
            return AskResponse(
                mode="direct",
                source="direct",
                answer=direct,
                needed_retrieval=False,
                corrective_trace=trace,
            )
    else:
        needed = True

    graph_entities = await find_entities_in_query(payload.question) if settings.graph_enabled else []
    has_entity = len(graph_entities) > 0

    if payload.force_mode:
        mode = payload.force_mode
    else:
        mode = await classify(payload.question)
        trace.append(f"route: {mode}")
        if has_entity and mode == "sql":
            mode = "graph"
            trace.append("route_override: has_entity -> graph")
        elif has_entity and mode == "vector":
            mode = "hybrid"
            trace.append("route_override: has_entity -> hybrid")

    if mode == "sql":
        result = await _run_sql_branch(payload.question)
        if not result.get("ok"):
            if payload.force_mode == "sql":
                return AskResponse(
                    mode="sql",
                    source="sql",
                    answer="I could not run a SQL query for that question.",
                    needed_retrieval=needed,
                    sql=result.get("sql_generated"),
                    sql_error=result.get("error"),
                    corrective_trace=trace,
                )
            v = await _run_vector_branch(payload.question, session, search_mode=payload.search_mode)
            support = await _attach_support(payload.question, v["answer"], v["chunks"])
            return AskResponse(
                mode="vector",
                source=v["source"],
                answer=v["answer"],
                needed_retrieval=needed,
                support=support,
                citations=_vector_citations(v["chunks"]),
                sql=result.get("sql_generated"),
                sql_error=result.get("error"),
                corrective_trace=trace,
            )
        return AskResponse(
            mode="sql",
            source="sql",
            answer=_summarize_sql_rows(payload.question, result["rows"]),
            needed_retrieval=needed,
            support=SupportInfo(supported=True, unsupported_claims=[]) if payload.self_rag else None,
            sql=result.get("sql"),
            sql_rows=result["rows"],
            corrective_trace=trace,
        )

    if mode == "graph":
        g = await _run_graph_branch(payload.question)
        if not g["facts"]:
            v = await _run_vector_branch(payload.question, session, search_mode=payload.search_mode)
            support = await _attach_support(payload.question, v["answer"], v["chunks"])
            return AskResponse(
                mode="vector",
                source=v["source"],
                answer=v["answer"],
                needed_retrieval=needed,
                support=support,
                citations=_vector_citations(v["chunks"]),
                corrective_trace=trace,
            )
        answer = await _answer_from_graph(payload.question, g)
        support = SupportInfo(supported=True, unsupported_claims=[]) if payload.self_rag else None
        return AskResponse(
            mode="graph",
            source="graph",
            answer=answer,
            needed_retrieval=needed,
            support=support,
            corrective_trace=trace,
        )

    if mode == "vector":
        if payload.corrective:
            v = await _run_vector_corrective(payload.question, session, search_mode=payload.search_mode)
        else:
            v = await _run_vector_branch(payload.question, session, search_mode=payload.search_mode)
        trace.extend(v["trace"])
        support = await _attach_support(payload.question, v["answer"], v["chunks"]) if payload.self_rag else None
        return AskResponse(
            mode="vector",
            source=v["source"],
            answer=v["answer"],
            needed_retrieval=needed,
            support=support,
            citations=_vector_citations(v["chunks"]),
            corrective_trace=trace,
        )

    # hybrid
    sql_result = await _run_sql_branch(payload.question)
    if payload.corrective:
        v = await _run_vector_corrective(payload.question, session, search_mode=payload.search_mode)
    else:
        v = await _run_vector_branch(payload.question, session, search_mode=payload.search_mode)
    trace.extend(v["trace"])
    g = await _run_graph_branch(payload.question)

    graph_answer = await _answer_from_graph(payload.question, g) if g["facts"] else None
    combined = _combine_hybrid_answer(v["answer"], graph_answer, sql_result)
    support = await _attach_support(payload.question, v["answer"], v["chunks"]) if payload.self_rag else None
    return AskResponse(
        mode="hybrid",
        source=f"vector:{v['source']}+graph+sql",
        answer=combined,
        needed_retrieval=needed,
        support=support,
        sql=sql_result.get("sql") if sql_result.get("ok") else sql_result.get("sql_generated"),
        sql_rows=sql_result.get("rows", []) if sql_result.get("ok") else [],
        sql_error=sql_result.get("error") if not sql_result.get("ok") else None,
        citations=_vector_citations(v["chunks"]),
        corrective_trace=trace,
    )


def _summarize_sql_rows(question: str, rows: list) -> str:
    if not rows:
        return "No matching records."
    import json as _json
    preview = rows[:10]
    if len(rows) == 1 and len(rows[0]) == 1:
        key, value = next(iter(rows[0].items()))
        if "count" in str(key).lower():
            return f"There are {value} matching records/documents in the database."
    return f"Found {len(rows)} result(s). First {len(preview)}: " + _json.dumps(preview, default=str)


def _combine_hybrid_answer(vector_answer, graph_answer, sql_result) -> str:
    import json as _json
    parts = []
    if graph_answer:
        parts.append("From knowledge graph:\n" + graph_answer)
    if vector_answer:
        parts.append("From documents:\n" + vector_answer)
    if sql_result.get("ok"):
        rows = sql_result.get("rows", [])
        parts.append(f"From database ({len(rows)} row(s)):\n" + _json.dumps(rows[:10], default=str))
    elif sql_result.get("error"):
        parts.append("Structured query failed: " + sql_result["error"])
    return "\n\n".join(parts) if parts else "No answer produced."


@app.post("/graph/backfill", response_model=dict)
async def graph_backfill(session: AsyncSession = Depends(get_session)):
    from sqlalchemy import select as _select
    from app.models import Chunk as _Chunk
    result = await session.execute(_select(_Chunk))
    chunks = result.scalars().all()
    total = 0
    for c in chunks:
        triples = await extract_triples(c.raw_content or c.content)
        total += await write_triples(triples, str(c.id), str(c.document_id))
    return {"chunks_processed": len(chunks), "triples_written": total}


@app.post("/ask/graph", response_model=dict)
async def ask_graph(payload: AskRequest):
    branch = await _run_graph_branch(payload.question)
    return {
        "entities_matched": branch["entities"],
        "facts": branch["facts"],
        "graph_text": branch["text"],
    }


@app.post("/agent", response_model=AgentResponse)
async def agent_endpoint(payload: AgentRequest, session: AsyncSession = Depends(get_session)):
    result = await run_agent(payload.question, session, max_steps=payload.max_steps)
    return AgentResponse(
        answer=result["answer"],
        evidence_count=result["evidence_count"],
        steps=result["steps"],
    )