import json
import re

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


EXTRACT_PROMPT = """Extract factual (subject, relation, object) triples from the
text below. Focus on named entities (organisations, countries, laws, taxes, people,
dates) and the relations between them.

Return ONLY a JSON array. Each element: {{"subject": "...", "relation": "...", "object": "..."}}
Relation must be a short verb phrase in snake_case: "introduced_by", "applies_to",
"targets", "has_rate", "penalty_of", "effective_from", "administered_by".
Use at most 8 triples. No prose. No markdown.

Example output:
[{{"subject":"Kenya","relation":"introduced","object":"Digital Services Tax"}},
 {{"subject":"Digital Services Tax","relation":"has_rate","object":"1.5 percent"}}]

Text:
{text}

JSON:"""


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=8))
async def extract_triples(text: str) -> list[dict]:
    if not settings.graph_enabled:
        return []
    prompt = EXTRACT_PROMPT.format(text=text[:3000])
    async with httpx.AsyncClient(timeout=180.0) as client:
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
        raw = response.json()["message"]["content"].strip()
    # strip markdown fences if present
    if raw.startswith("```"):
        nl = raw.find("\n")
        if nl != -1:
            raw = raw[nl + 1:]
        if raw.rstrip().endswith("```"):
            raw = raw.rstrip()[:-3]
    # keep only the outer JSON array
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        data = json.loads(raw[start:end + 1])
    except Exception:
        return []
    clean: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        s = str(item.get("subject", "")).strip()
        r = str(item.get("relation", "")).strip().replace(" ", "_").lower()
        o = str(item.get("object", "")).strip()
        if s and r and o:
            clean.append({"subject": s, "relation": r, "object": o})
    return clean[:8]
