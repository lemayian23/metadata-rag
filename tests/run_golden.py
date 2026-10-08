"""Golden Q/A regression runner.

Reads tests/golden.jsonl. For each entry, POSTs /ask and checks:
- If expect_contains is non-empty: every string must appear (case-insensitive).
- If expect_refusal is true: the answer must contain a refusal phrase.
- If known_failure is set: reported separately, not counted in pass/fail.

Waits for /health to respond before starting.

Run inside the app container:
    docker compose exec app python tests/run_golden.py
"""
import asyncio
import json
import sys
from pathlib import Path

import httpx

BASE = "http://localhost:8000"
GOLDEN = Path(__file__).parent / "golden.jsonl"
TIMEOUT = 300.0
STARTUP_TIMEOUT = 60.0

REFUSAL_PHRASES = (
    "do not know",
    "don't know",
    "not contain",
    "no relevant",
    "could not",
    "cannot find",
    "no information",
    "no matching records",
    "no records",
    "no results",
    "need more information",
)


def _is_refusal(answer: str) -> bool:
    a = answer.lower()
    return any(p in a for p in REFUSAL_PHRASES)


async def _wait_for_api(client: httpx.AsyncClient) -> bool:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + STARTUP_TIMEOUT
    while loop.time() < deadline:
        try:
            r = await client.get(f"{BASE}/health", timeout=3.0)
            if r.status_code == 200:
                print(f"[startup] API ready")
                return True
        except Exception:
            pass
        await asyncio.sleep(2.0)
    return False


async def run_one(client: httpx.AsyncClient, item: dict) -> dict:
    try:
        r = await client.post(
            f"{BASE}/ask",
            json={"question": item["question"]},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        body = r.json()
    except Exception as e:
        return {"id": item["id"], "status": "FAIL", "reason": f"request error: {e}"}

    answer = (body.get("answer") or "").lower()
    known = item.get("known_failure")

    if item.get("expect_refusal"):
        ok = _is_refusal(answer)
        reason = f"refused={ok} | answer[:120]={answer[:120]!r}"
        return {"id": item["id"], "status": "PASS" if ok else "FAIL", "reason": reason,
                "known_failure": known}

    missing = [s for s in item.get("expect_contains", []) if s.lower() not in answer]
    if missing:
        return {
            "id": item["id"],
            "status": "FAIL",
            "reason": f"missing: {missing} | answer[:120]={answer[:120]!r}",
            "known_failure": known,
        }
    return {"id": item["id"], "status": "PASS", "reason": f"mode={body.get('mode')}",
            "known_failure": known}


async def main() -> int:
    items = [json.loads(line) for line in GOLDEN.read_text().splitlines() if line.strip()]
    async with httpx.AsyncClient() as client:
        if not await _wait_for_api(client):
            print(f"[startup] API did not respond within {STARTUP_TIMEOUT:.0f}s")
            return 2

        results = []
        for item in items:
            res = await run_one(client, item)
            results.append(res)
            tag = res["status"]
            if res["status"] == "FAIL" and res.get("known_failure"):
                tag = "KNOWN"
            print(f"[{tag}] {res['id']}: {res['reason']}")

    passed = sum(1 for r in results if r["status"] == "PASS")
    known = sum(1 for r in results if r["status"] == "FAIL" and r.get("known_failure"))
    failed = sum(1 for r in results if r["status"] == "FAIL" and not r.get("known_failure"))
    total = len(results)
    print(f"\n{passed}/{total - known} passed, {known} known-failure, {failed} unexpected")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))