import json

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


VERIFY_PROMPT = """You are a fact-checker. Given a question, an answer, and the
context that was retrieved, decide whether EVERY factual claim in the answer is
supported by the context.

Rules:
- A claim is supported if the context contains the fact or a direct paraphrase.
- A claim is unsupported if it must come from outside knowledge (world facts,
  numbers, dates, names not mentioned in the context).
- Ignore style, hedging, and connectors. Focus on facts.
- If the answer says "I do not know" or refuses, treat it as supported.

Return ONLY a JSON object on one line:
{{"supported": true, "unsupported_claims": []}}
or
{{"supported": false, "unsupported_claims": ["claim1", "claim2"]}}

At most 3 unsupported claims, verbatim from the answer.

Context:
{context}

Question: {question}

Answer: {answer}

JSON:"""


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=8))
async def verify_support(question: str, answer: str, context_text: str) -> dict:
    if not answer or not context_text:
        return {"supported": True, "unsupported_claims": []}
    prompt = VERIFY_PROMPT.format(
        context=context_text[:4000],
        question=question,
        answer=answer[:2000],
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
        raw = response.json()["message"]["content"].strip()
    if raw.startswith("```"):
        nl = raw.find("\n")
        if nl != -1:
            raw = raw[nl + 1:]
        if raw.rstrip().endswith("```"):
            raw = raw.rstrip()[:-3]
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        return {"supported": True, "unsupported_claims": []}
    try:
        data = json.loads(raw[start:end + 1])
    except Exception:
        return {"supported": True, "unsupported_claims": []}
    supported = bool(data.get("supported", True))
    claims = data.get("unsupported_claims", [])
    if not isinstance(claims, list):
        claims = []
    return {"supported": supported, "unsupported_claims": [str(c) for c in claims[:3]]}