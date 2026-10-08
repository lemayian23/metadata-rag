from app.config import settings


SYSTEM_PROMPT = """You are a production RAG assistant.
Answer only using the provided context.
If the context does not contain the answer, say you do not know.
Cite sources inline using [chunk_id].
Do not invent facts.
"""


def build_context(chunks) -> str:
    parts = []
    for item in chunks:
        chunk = item["chunk"]
        doc = item["document"]
        parts.append(
            f"[chunk_id={chunk.id}]\n"
            f"title={doc.title}\n"
            f"source={doc.source}\n"
            f"author={doc.author}\n"
            f"category={doc.category}\n"
            f"published_at={doc.published_at}\n"
            f"content:\n{chunk.content}\n"
        )
    return "\n---\n".join(parts)


def build_user_prompt(question: str, chunks) -> str:
    context = build_context(chunks)
    return f"""Context:
{context}

Question: {question}

Answer with citations:"""