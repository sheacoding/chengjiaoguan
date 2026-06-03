"""
/* ========================================================================== */
/* GEB L3: 后台任务统一调度测试                                               */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 pytest monkeypatch、SQLite 会话夹具、FastAPI TestClient、app.models 与 workers 服务
 * [OUTPUT]: 验证 unified worker 可执行 follow-up、delivery retry、价格规则汇率刷新、启用轮询的 email channel，并证明 HTTP 入口租户隔离
 * [POS]: tests 的后台调度证明文件，锁住 due jobs 从服务层到 API 的单入口契约
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from datetime import timedelta

from app import agent_tools, models
from app.database import utcnow
from app.services.email_polling import RawEmailMessage, StaticEmailInboxClient
from app.services.workers import run_due_jobs


def _raw_email(message_id: str) -> str:
    return f"""From: Buyer <buyer@example.com>
To: sales@example-exporter.com
Subject: Need lamps
Message-ID: <{message_id}>

Need 1200 LED desk lamps to US.
"""


def _seed_due_jobs(db_session, monkeypatch):
    monkeypatch.setenv("CLOSER_DELIVERY_MODE", "live")
    seller = models.Seller(id=1, name="Demo Exporter", email="owner@example.com")
    customer = models.Customer(seller_id=1, email="buyer@example.com", status="active")
    db_session.add_all([seller, customer])
    db_session.flush()
    inquiry = models.Inquiry(seller_id=1, customer_id=customer.id, raw_content="Need lamps", status="new")
    db_session.add(inquiry)
    db_session.flush()
    conversation = models.Conversation(
        seller_id=1,
        customer_id=customer.id,
        inquiry_id=inquiry.id,
        channel="email",
        language="en",
    )
    channel = models.ChannelAccount(
        seller_id=1,
        channel_type="email",
        name="Sales inbox",
        credentials={
            "host": "imap.example.com",
            "username": "sales",
            "password": "secret",
            "poll_enabled": True,
        },
        status="connected",
    )
    disabled_channel = models.ChannelAccount(
        seller_id=1,
        channel_type="email",
        name="Archive inbox",
        credentials={"poll_enabled": False},
        status="connected",
    )
    pricing_rule = models.PricingRule(
        seller_id=1,
        margin_rate="0.25",
        logistics_template={
            "exchange_rate_provider": {
                "source": "demo_bank",
                "source_currency": "USD",
                "target_currencies": ["EUR"],
                "ttl_days": 2,
                "rates": {"USD": {"EUR": "0.90"}},
            }
        },
        floor_price="2.00",
        currency="USD",
    )
    db_session.add_all([conversation, channel, disabled_channel, pricing_rule])
    db_session.flush()
    followup = agent_tools.create_followup(db_session, 1, inquiry.id, conversation.id, delay_hours=1, max_attempts=1)
    task = db_session.get(models.FollowupTask, followup["followup_id"])
    now = utcnow()
    task.next_run_at = now - timedelta(minutes=1)
    sent = agent_tools.send_message(db_session, 1, conversation.id, "Thanks for your inquiry.")
    attempt = db_session.get(models.DeliveryAttempt, sent["delivery"]["delivery_attempt_id"])
    attempt.next_retry_at = now
    monkeypatch.delenv("CLOSER_DELIVERY_MODE", raising=False)
    return channel, task, attempt, pricing_rule


def test_run_due_jobs_executes_all_due_boundaries(db_session, monkeypatch):
    channel, task, attempt, pricing_rule = _seed_due_jobs(db_session, monkeypatch)
    inbox = StaticEmailInboxClient([RawEmailMessage(uid="301", raw=_raw_email("worker-email-001@example.com"))])

    result = run_due_jobs(
        db_session,
        1,
        email_client_factory=lambda account: inbox if account.id == channel.id else None,
    )

    assert result["followups"]["total"] == 1
    assert result["delivery_retries"]["total"] == 1
    assert result["pricing_exchange_rate_refreshes"]["total"] == 1
    assert result["email_polls"]["total"] == 1
    assert result["total_jobs"] == 4
    assert result["pricing_exchange_rate_refreshes"]["items"][0]["status"] == "refreshed"
    assert db_session.get(models.PricingRule, pricing_rule.id).logistics_template["exchange_rate_cache"]["rates"] == {
        "USD": {"EUR": "0.90"}
    }
    assert result["email_polls"]["items"][0]["fetched"] == 1
    assert inbox.acknowledged == ["301"]
    assert db_session.get(models.FollowupTask, task.id).status == "completed"
    assert db_session.get(models.DeliveryAttempt, attempt.id).status == "queued"
    assert db_session.query(models.Message).filter_by(channel_message_id="worker-email-001@example.com").count() == 1


def test_workers_run_due_endpoint_is_tenant_scoped(client, db_session, monkeypatch):
    _seed_due_jobs(db_session, monkeypatch)

    response = client.post("/api/v1/workers/run-due", headers={"Authorization": "Bearer seller:2"})

    assert response.status_code == 200
    assert response.json()["total_jobs"] == 0
    assert response.json()["followups"]["total"] == 0
    assert response.json()["delivery_retries"]["total"] == 0
    assert response.json()["pricing_exchange_rate_refreshes"]["total"] == 0
    assert response.json()["email_polls"]["total"] == 0


def test_run_due_jobs_reports_pricing_refresh_failures_without_stopping(db_session):
    seller = models.Seller(id=1, name="Demo Exporter", email="owner@example.com")
    bad_rule = models.PricingRule(
        seller_id=1,
        logistics_template={
            "exchange_rate_provider": {
                "source_currency": "USD",
                "target_currencies": ["EUR"],
                "rates": {"USD": {"GBP": "0.78"}},
            }
        },
        floor_price="2.00",
        currency="USD",
    )
    good_rule = models.PricingRule(
        seller_id=1,
        logistics_template={
            "exchange_rate_provider": {
                "source_currency": "USD",
                "target_currencies": ["EUR"],
                "rates": {"USD": {"EUR": "0.91"}},
            }
        },
        floor_price="2.00",
        currency="USD",
    )
    db_session.add_all([seller, bad_rule, good_rule])
    db_session.flush()

    result = run_due_jobs(db_session, 1)

    items = result["pricing_exchange_rate_refreshes"]["items"]
    assert result["pricing_exchange_rate_refreshes"]["total"] == 2
    assert result["total_jobs"] == 2
    assert items[0]["status"] == "failed"
    assert "USD->EUR" in items[0]["error"]
    assert items[1]["status"] == "refreshed"
    assert db_session.get(models.PricingRule, good_rule.id).logistics_template["exchange_rate_cache"]["rates"] == {
        "USD": {"EUR": "0.91"}
    }


def test_workers_run_due_endpoint_uses_single_operational_entry(client, db_session, monkeypatch):
    channel, _, _, _ = _seed_due_jobs(db_session, monkeypatch)

    def fake_run_due_jobs(session, seller_id, **kwargs):
        assert seller_id == 1
        assert kwargs["email_message_limit"] == 5
        assert kwargs["pricing_exchange_rate_limit"] == 7
        return {
            "followups": {"items": [], "total": 0},
            "delivery_retries": {"items": [], "total": 0},
            "pricing_exchange_rate_refreshes": {"items": [], "total": 0},
            "email_polls": {"items": [{"status": "ok", "channel_account_id": channel.id}], "total": 1},
            "total_jobs": 1,
        }

    monkeypatch.setattr("app.routers.workers.run_due_jobs", fake_run_due_jobs)

    response = client.post(
        "/api/v1/workers/run-due",
        params={"email_message_limit": 5, "pricing_exchange_rate_limit": 7},
    )

    assert response.status_code == 200
    assert response.json()["email_polls"]["items"][0]["channel_account_id"] == channel.id
    assert response.json()["total_jobs"] == 1
