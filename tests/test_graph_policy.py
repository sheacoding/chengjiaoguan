"""
/* ========================================================================== */
/* GEB L3: Agent 图决策策略测试                                               */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 json、pytest monkeypatch 与 app.agent.graph_domain.policy
 * [OUTPUT]: 验证规则型 graph policy、HTTP/OpenAI-compatible graph policy 请求与配置画像
 * [POS]: tests 的 Agent 图决策边界证明文件，锁住规则决策与生产 HTTP/LLM 决策 provider 的隔离
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

import json

from app.agent.graph_domain import policy


def test_rule_based_graph_policy_hands_off_low_quality_inquiry():
    provider = policy.RuleBasedGraphDecisionProvider()
    decision = provider.decide(
        policy.GraphPolicyContext(
            stage="qualify",
            seller_id=1,
            user_prompt="Handle inquiry.",
            inquiry_id=1,
            conversation_id=1,
            score={"grade": "C"},
        )
    )

    assert decision.requires_human_review is True
    assert decision.handoff_reason == "low_quality_inquiry"
    assert decision.should_quote is False


def test_http_graph_policy_posts_context_and_parses_decision(monkeypatch):
    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return json.dumps(
                {
                    "decision": {
                        "requires_human_review": True,
                        "handoff_reason": "policy_review",
                        "handoff_summary": "Review before sending.",
                        "should_quote": False,
                    }
                }
            ).encode()

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(policy, "urlopen", fake_urlopen)

    provider = policy.HttpGraphDecisionProvider(
        endpoint="https://policy.example/decide",
        auth_token="token-123",
        timeout_seconds=2.5,
    )
    decision = provider.decide(
        policy.GraphPolicyContext(
            stage="answer",
            seller_id=1,
            user_prompt="Need 500 lamps",
            inquiry_id=7,
            conversation_id=9,
            score={"grade": "A"},
        )
    )

    request, timeout = requests[0]
    payload = json.loads(request.data.decode())
    assert timeout == 2.5
    assert request.full_url == "https://policy.example/decide"
    assert request.get_header("Authorization") == "Bearer token-123"
    assert payload["stage"] == "answer"
    assert payload["inquiry_id"] == 7
    assert decision.requires_human_review is True
    assert decision.handoff_reason == "policy_review"
    assert decision.should_quote is False


def test_openai_graph_policy_posts_chat_completion_and_parses_json_decision(monkeypatch):
    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "decision": {
                                            "requires_human_review": False,
                                            "knowledge_query": "500 lamps CIF Chile",
                                            "should_quote": True,
                                            "draft_response": "We can quote this order.",
                                        }
                                    }
                                )
                            }
                        }
                    ]
                }
            ).encode()

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(policy, "urlopen", fake_urlopen)

    provider = policy.OpenAICompatibleGraphDecisionProvider(
        endpoint="https://llm.example/v1/chat/completions",
        api_key="sk-test",
        model="gpt-test",
        timeout_seconds=3.0,
    )
    decision = provider.decide(
        policy.GraphPolicyContext(
            stage="understand",
            seller_id=1,
            user_prompt="Need 500 lamps shipped to Chile",
            inquiry_id=7,
            conversation_id=9,
        )
    )

    request, timeout = requests[0]
    payload = json.loads(request.data.decode())
    user_content = json.loads(payload["messages"][1]["content"])

    assert timeout == 3.0
    assert request.full_url == "https://llm.example/v1/chat/completions"
    assert request.get_header("Authorization") == "Bearer sk-test"
    assert payload["model"] == "gpt-test"
    assert payload["temperature"] == 0
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["messages"][0]["role"] == "system"
    assert user_content["context"]["stage"] == "understand"
    assert user_content["context"]["inquiry_id"] == 7
    assert decision.knowledge_query == "500 lamps CIF Chile"
    assert decision.should_quote is True
    assert decision.draft_response == "We can quote this order."


def test_graph_decision_provider_config_reports_default_and_http(monkeypatch):
    monkeypatch.delenv("CLOSER_GRAPH_DECISION_PROVIDER", raising=False)
    default_config = policy.get_graph_decision_provider_config()

    monkeypatch.setenv("CLOSER_GRAPH_DECISION_PROVIDER", "http")
    monkeypatch.setenv("CLOSER_GRAPH_DECISION_ENDPOINT", "https://policy.example/decide")
    monkeypatch.setenv("CLOSER_GRAPH_DECISION_AUTH_TOKEN", "token-123")
    http_config = policy.get_graph_decision_provider_config()

    assert default_config.status == "warning"
    assert default_config.details()["provider"] == "rule_based"
    assert http_config.status == "ok"
    assert http_config.details()["provider"] == "http"
    assert http_config.details()["auth_token_configured"] is True


def test_graph_decision_provider_config_reports_openai_key_and_model_states():
    missing_model = policy.get_graph_decision_provider_config(
        {
            "CLOSER_GRAPH_DECISION_PROVIDER": "openai",
            "OPENAI_API_KEY": "sk-test",
        }
    )
    missing_key = policy.get_graph_decision_provider_config(
        {
            "CLOSER_GRAPH_DECISION_PROVIDER": "openai",
            "CLOSER_GRAPH_DECISION_MODEL": "gpt-test",
        }
    )
    configured = policy.get_graph_decision_provider_config(
        {
            "CLOSER_GRAPH_DECISION_PROVIDER": "llm",
            "CLOSER_GRAPH_DECISION_MODEL": "gpt-test",
            "CLOSER_GRAPH_DECISION_BASE_URL": "https://llm.example/v1",
            "CLOSER_GRAPH_DECISION_API_KEY_ENV": "GRAPH_KEY",
            "GRAPH_KEY": "sk-test",
        }
    )

    assert missing_model.status == "failed"
    assert "CLOSER_GRAPH_DECISION_MODEL" in missing_model.message
    assert missing_model.details()["api_key_configured"] is True
    assert missing_key.status == "failed"
    assert "OPENAI_API_KEY" in missing_key.message
    assert configured.status == "ok"
    assert configured.details()["provider"] == "openai"
    assert configured.details()["model"] == "gpt-test"
    assert configured.details()["endpoint"] == "https://llm.example/v1/chat/completions"
    assert configured.details()["api_key_env"] == "GRAPH_KEY"
    assert configured.details()["api_key_configured"] is True
