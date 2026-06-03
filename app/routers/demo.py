"""
/* ========================================================================== */
/* GEB L3: Demo 场景路由                                                      */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI APIRouter/Depends、租户依赖、SQLAlchemy Session 与 demo seed 服务
 * [OUTPUT]: 对外提供 router，暴露 /api/v1/demo/seed 确定性演示数据入口
 * [POS]: routers 的演示辅助边界，让 Demo 主链路能一键生成可审阅数据，生产业务规则仍在 services 中执行
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_session
from app.dependencies import get_seller_id
from app.services.demo import seed_demo_scenario


router = APIRouter(prefix="/api/v1")


@router.post("/demo/seed")
def seed_demo(
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    result = seed_demo_scenario(session, seller_id)
    session.commit()
    return result
