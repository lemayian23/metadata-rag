import re
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


SCHEMA_DOC = """
Available tables (read-only):

documents(
  id UUID PRIMARY KEY,
  source TEXT,
  title TEXT,
  author TEXT,
  category TEXT,
  location TEXT,
  published_at TIMESTAMPTZ,
  tags TEXT[],
  meta JSONB,
  created_at TIMESTAMPTZ
)

chunks(
  id UUID PRIMARY KEY,
  document_id UUID REFERENCES documents(id),
  chunk_index INT,
  content TEXT,
  raw_content TEXT,
  token_count INT,
  meta JSONB,
  created_at TIMESTAMPTZ
)

Notes:
- Use PostgreSQL syntax.
- Join chunks to documents via chunks.document_id = documents.id.
- For text search on tags use the && operator (array overlap).
- Always add LIMIT.
"""


SQL_PROMPT = """You are a PostgreSQL expert. Given a schema and a question, write ONE
SELECT statement that answers it. Output ONLY the raw SQL text. Do NOT wrap it in
markdown fences. Do NOT prefix with "sql". Do NOT include comments or explanations.
Do NOT end with a semicolon. If the question cannot be answered with SQL, return
exactly: SELECT NULL;

Schema:
{schema}

Question: {question}

SQL:"""


_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|vacuum|analyze)\b",
    re.IGNORECASE,
)


def _clean_sql(raw: str) -> str:
    s = raw.strip()
    # strip markdown fences: ```sql ... ``` or ``` ... ```
    if s.startswith("```"):
        # drop opening fence line
        first_newline = s.find("\n")
        if first_newline != -1:
            s = s[first_newline + 1:]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    s = s.strip().strip("`").strip()
    # remove trailing semicolons and any trailing comments
    s = s.rstrip(";").strip()
    # collapse inner whitespace runs on the first line only, keep body intact
    return s


def _is_safe_select(raw: str) -> tuple[bool, str]:
    s = _clean_sql(raw)
    if not s:
        return False, "empty SQL"
    if not s.lower().lstrip().startswith("select"):
        return False, f"must start with SELECT (got: {s[:40]!r})"
    if ";" in s:
        return False, "multiple statements not allowed"
    if _FORBIDDEN.search(s):
        return False, "forbidden keyword"
    return True, s


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=8))
async def generate_sql(question: str) -> str:
    prompt = SQL_PROMPT.format(schema=SCHEMA_DOC, question=question)
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


async def run_sql(
    session: AsyncSession,
    sql: str,
    max_rows: int | None = None,
) -> dict[str, Any]:
    max_rows = max_rows or settings.sql_max_rows
    ok, safe_or_reason = _is_safe_select(sql)
    if not ok:
        return {"ok": False, "error": f"unsafe SQL: {safe_or_reason}", "rows": []}

    safe_sql = safe_or_reason
    if "limit" not in safe_sql.lower():
        safe_sql = f"{safe_sql} LIMIT {max_rows}"

    try:
        await session.execute(text("SET LOCAL statement_timeout = '5000'"))
        result = await session.execute(text(safe_sql))
        columns = list(result.keys())
        rows = [dict(zip(columns, row)) for row in result.fetchall()]
        return {"ok": True, "sql": safe_sql, "columns": columns, "rows": rows}
    except Exception as e:
        return {"ok": False, "error": str(e), "sql": safe_sql, "rows": []}
