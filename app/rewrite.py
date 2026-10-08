import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


REWRITE_PROMPT = """Rewrite the user question to improve semantic retrieval.

Rules:
- Keep the same intent.
- Expand acronyms and add synonyms.
- Add the domain if obvious (tax, policy, finance).
- Return only the rewritten question, one line, no quotes, no preamble.

Original question: {question}

Rewritten:"""


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=6))
async def rewrite_query(question: str) -> str:
    prompt = REWRITE_PROMPT.format(question=question)
    async with httpx.AsyncClient(timeout=60.0) as client:
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
        rewritten = response.json()["message"]["content"].strip()
    if not rewritten or rewritten.lower() == question.lower():
        return question
    return rewritten[:500]