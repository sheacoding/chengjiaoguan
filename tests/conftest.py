"""
/* ========================================================================== */
/* GEB L3: Pytest 夹具                                                        */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 pytest、FastAPI TestClient、SQLAlchemy SQLite 内存库与 app.main.create_app
 * [OUTPUT]: 对外提供 db_session、client 夹具，并默认关闭 live delivery、托管知识索引、全局汇率源与运维监控外部边界
 * [POS]: tests 的基础设施真源，让所有测试共享确定性数据库和零网络外部边界
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_session
from app.main import create_app
import app.models  # noqa: F401


@pytest.fixture(autouse=True)
def deterministic_external_boundaries(monkeypatch):
    monkeypatch.setenv("CLOSER_ALLOW_DEV_AUTH", "1")
    monkeypatch.setenv("CLOSER_ALLOW_DEV_CREDENTIALS", "1")
    monkeypatch.delenv("CLOSER_DELIVERY_MODE", raising=False)
    monkeypatch.delenv("CLOSER_KNOWLEDGE_INDEX_PROVIDER", raising=False)
    monkeypatch.delenv("CLOSER_KNOWLEDGE_INDEX_ENDPOINT", raising=False)
    monkeypatch.delenv("CLOSER_KNOWLEDGE_INDEX_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("CLOSER_EXCHANGE_RATE_PROVIDER", raising=False)
    monkeypatch.delenv("CLOSER_EXCHANGE_RATE_SOURCE", raising=False)
    monkeypatch.delenv("CLOSER_EXCHANGE_RATE_ENDPOINT", raising=False)
    monkeypatch.delenv("CLOSER_EXCHANGE_RATE_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("CLOSER_OPS_MONITOR_PROVIDER", raising=False)
    monkeypatch.delenv("CLOSER_OPS_MONITOR_ENDPOINT", raising=False)
    monkeypatch.delenv("CLOSER_OPS_MONITOR_AUTH_TOKEN", raising=False)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    with Session() as session:
        yield session


@pytest.fixture
def client(db_session):
    app = create_app(create_db_on_startup=False)

    def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
