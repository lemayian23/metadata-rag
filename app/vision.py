import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


CAPTION_PROMPT = """Describe this image in 2-4 sentences for a retrieval system.

Include:
- What kind of image it is (photo, chart, diagram, table, scan).
- Any visible numbers, labels, titles, axis labels, or entity names.
- The subject matter in plain language.

Do NOT invent facts you cannot see. Do NOT answer questions. Only describe.
{hint}

Description:"""


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=10))
async def caption_image(image_bytes: bytes, hint: str | None = None) -> str:
    if not settings.multimodal_enabled:
        return "[multimodal disabled]"
    import base64
    b64 = base64.b64encode(image_bytes).decode("ascii")
    hint_line = f"\nHint from the uploader: {hint}" if hint else ""
    prompt = CAPTION_PROMPT.format(hint=hint_line)
    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.vision_model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [b64],
                    }
                ],
                "stream": False,
                "options": {"temperature": 0},
            },
        )
        response.raise_for_status()
        return response.json()["message"]["content"].strip()