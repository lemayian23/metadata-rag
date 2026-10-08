import asyncio

try:
    from duckduckgo_search import DDGS
    _DDG_AVAILABLE = True
except Exception:
    _DDG_AVAILABLE = False


def _search_sync(query: str, max_results: int) -> list[dict]:
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            })
    return results


async def web_search(query: str, max_results: int = 5) -> list[dict]:
    if not _DDG_AVAILABLE:
        return []
    try:
        return await asyncio.to_thread(_search_sync, query, max_results)
    except Exception:
        return []


def format_web_results(results: list[dict]) -> str:
    if not results:
        return ""
    lines = []
    for r in results:
        lines.append(f"- {r['title']} ({r['url']})\n  {r['snippet']}")
    return "\n".join(lines)