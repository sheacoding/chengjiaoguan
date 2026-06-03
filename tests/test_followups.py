"""
/* ========================================================================== */
/* GEB L3: 跟进任务测试                                                       */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 datetime timedelta、SQLite 会话夹具、agent_tools、models 与 followups 服务
 * [OUTPUT]: 验证 follow-up 创建、到期发送、最大次数完成与客户回复停止
 * [POS]: tests 的 follow-up 状态机证明文件，锁住未回复询盘推进器行为
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from datetime import timedelta

from app import agent_tools, models
from app.database import utcnow
from app.services.followups import run_due_followups


def _seed_conversation(db_session, *, takeover: bool = False):
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
        is_human_takeover=takeover,
    )
    db_session.add(conversation)
    db_session.flush()
    return inquiry, conversation


def test_create_followup_tool_schedules_task(db_session):
    inquiry, conversation = _seed_conversation(db_session)

    result = agent_tools.create_followup(db_session, 1, inquiry.id, conversation.id, delay_hours=2, max_attempts=2)

    assert result["status"] == "active"
    assert result["schedule"]["delay_hours"] == 2
    task = db_session.get(models.FollowupTask, result["followup_id"])
    assert task.conversation_id == conversation.id
    assert task.next_run_at is not None


def test_run_due_followups_sends_message_and_reschedules(db_session):
    inquiry, conversation = _seed_conversation(db_session)
    result = agent_tools.create_followup(
        db_session,
        1,
        inquiry.id,
        conversation.id,
        delay_hours=1,
        message="Do you need anything else for this order?",
        max_attempts=2,
    )
    task = db_session.get(models.FollowupTask, result["followup_id"])
    now = utcnow()
    task.next_run_at = now - timedelta(minutes=1)

    runs = run_due_followups(db_session, seller_id=1, now=now)

    assert runs[0]["send_result"]["status"] == "sent"
    assert runs[0]["status"] == "active"
    assert db_session.query(models.Message).filter_by(conversation_id=conversation.id, sender_role="ai").count() == 1
    assert db_session.get(models.FollowupTask, task.id).schedule["attempt"] == 1


def test_run_due_followups_completes_after_max_attempts(db_session):
    inquiry, conversation = _seed_conversation(db_session)
    result = agent_tools.create_followup(db_session, 1, inquiry.id, conversation.id, delay_hours=1, max_attempts=1)
    task = db_session.get(models.FollowupTask, result["followup_id"])
    now = utcnow()
    task.next_run_at = now - timedelta(minutes=1)

    runs = run_due_followups(db_session, seller_id=1, now=now)

    assert runs[0]["status"] == "completed"
    assert runs[0]["stop_reason"] == "max_attempts_reached"
    assert db_session.get(models.FollowupTask, task.id).next_run_at is None


def test_run_due_followups_stops_when_customer_replied(db_session):
    inquiry, conversation = _seed_conversation(db_session)
    result = agent_tools.create_followup(db_session, 1, inquiry.id, conversation.id)
    task = db_session.get(models.FollowupTask, result["followup_id"])
    now = utcnow()
    task.next_run_at = now - timedelta(minutes=1)
    db_session.add(
        models.Message(
            conversation_id=conversation.id,
            sender_role="customer",
            content="Thanks, I will review it.",
            sent_at=now,
        )
    )

    runs = run_due_followups(db_session, seller_id=1, now=now)

    assert runs[0]["status"] == "stopped"
    assert runs[0]["stop_reason"] == "customer_replied"
    assert db_session.query(models.Message).filter_by(conversation_id=conversation.id, sender_role="ai").count() == 0
