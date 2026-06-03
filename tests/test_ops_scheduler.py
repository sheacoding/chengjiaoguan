"""
/* ========================================================================== */
/* GEB L3: 运维调度组合测试                                                   */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 pytest monkeypatch、SQLite 会话夹具、ops_scheduler 服务与 workers 路由
 * [OUTPUT]: 验证外部 scheduler 单入口可组合 due jobs、readiness、alerts 与 monitoring 上报，并保持租户隔离
 * [POS]: tests 的外部 cron/queue 适配证明文件，锁住调度入口的可观测结果契约
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from app import models
from app.services.ops_scheduler import run_scheduled_operations


class RecordingMonitoringSink:
    name = "recording"

    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)
        return {"status": "ok", "provider": self.name, "event_type": event["event_type"]}


def test_run_scheduled_operations_emits_monitoring_event(db_session, monkeypatch):
    db_session.add(models.Seller(id=1, name="Demo Exporter", email="owner@example.com"))
    sink = RecordingMonitoringSink()

    monkeypatch.setattr(
        "app.services.ops_scheduler.run_due_jobs",
        lambda session, seller_id, **kwargs: {
            "followups": {"items": [], "total": 0},
            "delivery_retries": {"items": [], "total": 0},
            "pricing_exchange_rate_refreshes": {"items": [], "total": 0},
            "email_polls": {"items": [], "total": 0},
            "total_jobs": 0,
        },
    )
    monkeypatch.setattr(
        "app.services.ops_scheduler.get_readiness",
        lambda session, seller_id: {"status": "ready", "summary": {"ok": 1, "warning": 0, "failed": 0}},
    )
    monkeypatch.setattr(
        "app.services.ops_scheduler.list_ops_alerts",
        lambda session, seller_id, limit: {"status": "ok", "items": [], "total": 0, "counts": {"critical": 0, "warning": 0}},
    )

    result = run_scheduled_operations(db_session, 1, monitoring_sink=sink)

    assert result["status"] == "ok"
    assert result["jobs"]["total_jobs"] == 0
    assert result["readiness"]["status"] == "ready"
    assert result["alerts"]["status"] == "ok"
    assert result["monitoring"] == {"status": "ok", "provider": "recording", "event_type": "ops_scheduler_run"}
    assert sink.events[0]["event_type"] == "ops_scheduler_run"
    assert sink.events[0]["seller_id"] == 1
    assert sink.events[0]["jobs"]["total_jobs"] == 0


def test_run_scheduled_operations_marks_failed_job_as_critical(db_session, monkeypatch):
    db_session.add(models.Seller(id=1, name="Demo Exporter", email="owner@example.com"))

    monkeypatch.setattr(
        "app.services.ops_scheduler.run_due_jobs",
        lambda session, seller_id, **kwargs: {
            "followups": {"items": [], "total": 0},
            "delivery_retries": {"items": [{"status": "failed"}], "total": 1},
            "pricing_exchange_rate_refreshes": {"items": [], "total": 0},
            "email_polls": {"items": [], "total": 0},
            "total_jobs": 1,
        },
    )
    monkeypatch.setattr(
        "app.services.ops_scheduler.get_readiness",
        lambda session, seller_id: {"status": "ready", "summary": {"ok": 1, "warning": 0, "failed": 0}},
    )
    monkeypatch.setattr(
        "app.services.ops_scheduler.list_ops_alerts",
        lambda session, seller_id, limit: {"status": "ok", "items": [], "total": 0, "counts": {"critical": 0, "warning": 0}},
    )

    result = run_scheduled_operations(db_session, 1, emit_monitoring=False)

    assert result["status"] == "critical"
    assert result["monitoring"]["status"] == "skipped"


def test_ops_scheduler_endpoint_uses_single_operational_entry(client, db_session, monkeypatch):
    db_session.add(models.Seller(id=1, name="Demo Exporter", email="owner@example.com"))

    def fake_run_scheduled_operations(session, seller_id, **kwargs):
        assert seller_id == 1
        assert kwargs["email_message_limit"] == 5
        assert kwargs["pricing_exchange_rate_limit"] == 7
        assert kwargs["emit_monitoring"] is False
        return {
            "status": "ok",
            "seller_id": seller_id,
            "jobs": {"total_jobs": 0},
            "readiness": {"status": "ready", "summary": {}},
            "alerts": {"status": "ok", "total": 0, "counts": {}},
            "monitoring": {"status": "skipped", "provider": "disabled"},
        }

    monkeypatch.setattr("app.routers.workers.run_scheduled_operations", fake_run_scheduled_operations)

    response = client.post(
        "/api/v1/ops/scheduler/run",
        params={"email_message_limit": 5, "pricing_exchange_rate_limit": 7, "emit_monitoring": False},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["seller_id"] == 1


def test_ops_scheduler_endpoint_is_tenant_scoped(client, db_session, monkeypatch):
    db_session.add(models.Seller(id=1, name="Demo Exporter", email="owner@example.com"))

    def fake_run_scheduled_operations(session, seller_id, **kwargs):
        return {
            "status": "ok",
            "seller_id": seller_id,
            "jobs": {"total_jobs": 0},
            "readiness": {"status": "ready", "summary": {}},
            "alerts": {"status": "ok", "total": 0, "counts": {}},
            "monitoring": {"status": "skipped", "provider": "disabled"},
        }

    monkeypatch.setattr("app.routers.workers.run_scheduled_operations", fake_run_scheduled_operations)

    response = client.post("/api/v1/ops/scheduler/run", headers={"Authorization": "Bearer seller:2"})

    assert response.status_code == 200
    assert response.json()["seller_id"] == 2
