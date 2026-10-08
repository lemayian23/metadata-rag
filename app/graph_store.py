from neo4j import AsyncGraphDatabase

from app.config import settings


_driver = None


def get_driver():
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
    return _driver


async def close_driver():
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


async def ensure_constraints() -> None:
    if not settings.graph_enabled:
        return
    driver = get_driver()
    async with driver.session() as session:
        await session.run(
            "CREATE CONSTRAINT entity_name IF NOT EXISTS "
            "FOR (e:Entity) REQUIRE e.name IS UNIQUE"
        )


async def write_triples(triples: list[dict], chunk_id: str, document_id: str) -> int:
    if not settings.graph_enabled or not triples:
        return 0
    driver = get_driver()
    written = 0
    async with driver.session() as session:
        for t in triples:
            await session.run(
                """
                MERGE (a:Entity {name: $subject})
                MERGE (b:Entity {name: $object})
                MERGE (a)-[r:REL {type: $relation}]->(b)
                ON CREATE SET r.chunk_ids = [$chunk_id], r.document_ids = [$document_id]
                ON MATCH SET r.chunk_ids = CASE
                    WHEN $chunk_id IN r.chunk_ids THEN r.chunk_ids
                    ELSE r.chunk_ids + $chunk_id
                END,
                r.document_ids = CASE
                    WHEN $document_id IN r.document_ids THEN r.document_ids
                    ELSE r.document_ids + $document_id
                END
                """,
                subject=t["subject"],
                object=t["object"],
                relation=t["relation"],
                chunk_id=chunk_id,
                document_id=document_id,
            )
            written += 1
    return written
