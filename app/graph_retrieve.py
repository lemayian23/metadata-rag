from neo4j import AsyncGraphDatabase

from app.config import settings
from app.graph_store import get_driver


async def find_entities_in_query(query: str) -> list[str]:
    if not settings.graph_enabled:
        return []
    driver = get_driver()
    async with driver.session() as session:
        result = await session.run("MATCH (e:Entity) RETURN e.name AS name LIMIT 500")
        names = [record["name"] async for record in result]
    q = query.lower()
    hits: list[str] = []
    for name in names:
        if name and name.lower() in q:
            hits.append(name)
    return hits


async def neighbors(entity_names: list[str], max_hops: int = 2) -> list[dict]:
    if not settings.graph_enabled or not entity_names:
        return []
    driver = get_driver()
    facts: list[dict] = []
    async with driver.session() as session:
        for name in entity_names:
            cypher = (
                "MATCH path = (a:Entity {name: $name})-[r:REL*1.." + str(max_hops) + "]-(b:Entity) "
                "RETURN a.name AS subject, "
                "       [rel IN relationships(path) | rel.type] AS rels, "
                "       b.name AS object, "
                "       reduce(ids = [], rel IN relationships(path) | ids + rel.chunk_ids) AS chunk_ids "
                "LIMIT 50"
            )
            result = await session.run(cypher, name=name)
            async for record in result:
                facts.append({
                    "subject": record["subject"],
                    "relation": " -> ".join(record["rels"]),
                    "object": record["object"],
                    "chunk_ids": record["chunk_ids"],
                })
    return facts


def format_facts(facts: list[dict]) -> str:
    if not facts:
        return ""
    out_lines = []
    for f in facts:
        s = f.get("subject", "")
        r = f.get("relation", "")
        o = f.get("object", "")
        out_lines.append("- " + s + " --[" + r + "]--> " + o)
    return "\n".join(out_lines)
