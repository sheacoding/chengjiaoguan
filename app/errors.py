"""
/* ========================================================================== */
/* GEB L3: API 错误适配                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 FastAPI 异常机制与 JSONResponse
 * [OUTPUT]: 对外提供 add_error_handlers 与 api_error
 * [POS]: app 的错误形状守门员，保证 API 输出符合统一 error contract
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse


def add_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail and "message" in detail:
            payload = detail
        else:
            payload = {"code": str(exc.status_code), "message": str(detail)}
        return JSONResponse(status_code=exc.status_code, content={"error": payload})


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})
