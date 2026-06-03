"""
/* ========================================================================== */
/* GEB L3: 知识路由                                                           */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI APIRouter/Depends、KnowledgeCreate、knowledge 服务与 common 序列化
 * [OUTPUT]: 对外提供 router，暴露 /api/v1/knowledge 入库与检索接口
 * [POS]: routers 的知识库资源边界，把前端配置转成 RAG 检索材料
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_session
from app.dependencies import get_seller_id
from app.routers.common import knowledge_item
from app.schemas import KnowledgeCreate
from app.services.knowledge import ingest_knowledge, search_knowledge


router = APIRouter(prefix="/api/v1")


@router.post("/knowledge", status_code=201)
def create_knowledge(
    payload: KnowledgeCreate,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    chunks = ingest_knowledge(
        session,
        seller_id,
        source_type=payload.source_type,
        source_ref=payload.source_ref,
        content=payload.content,
    )
    session.commit()
    return {"items": [knowledge_item(chunk, None) for chunk in chunks], "total": len(chunks)}


@router.get("/knowledge")
def list_knowledge(
    q: str,
    source_type: str | None = None,
    limit: int = 5,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    results = search_knowledge(session, seller_id, query=q, source_type=source_type, limit=limit)
    return {"items": results, "total": len(results)}
