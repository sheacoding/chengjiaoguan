"""
/* ========================================================================== */
/* GEB L3: Agent runtime 测试                                                 */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 PydanticAI TestModel、SQLite 会话夹具、app.models、graph policy 与 app.agent_runtime
 * [OUTPUT]: 验证 PydanticAI runtime 的工具绑定、结构化输出、graph policy 注入与 Pydantic Graph 八步状态机
 * [POS]: tests 的 Agent 编排证明文件，锁住模型运行入口与确定性图执行契约
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from decimal import Decimal

from pydantic_ai.models.test import TestModel

from app import models
from app.agent.graph_domain.policy import GraphPolicyDecision
from app.agent_runtime import (
    CloserAgentOutput,
    closer_graph_mermaid,
    get_agent_model_config,
    run_closer_agent,
    run_closer_graph_result,
)


def test_closer_agent_runs_with_pydanticai_test_model(db_session):
    model = TestModel(
        call_tools=[],
        custom_output_args={
            "summary": "Inquiry has enough details to score and draft a quote.",
            "draft_response": "Thanks, we can prepare pricing after confirming quantity.",
            "next_actions": ["score_inquiry", "calc_quote"],
            "requires_human_review": False,
        },
    )

    output = run_closer_agent(
        db_session,
        1,
        "Assess this inquiry and suggest next steps.",
        inquiry_id=123,
        model=model,
    )

    assert isinstance(output, CloserAgentOutput)
    assert output.summary.startswith("Inquiry has enough details")
    assert output.next_actions == ["score_inquiry", "calc_quote"]


def test_closer_agent_exposes_core_tools_to_model(db_session):
    model = TestModel(
        call_tools=[],
        custom_output_args={
            "summary": "Ready.",
            "draft_response": None,
            "next_actions": [],
            "requires_human_review": False,
        },
    )

    run_closer_agent(db_session, 1, "List available operating tools.", model=model)

    tool_names = {tool.name for tool in model.last_model_request_parameters.function_tools}
    assert {
        "get_inquiry",
        "score_inquiry",
        "get_customer",
        "calc_quote",
        "generate_pi",
        "search_knowledge",
        "match_product",
        "send_message",
        "create_followup",
        "request_handoff",
    }.issubset(tool_names)


def test_closer_agent_uses_configured_model_when_no_explicit_model(db_session, monkeypatch):
    calls = {}

    class Result:
        output = CloserAgentOutput(
            summary="Configured model used.",
            draft_response=None,
            next_actions=[],
            requires_human_review=False,
        )

    def fake_run_sync(user_prompt, **kwargs):
        calls["prompt"] = user_prompt
        calls["model"] = kwargs["model"]
        return Result()

    monkeypatch.setenv("CLOSER_AGENT_MODEL", "custom:closer-test")
    monkeypatch.setattr("app.agent.runtime.closer_agent.run_sync", fake_run_sync)

    output = run_closer_agent(db_session, 1, "Use configured model.")

    assert output.summary == "Configured model used."
    assert calls == {"prompt": "Use configured model.", "model": "custom:closer-test"}


def test_agent_model_config_requires_key_for_openai_model(monkeypatch):
    monkeypatch.setenv("CLOSER_AGENT_MODEL", "openai:gpt-4o-mini")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    missing = get_agent_model_config()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    configured = get_agent_model_config()

    assert missing.status == "failed"
    assert missing.api_key_env == "OPENAI_API_KEY"
    assert configured.status == "ok"


def test_closer_graph_runs_quote_answer_followup_path(db_session):
    inquiry, conversation, _ = _seed_operating_graph(db_session)

    result = run_closer_graph_result(
        db_session,
        1,
        "Handle this qualified inquiry end to end.",
        inquiry_id=inquiry.id,
        conversation_id=conversation.id,
    )

    assert result.output.requires_human_review is False
    assert result.state.steps == ["receive", "qualify", "understand", "quote", "answer", "followup", "persist"]
    assert result.state.quote["quotation_id"] == 1
    assert result.state.send_result["status"] == "sent"
    assert result.state.followup["status"] == "active"
    assert db_session.query(models.Quotation).count() == 1
    assert db_session.query(models.FollowupTask).count() == 1
    assert db_session.query(models.Message).filter_by(sender_role="ai").count() == 1


def test_closer_graph_requests_handoff_when_product_is_out_of_scope(db_session):
    inquiry, conversation, _ = _seed_operating_graph(db_session, parsed_product="custom turbine")

    result = run_closer_graph_result(
        db_session,
        1,
        "Handle this out-of-scope inquiry.",
        inquiry_id=inquiry.id,
        conversation_id=conversation.id,
    )

    assert result.output.requires_human_review is True
    assert result.state.steps == ["receive", "qualify", "understand", "handoff", "persist"]
    approval = db_session.get(models.Approval, result.state.handoff["approval_id"])
    assert approval.reason == "product_out_of_scope"
    assert db_session.get(models.Conversation, conversation.id).is_human_takeover is True


def test_closer_graph_uses_injected_policy_before_sending(db_session):
    class HoldBeforeSendPolicy:
        name = "hold_before_send"

        def decide(self, context):
            if context.stage == "answer":
                return GraphPolicyDecision(
                    requires_human_review=True,
                    handoff_reason="policy_review",
                    handoff_summary="Policy requested review before sending.",
                    should_quote=False,
                )
            return GraphPolicyDecision()

    inquiry, conversation, _ = _seed_operating_graph(db_session)

    result = run_closer_graph_result(
        db_session,
        1,
        "Handle this inquiry but hold before sending.",
        inquiry_id=inquiry.id,
        conversation_id=conversation.id,
        decision_provider=HoldBeforeSendPolicy(),
    )

    assert result.output.requires_human_review is True
    assert result.state.steps == ["receive", "qualify", "understand", "quote", "answer", "handoff", "persist"]
    assert result.state.policy_decisions[-1]["provider"] == "hold_before_send"
    approval = db_session.get(models.Approval, result.state.handoff["approval_id"])
    assert approval.reason == "policy_review"
    assert db_session.query(models.Message).filter_by(sender_role="ai").count() == 0


def test_closer_graph_mermaid_exposes_eight_operating_nodes():
    diagram = closer_graph_mermaid()

    for node in [
        "ReceiveInquiry",
        "QualifyInquiry",
        "UnderstandRequirement",
        "ReplyWithQuote",
        "NegotiateAndAnswer",
        "ScheduleFollowup",
        "RequestHumanHandoff",
        "PersistMemory",
    ]:
        assert node in diagram


def _seed_operating_graph(db_session, *, parsed_product: str = "led desk lamp"):
    seller = models.Seller(id=1, name="Demo Exporter", email="owner@example.com")
    customer = models.Customer(
        seller_id=1,
        email="buyer@acme-trading.com",
        company="ACME Trading",
        country="US",
        status="active",
    )
    product = models.Product(
        seller_id=1,
        name="LED Desk Lamp",
        sku="LAMP-10W",
        cost=Decimal("2.00"),
        moq=100,
        description="10W aluminum LED desk lamp for office buyers.",
        status="active",
    )
    db_session.add_all([seller, customer, product])
    db_session.flush()
    inquiry = models.Inquiry(
        seller_id=1,
        customer_id=customer.id,
        source_channel="email",
        raw_content=f"Need 500 {parsed_product} shipped to US.",
        parsed={"product": parsed_product, "quantity": 500, "destination": "US"},
        status="new",
        language="en",
    )
    db_session.add(inquiry)
    db_session.flush()
    conversation = models.Conversation(
        seller_id=1,
        customer_id=customer.id,
        inquiry_id=inquiry.id,
        channel="email",
        language="en",
    )
    rule = models.PricingRule(
        seller_id=1,
        product_id=product.id,
        margin_rate=Decimal("0.25"),
        logistics_template={"unit_cost": "0.10"},
        valid_days=14,
        floor_price=Decimal("2.00"),
        currency="USD",
    )
    db_session.add_all([conversation, rule])
    db_session.flush()
    return inquiry, conversation, product
