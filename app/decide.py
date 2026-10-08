import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


DECIDE_PROMPT = """You decide whether answering the question requires looking up
information from an external knowledge base or database.

Answer YES if the question is about ANY of:
- A specific document, law, policy, tax, fee, penalty, rate, or filing.
- A specific organisation, country, company, or jurisdiction.
- Numbers, dates, names, or counts that would come from stored records.
- Anything that mentions a named entity, even if the question is also general.

Answer NO only if the question is truly universal and cannot depend on a corpus:
- Pure arithmetic ("what is 2+2", "what is 15% of 80").
- Grammar, definitions of common words, or basic science.
- Chat meta ("who are you?", "say hello").

When in doubt, answer YES.

Return exactly one word: YES or NO. Nothing else.

Question: {question}

Answer:"""


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=6))
async def needs_retrieval(question: str) -> bool:
    prompt = DECIDE_PROMPT.format(question=question)
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
        raw = response.json()["message"]["content"].strip().upper()
    return raw.startswith("YES")


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=6))
async def answer_direct(question: str) -> str:
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.chat_model,
                "messages": [{"role": "user", "content": question}],
                "stream": False,
                "options": {"temperature": 0},
            },
        )
        response.raise_for_status()
        return response.json()["message"]["content"].strip()