"""
/* ========================================================================== */
/* GEB L3: HTTP API 应用入口                                                  */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI lifespan、数据库 Base/engine、错误处理与 app.routers 分域路由
 * [OUTPUT]: 对外提供 create_app 工厂与 app 实例，挂载 /api/v1 health、auth、webhook、inquiries、customers、conversations、settings、products、pricing-rules、channels、channel-operations、knowledge、approvals、notifications、quotations、delivery-attempts、workers、exports、dashboard、demo API
 * [POS]: app 的 HTTP 组合根，只负责应用生命周期、错误处理与 router 装配
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine
from app.errors import add_error_handlers
from app.routers import (
    approvals,
    auth,
    catalog,
    channel_operations,
    conversations,
    customers,
    demo,
    delivery_attempts,
    exports,
    inquiries,
    knowledge,
    notifications,
    quotations,
    settings,
    workers,
    webhooks,
)


def create_app(create_db_on_startup: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if create_db_on_startup:
            Base.metadata.create_all(engine)
        yield

    app = FastAPI(title="Closer API", version="0.1.0", lifespan=lifespan)
    add_error_handlers(app)
    _include_routers(app)

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _include_routers(app: FastAPI) -> None:
    for router in [
        webhooks.router,
        auth.router,
        inquiries.router,
        customers.router,
        conversations.router,
        settings.router,
        demo.router,
        delivery_attempts.router,
        exports.router,
        channel_operations.router,
        catalog.router,
        knowledge.router,
        approvals.router,
        notifications.router,
        quotations.router,
        workers.router,
    ]:
        app.include_router(router)


app = create_app()
