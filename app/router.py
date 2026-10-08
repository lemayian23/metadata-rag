import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


ROUTER_PROMPT = """You classify a user question into exactly one of four labels.

Labels:

- sql:    Answerable by counting, listing, aggregating, or filtering rows using
          ONLY the columns id, title, author, category, location, tags,
          published_at, created_at, token_count, chunk_index.
          Examples: "How many documents?", "List categories.", "Docs from Kenya?"

- vector: Answerable by semantic text lookup — what a document says, why, summaries.
          Examples: "What is the tax rate?", "Summarize the Kenya act."

- graph:  About RELATIONSHIPS between named entities.
          Examples: "Who introduced the digital tax?", "What does the Finance Act 2024 introduce?"
          "What is connected to Kenya Revenue Authority?"

- hybrid: Needs structured filters AND content answers, or graph AND content.
          Example: "How many finance documents discuss digital tax?"

Return exactly one lowercase word: sql, vector, graph, or hybrid. Nothing else.

Question: {question}

Label:"""


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=6))
async def classify(question: str) -> str:
    prompt = ROUTER_PROMPT.format(question=question)
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
        raw = response.json()["message"]["content"].strip().lower()
        for label in ("hybrid", "graph", "vector", "sql"):
            if label in raw:
                return label
        return "vector"
