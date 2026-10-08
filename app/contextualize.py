import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


CONTEXT_PROMPT = """You are helping a retrieval system. Below is a document and one of its chunks.
Write 1-2 sentences (max 60 words) that situate the chunk within the document.
Mention the document title, the subject, and anything the chunk refers to implicitly (pronouns, "the rate", "this policy", dates).
Do NOT repeat the chunk verbatim. Do NOT answer any question. Only provide the situating context.
Return only the 1-2 sentences, no preamble, no quotes.

Document title: {title}
Document metadata: category={category}, location={location}, author={author}

Document:
{document}

Chunk:
{chunk}
"""


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=8))
async def _contextualize_one(
    document_text: str,
    chunk: str,
    title: str | None,
    category: str | None,
    location: str | None,
    author: str | None,
) -> str:
    prompt = CONTEXT_PROMPT.format(
        title=title or "(untitled)",
        category=category or "(none)",
        location=location or "(none)",
        author=author or "(none)",
        document=document_text[:4000],
        chunk=chunk,
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
        data = response.json()
        return data["message"]["content"].strip()


async def contextualize_chunks(
    document_text: str,
    chunks: list[str],
    title: str | None = None,
    category: str | None = None,
    location: str | None = None,
    author: str | None = None,
) -> list[str]:
    if not settings.contextual_chunking:
        return list(chunks)
    enriched: list[str] = []
    for chunk in chunks:
        try:
            prefix = await _contextualize_one(
                document_text, chunk, title, category, location, author
            )
            enriched.append(f"[{prefix}]\n\n{chunk}")
        except Exception:
            enriched.append(chunk)
    return enriched
