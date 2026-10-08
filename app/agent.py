"""Plan-act-observe agent with heuristic plan seeding + LLM tool execution."""
import re

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.graph_retrieve import find_entities_in_query
from app.tools import TOOL_REGISTRY


SYNTH_PROMPT = """Answer the USER QUESTION using ONLY the evidence below.

CRITICAL RULES:
- Use every relevant fact found in the evidence.
- If the evidence does NOT contain the answer to a part of the question, explicitly
  say "the evidence does not contain X". Do not invent numbers, names, or facts.
- Cite chunk_ids or URLs where possible.
- Be concise.

USER QUESTION: {question}

Evidence:
{evidence}

Answer:"""


REFINE_PROMPT = """You have this evidence for the USER QUESTION:

USER QUESTION: {question}

Evidence so far:
{evidence}

Do you need another tool call to fully answer? Available tools:
- vector_search(<text>) : semantic lookup in local documents
- graph_query(<entity>) : local knowledge graph
- sql_query(<text>)     : structured queries over documents/chunks metadata
- direct_answer(<text>) : model's own knowledge, no retrieval

Reply on one line. Either:
NEED: <tool_name>(<argument>)
or
DONE"""


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=6))
async def _call_chat(prompt: str, timeout: float = 120.0) -> str:
    async with httpx.AsyncClient(timeout=timeout) as client:
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


_CALL_RE = re.compile(r"^(?P<name>[a-z_]+)\s*\(\s*(?P<arg>.*?)\s*\)\s*$", re.IGNORECASE)
_KV_RE = re.compile(r"^[a-z_]+\s*=\s*", re.IGNORECASE)


def _clean_arg(raw: str) -> str:
    s = raw.strip()
    s = _KV_RE.sub("", s, count=1).strip()
    while len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        s = s[1:-1].strip()
    return s


def _parse_tool_line(text: str) -> tuple[str | None, str]:
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.upper().startswith("NEED:"):
            s = s[5:].strip()
        if s.upper().startswith("TOOL:"):
            s = s[5:].strip()
        if s.upper() in ("DONE", "FINISH"):
            return "FINISH", ""
        m = _CALL_RE.match(s)
        if m:
            return m.group("name").lower(), _clean_arg(m.group("arg"))
        if s.lower() in TOOL_REGISTRY:
            return s.lower(), ""
    return None, ""


_SUBQ_SPLIT = re.compile(r"\s+and\s+|,\s+(?=[a-z])", re.IGNORECASE)
_COUNT_KW = re.compile(r"\b(how many|count|total|list|show all|which documents)\b", re.IGNORECASE)
_CONTENT_KW = re.compile(r"\b(what|why|how|explain|describe|summar|penalty|rate)\b", re.IGNORECASE)


def _split_subquestions(question: str) -> list[str]:
    q = question.strip().rstrip("?")
    parts = [p.strip() for p in _SUBQ_SPLIT.split(q) if p.strip()]
    return parts if parts else [question]


async def _heuristic_plan(question: str) -> list[tuple[str, str]]:
    """Return list of (tool_name, argument) executed in order."""
    parts = _split_subquestions(question)
    entities = []
    try:
        entities = await find_entities_in_query(question)
    except Exception:
        entities = []

    plan: list[tuple[str, str]] = []
    for part in parts:
        if _COUNT_KW.search(part):
            plan.append(("sql_query", part))
        elif _CONTENT_KW.search(part):
            plan.append(("vector_search", part))
        elif entities:
            plan.append(("graph_query", part))
        else:
            plan.append(("vector_search", part))

    # deduplicate, preserve order
    seen = set()
    unique: list[tuple[str, str]] = []
    for tool, arg in plan:
        key = (tool, arg.lower())
        if key not in seen:
            seen.add(key)
            unique.append((tool, arg))
    return unique


async def _execute_tool(
    tool_name: str, arg: str, session: AsyncSession
) -> dict:
    if tool_name not in TOOL_REGISTRY:
        return {"ok": False, "text": f"unknown tool {tool_name}", "data": {}}
    fn = TOOL_REGISTRY[tool_name]
    try:
        if tool_name == "vector_search":
            return await fn(session, arg, top_k=settings.default_top_k)
        return await fn(arg)
    except Exception as e:
        return {"ok": False, "text": f"tool exception: {e}", "data": {}}


async def run_agent(
    question: str,
    session: AsyncSession,
    max_steps: int = 6,
) -> dict:
    steps: list[dict] = []
    evidence_blocks: list[str] = []
    seen_calls: set[tuple[str, str]] = set()

    # --- Phase 1: heuristic plan ---
    heuristic = await _heuristic_plan(question)
    steps.append({
        "phase": "plan_heuristic",
        "plan": [{"tool": t, "arg": a} for t, a in heuristic],
    })

    for step_no, (tool_name, arg) in enumerate(heuristic[:max_steps], start=1):
        key = (tool_name, arg.lower())
        if key in seen_calls:
            continue
        seen_calls.add(key)

        result = await _execute_tool(tool_name, arg, session)
        steps.append({
            "step": step_no,
            "action": "tool_result",
            "tool": tool_name,
            "arg": arg,
            "ok": result.get("ok"),
            "preview": (result.get("text") or "")[:200],
        })

        if result.get("ok"):
            evidence_blocks.append(f"### {tool_name}({arg})\n{result.get('text', '')}")

    # --- Phase 2: LLM refine (add at most 2 more steps if useful) ---
    for refine_no in range(2):
        if len(steps) >= max_steps:
            break
        evidence_text = "\n\n".join(evidence_blocks)[:4000] or "(none yet)"
        prompt = REFINE_PROMPT.format(question=question, evidence=evidence_text)
        try:
            raw = await _call_chat(prompt, timeout=90.0)
        except Exception as e:
            steps.append({"action": "refine_error", "detail": str(e)})
            break

        tool_name, arg = _parse_tool_line(raw)
        steps.append({"action": "refine_plan", "tool": tool_name, "arg": arg})

        if tool_name == "FINISH" or tool_name is None:
            break
        if tool_name == "web_search":
            steps.append({"action": "blocked", "tool": "web_search",
                          "detail": "web_search disabled"})
            break

        key = (tool_name, arg.lower())
        if key in seen_calls:
            steps.append({"action": "skip_duplicate", "tool": tool_name})
            break
        seen_calls.add(key)

        result = await _execute_tool(tool_name, arg, session)
        steps.append({
            "action": "tool_result",
            "tool": tool_name,
            "arg": arg,
            "ok": result.get("ok"),
            "preview": (result.get("text") or "")[:200],
        })
        if result.get("ok"):
            evidence_blocks.append(f"### {tool_name}({arg})\n{result.get('text', '')}")

    if not evidence_blocks:
        return {
            "answer": "I could not gather enough evidence to answer.",
            "evidence_count": 0,
            "steps": steps,
        }

    synth_prompt = SYNTH_PROMPT.format(
        question=question,
        evidence="\n\n".join(evidence_blocks)[:6000],
    )
    try:
        final = await _call_chat(synth_prompt, timeout=180.0)
    except Exception as e:
        final = f"Synthesis failed: {e}"

    return {
        "answer": final,
        "evidence_count": len(evidence_blocks),
        "steps": steps,
    }