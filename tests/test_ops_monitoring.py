"""
/* ========================================================================== */
/* GEB L3: 运维监控 Sink 测试                                                 */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 json、pytest monkeypatch 与 ops_monitoring 服务
 * [OUTPUT]: 验证 disabled/http 运维监控 sink、事件上报请求与配置画像
 * [POS]: tests 的外部监控边界证明文件，锁住 scheduler 事件上报不触真实网络
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

import json

from app.services.ops_monitoring import (
    DisabledMonitoringSink,
    HttpMonitoringSink,
    get_monitoring_sink_config,
)


def test_disabled_monitoring_sink_skips_event():
    sink = DisabledMonitoringSink()

    assert sink.emit({"event_type": "ops_scheduler_run"}) == {
        "status": "skipped",
        "provider": "disabled",
        "event_type": "ops_scheduler_run",
    }


def test_http_monitoring_sink_posts_event(monkeypatch):
    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return json.dumps({"status": "ok", "external_id": "evt_123"}).encode()

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr("app.services.ops_monitoring.urlopen", fake_urlopen)

    sink = HttpMonitoringSink(
        endpoint="https://monitor.example/events",
        auth_token="token-123",
        timeout_seconds=2.5,
    )
    result = sink.emit({"event_type": "ops_scheduler_run", "seller_id": 1, "status": "ok"})

    request, timeout = requests[0]
    payload = json.loads(request.data.decode())
    assert timeout == 2.5
    assert request.full_url == "https://monitor.example/events"
    assert request.get_header("Authorization") == "Bearer token-123"
    assert payload["event_type"] == "ops_scheduler_run"
    assert payload["seller_id"] == 1
    assert result == {
        "status": "ok",
        "provider": "http",
        "event_type": "ops_scheduler_run",
        "external_id": "evt_123",
    }


def test_get_monitoring_sink_config_reports_default_and_http():
    default_config = get_monitoring_sink_config({})
    missing_endpoint = get_monitoring_sink_config({"CLOSER_OPS_MONITOR_PROVIDER": "http"})
    configured = get_monitoring_sink_config(
        {
            "CLOSER_OPS_MONITOR_PROVIDER": "webhook",
            "CLOSER_OPS_MONITOR_ENDPOINT": "https://monitor.example/events",
            "CLOSER_OPS_MONITOR_AUTH_TOKEN": "token-123",
        }
    )

    assert default_config.status == "warning"
    assert default_config.details()["provider"] == "disabled"
    assert missing_endpoint.status == "failed"
    assert "CLOSER_OPS_MONITOR_ENDPOINT" in missing_endpoint.message
    assert configured.status == "ok"
    assert configured.details()["provider"] == "http"
    assert configured.details()["auth_token_configured"] is True
