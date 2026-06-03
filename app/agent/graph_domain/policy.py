"""
/* ========================================================================== */
/* GEB L3: Agent 图决策策略                                                   */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 os/json/urllib、dataclass 与 Graph 节点运行上下文快照
 * [OUTPUT]: 对外提供 GraphPolicyContext、GraphPolicyDecision、GraphDecisionProvider、RuleBasedGraphDecisionProvider、HttpGraphDecisionProvider、OpenAICompatibleGraphDecisionProvider、get_graph_decision_provider、get_graph_decision_provider_config
 * [POS]: app/agent/graph_domain 的决策边界，把确定性规则与生产 HTTP/OpenAI-compatible LLM 决策 provider 从节点跳转中分离
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.request import Request, urlopen


GRAPH_POLICY_PROVIDER_ENV = "CLOSER_GRAPH_DECISION_PROVIDER"
GRAPH_POLICY_ENDPOINT_ENV = "CLOSER_GRAPH_DECISION_ENDPOINT"
GRAPH_POLICY_AUTH_TOKEN_ENV = "CLOSER_GRAPH_DECISION_AUTH_TOKEN"
GRAPH_POLICY_MODEL_ENV = "CLOSER_GRAPH_DECISION_MODEL"
GRAPH_POLICY_BASE_URL_ENV = "CLOSER_GRAPH_DECISION_BASE_URL"
GRAPH_POLICY_API_KEY_ENV = "CLOSER_GRAPH_DECISION_API_KEY_ENV"
GRAPH_POLICY_TIMEOUT_ENV = "CLOSER_GRAPH_DECISION_TIMEOUT_SECONDS"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
RULE_BASED_PROVIDER = "rule_based"
HTTP_PROVIDER_ALIASES = {"http", "remote"}
OPENAI_PROVIDER_ALIASES = {"openai", "openai_compatible", "llm"}

OPENAI_GRAPH_SYSTEM_PROMPT = """You decide the next action for a cross-border B2B inquiry closing graph.
Return only JSON with these keys: requires_human_review, handoff_reason, handoff_summary,
handoff_suggestion, handoff_payload, knowledge_query, should_quote, draft_response.
Use human review for unsafe promises, missing facts, off-catalog products, weak inquiries, or policy uncertainty."""


@dataclass(frozen=True)
class GraphPolicyContext:
    stage: str
    seller_id: int
    user_prompt: str
    inquiry_id: int | None = None
    conversation_id: int | None = None
    inquiry: Mapping[str, Any] | None = None
    score: Mapping[str, Any] | None = None
    product_matches: Sequence[Mapping[str, Any]] = field(default_factory=list)
    knowledge: Sequence[Mapping[str, Any]] = field(default_factory=list)
    extra: Mapping[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "seller_id": self.seller_id,
            "user_prompt": self.user_prompt,
            "inquiry_id": self.inquiry_id,
            "conversation_id": self.conversation_id,
            "inquiry": dict(self.inquiry or {}),
            "score": dict(self.score or {}),
            "product_matches": [dict(item) for item in self.product_matches],
            "knowledge": [dict(item) for item in self.knowledge],
            "extra": dict(self.extra or {}),
        }


@dataclass(frozen=True)
class GraphPolicyDecision:
    requires_human_review: bool = False
    handoff_reason: str | None = None
    handoff_summary: str | None = None
    handoff_suggestion: str | None = None
    handoff_payload: Mapping[str, Any] | None = None
    knowledge_query: str | None = None
    should_quote: bool = True
    draft_response: str | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "requires_human_review": self.requires_human_review,
            "handoff_reason": self.handoff_reason,
            "knowledge_query": self.knowledge_query,
            "should_quote": self.should_quote,
            "has_draft_response": self.draft_response is not None,
        }


@dataclass(frozen=True)
class GraphDecisionProviderConfig:
    provider: str
    endpoint: str | None
    auth_token_configured: bool
    timeout_seconds: float | None
    status: str
    message: str
    model: str | None = None
    api_key_env: str | None = None
    api_key_configured: bool = False

    def details(self) -> dict[str, str | float | bool | None]:
        return {
            "provider": self.provider,
            "endpoint": self.endpoint,
            "auth_token_configured": self.auth_token_configured,
            "timeout_seconds": self.timeout_seconds,
            "model": self.model,
            "api_key_env": self.api_key_env,
            "api_key_configured": self.api_key_configured,
        }


class GraphDecisionProvider(Protocol):
    name: str

    def decide(self, context: GraphPolicyContext) -> GraphPolicyDecision:
        raise NotImplementedError


class RuleBasedGraphDecisionProvider:
    name = RULE_BASED_PROVIDER

    def decide(self, context: GraphPolicyContext) -> GraphPolicyDecision:
        if context.stage == "qualify":
            if context.inquiry_id is None:
                return _handoff("missing_inquiry", "No inquiry is attached to this graph run.")
            if (context.score or {}).get("grade") == "C" and context.conversation_id is not None:
                return _handoff(
                    "low_quality_inquiry",
                    "Inquiry scored C and should be reviewed before AI sends a reply.",
                )
        if context.stage == "understand":
            parsed = _parsed(context)
            requirement = context.extra.get("requirement") or parsed or context.user_prompt
            if parsed.get("product") and not context.product_matches and context.conversation_id is not None:
                return _handoff(
                    "product_out_of_scope",
                    "No active product matched the inquiry requirement.",
                    suggestion="Review the inquiry manually or add the missing product to the catalog.",
                    payload={"requirement": parsed},
                    knowledge_query=_query_text(requirement),
                )
            return GraphPolicyDecision(knowledge_query=_query_text(requirement))
        if context.stage == "quote":
            parsed = _parsed(context)
            return GraphPolicyDecision(should_quote=bool(context.inquiry_id and parsed.get("quantity") and context.product_matches))
        return GraphPolicyDecision()


@dataclass(frozen=True)
class HttpGraphDecisionProvider:
    endpoint: str
    auth_token: str | None = None
    timeout_seconds: float = 10.0
    name: str = "http"

    def decide(self, context: GraphPolicyContext) -> GraphPolicyDecision:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        request = Request(
            self.endpoint,
            data=json.dumps(context.payload()).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if isinstance(payload, Mapping) and isinstance(payload.get("decision"), Mapping):
            payload = payload["decision"]
        return _decision_from_mapping(payload)


@dataclass(frozen=True)
class OpenAICompatibleGraphDecisionProvider:
    endpoint: str
    api_key: str
    model: str
    timeout_seconds: float = 10.0
    name: str = "openai"

    def decide(self, context: GraphPolicyContext) -> GraphPolicyDecision:
        request = Request(
            self.endpoint,
            data=json.dumps(self._payload(context)).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return _decision_from_openai_response(payload)

    def _payload(self, context: GraphPolicyContext) -> dict[str, Any]:
        return {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": OPENAI_GRAPH_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "context": context.payload(),
                            "decision_schema": {
                                "requires_human_review": "boolean",
                                "handoff_reason": "string|null",
                                "handoff_summary": "string|null",
                                "handoff_suggestion": "string|null",
                                "handoff_payload": "object|null",
                                "knowledge_query": "string|null",
                                "should_quote": "boolean",
                                "draft_response": "string|null",
                            },
                        }
                    ),
                },
            ],
        }


def get_graph_decision_provider(env: Mapping[str, str] | None = None) -> GraphDecisionProvider:
    env = env or os.environ
    provider = _provider_name(env)
    if provider == RULE_BASED_PROVIDER:
        return RuleBasedGraphDecisionProvider()
    if provider == "http":
        endpoint = _clean(env.get(GRAPH_POLICY_ENDPOINT_ENV))
        if endpoint is None:
            raise ValueError(f"{GRAPH_POLICY_ENDPOINT_ENV} is required for graph decision provider")
        return HttpGraphDecisionProvider(
            endpoint=endpoint,
            auth_token=_clean(env.get(GRAPH_POLICY_AUTH_TOKEN_ENV)),
            timeout_seconds=_timeout(env),
        )
    if provider == "openai":
        api_key_env = _api_key_env(env)
        api_key = _clean(env.get(api_key_env))
        model = _clean(env.get(GRAPH_POLICY_MODEL_ENV))
        if model is None:
            raise ValueError(f"{GRAPH_POLICY_MODEL_ENV} is required for graph decision LLM provider")
        if api_key is None:
            raise ValueError(f"{api_key_env} is required for graph decision LLM provider")
        return OpenAICompatibleGraphDecisionProvider(
            endpoint=_openai_endpoint(env),
            api_key=api_key,
            model=model,
            timeout_seconds=_timeout(env),
        )
    raise ValueError(f"Unsupported graph decision provider: {provider}")


def get_graph_decision_provider_config(env: Mapping[str, str] | None = None) -> GraphDecisionProviderConfig:
    env = env or os.environ
    provider = _provider_name(env)
    if provider == RULE_BASED_PROVIDER:
        return GraphDecisionProviderConfig(
            provider=provider,
            endpoint=None,
            auth_token_configured=False,
            timeout_seconds=None,
            status="warning",
            message="Rule-based graph decisions are active; configure a production decision provider.",
        )
    if provider == "http":
        endpoint = _clean(env.get(GRAPH_POLICY_ENDPOINT_ENV))
        timeout = _timeout(env)
        if endpoint is None:
            return GraphDecisionProviderConfig(
                provider=provider,
                endpoint=None,
                auth_token_configured=bool(_clean(env.get(GRAPH_POLICY_AUTH_TOKEN_ENV))),
                timeout_seconds=timeout,
                status="failed",
                message=f"{GRAPH_POLICY_ENDPOINT_ENV} is required for graph decision provider.",
            )
        return GraphDecisionProviderConfig(
            provider=provider,
            endpoint=endpoint,
            auth_token_configured=bool(_clean(env.get(GRAPH_POLICY_AUTH_TOKEN_ENV))),
            timeout_seconds=timeout,
            status="ok",
            message="Graph decision provider is configured.",
        )
    if provider == "openai":
        return _openai_provider_config(env)
    return GraphDecisionProviderConfig(
        provider=provider,
        endpoint=None,
        auth_token_configured=bool(_clean(env.get(GRAPH_POLICY_AUTH_TOKEN_ENV))),
        timeout_seconds=None,
        status="failed",
        message=f"Unsupported graph decision provider: {provider}",
    )


def _openai_provider_config(env: Mapping[str, str]) -> GraphDecisionProviderConfig:
    api_key_env = _api_key_env(env)
    model = _clean(env.get(GRAPH_POLICY_MODEL_ENV))
    api_key_configured = _clean(env.get(api_key_env)) is not None
    try:
        timeout = _timeout(env)
    except ValueError as exc:
        return GraphDecisionProviderConfig(
            provider="openai",
            endpoint=_openai_endpoint(env),
            auth_token_configured=False,
            timeout_seconds=None,
            status="failed",
            message=str(exc),
            model=model,
            api_key_env=api_key_env,
            api_key_configured=api_key_configured,
        )

    if model is None:
        return GraphDecisionProviderConfig(
            provider="openai",
            endpoint=_openai_endpoint(env),
            auth_token_configured=False,
            timeout_seconds=timeout,
            status="failed",
            message=f"{GRAPH_POLICY_MODEL_ENV} is required for graph decision LLM provider.",
            model=None,
            api_key_env=api_key_env,
            api_key_configured=api_key_configured,
        )
    if not api_key_configured:
        return GraphDecisionProviderConfig(
            provider="openai",
            endpoint=_openai_endpoint(env),
            auth_token_configured=False,
            timeout_seconds=timeout,
            status="failed",
            message=f"{api_key_env} is required for graph decision LLM provider.",
            model=model,
            api_key_env=api_key_env,
            api_key_configured=False,
        )
    return GraphDecisionProviderConfig(
        provider="openai",
        endpoint=_openai_endpoint(env),
        auth_token_configured=False,
        timeout_seconds=timeout,
        status="ok",
        message="Graph decision LLM provider is configured.",
        model=model,
        api_key_env=api_key_env,
        api_key_configured=True,
    )


def _decision_from_openai_response(payload: Any) -> GraphPolicyDecision:
    if isinstance(payload, Mapping) and isinstance(payload.get("decision"), Mapping):
        return _decision_from_mapping(payload["decision"])
    content = _openai_message_content(payload)
    try:
        value = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("Graph decision LLM response content must be valid JSON") from exc
    if isinstance(value, Mapping) and isinstance(value.get("decision"), Mapping):
        value = value["decision"]
    return _decision_from_mapping(value)


def _openai_message_content(payload: Any) -> str:
    if not isinstance(payload, Mapping):
        raise ValueError("Graph decision LLM response must be a JSON object")
    choices = payload.get("choices")
    if not isinstance(choices, Sequence) or isinstance(choices, (str, bytes, bytearray)) or not choices:
        raise ValueError("Graph decision LLM response must contain choices")
    choice = choices[0]
    if not isinstance(choice, Mapping):
        raise ValueError("Graph decision LLM choice must be an object")
    message = choice.get("message")
    if not isinstance(message, Mapping):
        raise ValueError("Graph decision LLM choice must contain a message")
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence) and not isinstance(content, (str, bytes, bytearray)):
        text = "".join(str(item.get("text", "")) for item in content if isinstance(item, Mapping))
        if text:
            return text
    raise ValueError("Graph decision LLM message content must be text")


def _decision_from_mapping(value: Any) -> GraphPolicyDecision:
    if not isinstance(value, Mapping):
        raise ValueError("Graph decision response must be an object")
    return GraphPolicyDecision(
        requires_human_review=bool(value.get("requires_human_review")),
        handoff_reason=_clean(value.get("handoff_reason")),
        handoff_summary=_clean(value.get("handoff_summary")),
        handoff_suggestion=_clean(value.get("handoff_suggestion")),
        handoff_payload=value.get("handoff_payload") if isinstance(value.get("handoff_payload"), Mapping) else None,
        knowledge_query=_clean(value.get("knowledge_query")),
        should_quote=bool(value.get("should_quote", True)),
        draft_response=_clean(value.get("draft_response")),
    )


def _handoff(
    reason: str,
    summary: str,
    *,
    suggestion: str | None = None,
    payload: Mapping[str, Any] | None = None,
    knowledge_query: str | None = None,
) -> GraphPolicyDecision:
    return GraphPolicyDecision(
        requires_human_review=True,
        handoff_reason=reason,
        handoff_summary=summary,
        handoff_suggestion=suggestion,
        handoff_payload=payload,
        knowledge_query=knowledge_query,
        should_quote=False,
    )


def _parsed(context: GraphPolicyContext) -> dict[str, Any]:
    inquiry = context.inquiry or {}
    parsed = inquiry.get("parsed") if isinstance(inquiry, Mapping) else None
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _query_text(requirement: Any) -> str:
    if isinstance(requirement, str):
        return requirement
    if isinstance(requirement, Mapping):
        return " ".join(str(value) for value in requirement.values() if value)
    return str(requirement or "")


def _provider_name(env: Mapping[str, str]) -> str:
    value = (_clean(env.get(GRAPH_POLICY_PROVIDER_ENV)) or RULE_BASED_PROVIDER).lower()
    if value in HTTP_PROVIDER_ALIASES:
        return "http"
    if value in OPENAI_PROVIDER_ALIASES:
        return "openai"
    return value


def _api_key_env(env: Mapping[str, str]) -> str:
    return _clean(env.get(GRAPH_POLICY_API_KEY_ENV)) or OPENAI_API_KEY_ENV


def _openai_endpoint(env: Mapping[str, str]) -> str:
    explicit = _clean(env.get(GRAPH_POLICY_ENDPOINT_ENV))
    if explicit:
        return explicit
    base_url = (_clean(env.get(GRAPH_POLICY_BASE_URL_ENV)) or DEFAULT_OPENAI_BASE_URL).rstrip("/")
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


def _timeout(env: Mapping[str, str]) -> float:
    value = _clean(env.get(GRAPH_POLICY_TIMEOUT_ENV))
    timeout = float(value) if value else 10.0
    if timeout <= 0:
        raise ValueError("Graph decision timeout must be positive")
    return timeout


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None
