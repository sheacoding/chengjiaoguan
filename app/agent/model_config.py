"""
/* ========================================================================== */
/* GEB L3: Agent 模型配置                                                     */
/* ========================================================================== */
/**
 * [INPUT]: 依赖 os.environ 与 PydanticAI model 字符串约定
 * [OUTPUT]: 对外提供 AgentModelConfig、configured_agent_model、selected_agent_model、get_agent_model_config
 * [POS]: app/agent 的生产模型配置边界，让 runtime 与 readiness 共享同一份 LLM 配置事实
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


MODEL_ENV = "CLOSER_AGENT_MODEL"
API_KEY_ENV_OVERRIDE = "CLOSER_AGENT_API_KEY_ENV"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"


@dataclass(frozen=True)
class AgentModelConfig:
    model: str | None
    provider: str | None
    api_key_env: str | None
    status: str
    message: str

    def details(self) -> dict[str, str | None]:
        return {
            "model": self.model,
            "provider": self.provider,
            "api_key_env": self.api_key_env,
        }


def configured_agent_model(env: Mapping[str, str] | None = None) -> str | None:
    return _clean((env or os.environ).get(MODEL_ENV))


def selected_agent_model(explicit_model: Any | None, env: Mapping[str, str] | None = None) -> Any | None:
    if explicit_model is not None:
        return explicit_model
    return configured_agent_model(env)


def get_agent_model_config(env: Mapping[str, str] | None = None) -> AgentModelConfig:
    env = env or os.environ
    model = configured_agent_model(env)
    if model is None:
        return AgentModelConfig(
            model=None,
            provider=None,
            api_key_env=None,
            status="warning",
            message=f"{MODEL_ENV} is not configured; runtime must pass an explicit model.",
        )

    provider = _provider(model)
    api_key_env = _api_key_env(provider, env)
    if api_key_env and not _clean(env.get(api_key_env)):
        return AgentModelConfig(
            model=model,
            provider=provider,
            api_key_env=api_key_env,
            status="failed",
            message=f"{api_key_env} is required for {provider} agent model.",
        )

    return AgentModelConfig(
        model=model,
        provider=provider,
        api_key_env=api_key_env,
        status="ok",
        message="Agent model is configured.",
    )


def _provider(model: str) -> str:
    if ":" in model:
        return model.split(":", 1)[0].lower()
    if model.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    return "custom"


def _api_key_env(provider: str, env: Mapping[str, str]) -> str | None:
    override = _clean(env.get(API_KEY_ENV_OVERRIDE))
    if override:
        return override
    if provider == "openai":
        return OPENAI_API_KEY_ENV
    return None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None
