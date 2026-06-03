"""
/* ========================================================================== */
/* GEB L3: 数据导出路由                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI APIRouter/Depends/Response、租户依赖、SQLAlchemy Session 与 data_exports 服务
 * [OUTPUT]: 对外提供 router，暴露 /api/v1/exports/{dataset}.csv
 * [POS]: routers 的数据导出边界，给看板与 CRM 提供询盘、客户、报价 CSV 下载
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.database import get_session
from app.dependencies import get_seller_id
from app.errors import api_error
from app.services.data_exports import export_dataset_csv, supported_export_datasets


router = APIRouter(prefix="/api/v1")


@router.get("/exports/{dataset}.csv")
def export_dataset(
    dataset: str,
    limit: int = 1000,
    seller_id: int = Depends(get_seller_id),
    session: Session = Depends(get_session),
) -> Response:
    try:
        content = export_dataset_csv(session, seller_id, dataset, limit=limit)
    except ValueError as exc:
        allowed = ", ".join(supported_export_datasets())
        raise api_error(404, "export_dataset_not_found", f"Export dataset must be one of: {allowed}") from exc
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{dataset}.csv"'},
    )
