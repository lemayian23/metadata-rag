import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.prompt import SYSTEM_PROMPT, build_user_prompt


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def generate_answer(question: str, chunks) -> str:
    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.chat_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(question, chunks)},
                ],
                "stream": False,
                "options": {"temperature": 0},
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"]
