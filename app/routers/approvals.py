"""
/* ========================================================================== */
/* GEB L3: 审批路由                                                           */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI APIRouter/Depends、ApprovalPatch/Reject、approvals 服务与 common 序列化
 * [OUTPUT]: 对外提供 router，暴露 approvals 列表、修改、批准、拒绝接口
 * [POS]: routers 的人工处理队列边界，连接护栏挂起动作与卖家确认
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_session
from app.dependencies import get_seller_id
from app.errors import api_error
from app.routers.common import approval_item
from app.schemas import ApprovalPatch, ApprovalReject
from app.services.approvals import approve_approval, list_approvals, patch_approval, reject_approval


router = APIRouter(prefix="/api/v1")


@router.get("/approvals")
def get_approvals(
    status: str | None = "pending",
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    approvals = list_approvals(session, seller_id, status=status)
    return {"items": [approval_item(approval) for approval in approvals], "total": len(approvals)}


@router.patch("/approvals/{approval_id}")
def update_approval(
    approval_id: int,
    payload: ApprovalPatch,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        approval = patch_approval(
            session,
            seller_id,
            approval_id,
            payload=payload.payload,
            suggestion=payload.suggestion,
            summary=payload.summary,
        )
    except LookupError as exc:
        raise api_error(404, "approval_not_found", "Approval not found") from exc
    except ValueError as exc:
        raise api_error(409, "approval_not_pending", str(exc)) from exc
    session.commit()
    return approval_item(approval)


@router.post("/approvals/{approval_id}/approve")
def approve_pending_approval(
    approval_id: int,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        result = approve_approval(session, seller_id, approval_id)
    except LookupError as exc:
        raise api_error(404, "approval_not_found", "Approval not found") from exc
    except ValueError as exc:
        raise api_error(409, "approval_not_executable", str(exc)) from exc
    session.commit()
    return result


@router.post("/approvals/{approval_id}/reject")
def reject_pending_approval(
    approval_id: int,
    payload: ApprovalReject | None = None,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> dict:
    try:
        result = reject_approval(session, seller_id, approval_id, reason=payload.reason if payload else None)
    except LookupError as exc:
        raise api_error(404, "approval_not_found", "Approval not found") from exc
    except ValueError as exc:
        raise api_error(409, "approval_not_pending", str(exc)) from exc
    session.commit()
    return result
