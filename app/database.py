"""
/* ========================================================================== */
/* GEB L3: 数据库基础设施                                                     */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 SQLAlchemy engine、DeclarativeBase、Session 与 datetime UTC
 * [OUTPUT]: 对外提供 Base、build_engine、engine、SessionLocal、get_session、utcnow
 * [POS]: app 的持久化根基，被 models、main、services 与 tests 共享
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from collections.abc import Generator
from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


DEFAULT_DATABASE_URL = "sqlite:///./closer.db"


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


def build_engine(database_url: str = DEFAULT_DATABASE_URL):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args, future=True)


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
