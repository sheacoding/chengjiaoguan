"""
/* ========================================================================== */
/* GEB L3: 运维告警测试                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 datetime/date、SQLite 会话夹具、FastAPI TestClient、app.models 与 ops_alerts 服务
 * [OUTPUT]: 验证 ops alerts 聚合失败投递、待审批、到期/暂停跟进、汇率缓存风险并保持租户隔离
 * [POS]: tests 的运行监控证明文件，锁住既有状态到只读告警列表的映射
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from datetime import date, timedelta

from app import models
from app.database import utcnow
from app.services.ops_alerts import list_ops_alerts


def _seed_alert_facts(db_session):
    seller = models.Seller(id=1, name="Demo Exporter", email="owner@example.com")
    customer = models.Customer(seller_id=1, email="buyer@example.com", status="active")
    db_session.add_all([seller, customer])
    db_session.flush()
    inquiry = models.Inquiry(seller_id=1, customer_id=customer.id, raw_content="Need lamps", status="new")
    db_session.add(inquiry)
    db_session.flush()
    conversation = models.Conversation(seller_id=1, customer_id=customer.id, inquiry_id=inquiry.id, channel="email")
    db_session.add(conversation)
    db_session.flush()
    message = models.Message(conversation_id=conversation.id, sender_role="ai", content="Thanks")
    db_session.add(message)
    db_session.flush()
    now = utcnow()
    db_session.add_all(
        [
            models.DeliveryAttempt(
                seller_id=1,
                message_id=message.id,
                channel="email",
                external_id="closer:email:out:1",
                status="failed",
                error="SMTP refused",
                payload={},
                response={},
            ),
            models.Approval(
                seller_id=1,
                conversation_id=conversation.id,
                inquiry_id=inquiry.id,
                type="message_send",
                reason="sensitive_commitment",
                summary="Needs review",
                status="pending",
            ),
            models.FollowupTask(
                seller_id=1,
                inquiry_id=inquiry.id,
                conversation_id=conversation.id,
                schedule={},
                next_run_at=now - timedelta(minutes=5),
                status="active",
            ),
            models.FollowupTask(
                seller_id=1,
                inquiry_id=inquiry.id,
                conversation_id=conversation.id,
                schedule={},
                status="paused",
                stop_reason="human_takeover_active",
            ),
            models.PricingRule(
                seller_id=1,
                floor_price=10,
                currency="EUR",
                logistics_template={
                    "exchange_rate_cache": {
                        "confirmed": True,
                        "expires_at": (date.today() - timedelta(days=1)).isoformat(),
                        "rates": {"USD": {"EUR": "0.90"}},
                    }
                },
            ),
        ]
    )
    db_session.flush()


def test_list_ops_alerts_aggregates_operational_risks(db_session):
    _seed_alert_facts(db_session)

    result = list_ops_alerts(db_session, 1)
    codes = {item["code"] for item in result["items"]}

    assert result["status"] == "critical"
    assert result["counts"]["critical"] == 1
    assert result["counts"]["warning"] == 4
    assert {
        "failed_delivery_attempt",
        "pending_approval",
        "due_followup",
        "paused_followup",
        "exchange_rate_cache_attention",
    } == codes


def test_ops_alerts_endpoint_supports_limit_and_tenant_scope(client, db_session):
    _seed_alert_facts(db_session)

    limited = client.get("/api/v1/ops/alerts", params={"limit": 2})
    other_tenant = client.get("/api/v1/ops/alerts", headers={"Authorization": "Bearer seller:2"})

    assert limited.status_code == 200
    assert limited.json()["total"] == 2
    assert limited.json()["counts"]["critical"] == 1
    assert other_tenant.status_code == 200
    assert other_tenant.json()["status"] == "ok"
    assert other_tenant.json()["total"] == 0
