"""
/* ========================================================================== */
/* GEB L3: 轻量知识检索                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy Session、app.models.KnowledgeChunk、embedding_providers、knowledge_index_providers 与 knowledge_search_providers
 * [OUTPUT]: 对外提供 chunk_text、embed_text、embed_texts、ingest_knowledge、search_knowledge
 * [POS]: services 的知识切块与检索服务，只消费 embedding provider 和 search provider 协议，不绑定具体模型或索引
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.services.embedding_providers import EmbeddingProvider
from app.services.embedding_providers import embed_texts as embed_with_provider
from app.services.knowledge_index_providers import KnowledgeIndexProvider, sync_knowledge_index
from app.services.knowledge_search_providers import KnowledgeSearchProvider, get_knowledge_search_provider


def chunk_text(text: str, *, max_chars: int = 800, overlap: int = 120) -> list[str]:
    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not normalized:
        raise ValueError("content is required")
    if max_chars <= overlap:
        raise ValueError("max_chars must be greater than overlap")

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + max_chars, len(normalized))
        if end < len(normalized):
            split_at = normalized.rfind("\n", start, end)
            if split_at <= start:
                split_at = normalized.rfind(" ", start, end)
            if split_at > start + max_chars // 2:
                end = split_at
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(end - overlap, 0)
    return chunks


def embed_text(text: str, *, provider: EmbeddingProvider | None = None) -> list[float]:
    return embed_texts([text], provider=provider)[0]


def embed_texts(texts: list[str], *, provider: EmbeddingProvider | None = None) -> list[list[float]]:
    return embed_with_provider(texts, provider=provider)


def ingest_knowledge(
    session: Session,
    seller_id: int,
    *,
    source_type: str,
    source_ref: str | None,
    content: str,
    provider: EmbeddingProvider | None = None,
    index_provider: KnowledgeIndexProvider | None = None,
) -> list[models.KnowledgeChunk]:
    records: list[models.KnowledgeChunk] = []
    chunks = chunk_text(content)
    vectors = embed_texts(chunks, provider=provider)
    for chunk, vector in zip(chunks, vectors, strict=True):
        record = models.KnowledgeChunk(
            seller_id=seller_id,
            source_type=source_type,
            source_ref=source_ref,
            content=chunk,
            embedding=vector,
        )
        session.add(record)
        records.append(record)
    session.flush()
    index_sync = sync_knowledge_index(records, provider=index_provider)
    session.add(
        models.AuditLog(
            seller_id=seller_id,
            actor="system",
            action_type="knowledge_ingested",
            target_type="knowledge_chunk",
            target_id=records[0].id if records else None,
            is_auto=True,
            snapshot={"source_type": source_type, "source_ref": source_ref, "chunks": len(records), "index_sync": index_sync},
        )
    )
    return records


def search_knowledge(
    session: Session,
    seller_id: int,
    *,
    query: str,
    source_type: str | None = None,
    limit: int = 5,
    provider: EmbeddingProvider | None = None,
    search_provider: KnowledgeSearchProvider | None = None,
) -> list[dict]:
    if not query.strip():
        raise ValueError("query is required")
    limit = min(max(limit, 1), 20)
    query_vector = embed_text(query, provider=provider)

    statement = select(models.KnowledgeChunk).where(models.KnowledgeChunk.seller_id == seller_id)
    if source_type:
        statement = statement.where(models.KnowledgeChunk.source_type == source_type)

    provider_impl = search_provider or get_knowledge_search_provider()
    chunks = session.scalars(statement).all()
    return provider_impl.search(query, query_vector, chunks, limit=limit)
