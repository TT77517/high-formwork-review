"""Dify completeness review mode configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"


def _load_project_env() -> None:
    """加载项目根 .env，与启动目录无关（override=False 不覆盖已显式导出的变量）。"""
    load_dotenv(ENV_PATH, override=False)


DifyCompletenessMode = Literal["off", "on_demand", "full"]
DEFAULT_DIFY_COMPLETENESS_MODE: DifyCompletenessMode = "on_demand"
VALID_DIFY_COMPLETENESS_MODES = {"off", "on_demand", "full"}
DEFAULT_DIFY_CACHE_ENABLED = False
DEFAULT_DIFY_WORKFLOW_VERSION = "v1"
DEFAULT_DIFY_PROMPT_VERSION = "v2"
DEFAULT_DIFY_MODEL_IDENTIFIER = "unknown"
DEFAULT_DIFY_OUTPUT_SCHEMA_VERSION = "v1"


@dataclass(frozen=True)
class DifyReviewConfig:
    """集中管理 Dify 缓存键所需的可变版本信息。"""

    cache_enabled: bool
    workflow_version: str
    prompt_version: str
    model_identifier: str
    output_schema_version: str


def resolve_dify_review_config(*, load_environment: bool = True) -> DifyReviewConfig:
    """Resolve cache and audit configuration without requiring Dify credentials."""
    if load_environment:
        _load_project_env()
    return DifyReviewConfig(
        cache_enabled=_env_truthy(
            "DIFY_CACHE_ENABLED", DEFAULT_DIFY_CACHE_ENABLED
        ),
        workflow_version=_env_text(
            "DIFY_WORKFLOW_VERSION", DEFAULT_DIFY_WORKFLOW_VERSION
        ),
        prompt_version=_env_text(
            "DIFY_PROMPT_VERSION", DEFAULT_DIFY_PROMPT_VERSION
        ),
        model_identifier=_env_text(
            "DIFY_MODEL_IDENTIFIER", DEFAULT_DIFY_MODEL_IDENTIFIER
        ),
        output_schema_version=_env_text(
            "DIFY_OUTPUT_SCHEMA_VERSION", DEFAULT_DIFY_OUTPUT_SCHEMA_VERSION
        ),
    )


def resolve_dify_completeness_mode(
    *,
    explicit_mode: str | None = None,
    web_enable_dify: str | bool | None = None,
    load_environment: bool = True,
) -> DifyCompletenessMode:
    """Resolve the effective Dify completeness review mode.

    ``WEB_ENABLE_DIFY=false`` is a compatibility switch and forces ``off``.
    Otherwise ``DIFY_COMPLETENESS_MODE`` defaults to ``on_demand``.
    """
    if load_environment:
        _load_project_env()

    web_value = (
        os.getenv("WEB_ENABLE_DIFY")
        if web_enable_dify is None and load_environment
        else web_enable_dify
    )
    if web_value is not None and not _truthy(web_value):
        return "off"

    mode = explicit_mode
    if mode is None and load_environment:
        mode = os.getenv("DIFY_COMPLETENESS_MODE")
    mode = (mode or DEFAULT_DIFY_COMPLETENESS_MODE).strip().lower()
    if mode not in VALID_DIFY_COMPLETENESS_MODES:
        allowed = ", ".join(sorted(VALID_DIFY_COMPLETENESS_MODES))
        raise ValueError(f"DIFY_COMPLETENESS_MODE 无效：{mode}，允许值：{allowed}")
    return mode  # type: ignore[return-value]


def resolve_semantic_review_mode(
    *,
    explicit_mode: str | None = None,
    load_environment: bool = True,
) -> str:
    """语义审查模式：``local`` / ``dify`` / ``agent``。

    - ``local``：关键词匹配（默认）
    - ``dify``：Dify Workflow 批式 LLM 判定
    - ``agent``：Evidence Agent 工具循环（代码侧直连 LLM tool calling），
      失败时降级 dify 批式，再失败降级本地，任务不中断
    """
    if load_environment:
        _load_project_env()
    mode = explicit_mode
    if mode is None and load_environment:
        mode = os.getenv("SEMANTIC_REVIEW_MODE")
    mode = (mode or "local").strip().lower()
    if mode not in {"local", "dify", "agent"}:
        raise ValueError("SEMANTIC_REVIEW_MODE 无效，允许值：local, dify, agent")
    return mode


def resolve_semantic_api_key(*, load_environment: bool = True) -> str:
    """语义审查 Workflow 的 API Key；未单独配置时回退完整性审查的 Key。"""
    if load_environment:
        _load_project_env()
    key = os.getenv("DIFY_SEMANTIC_API_KEY", "").strip()
    if key:
        return key
    return os.getenv("DIFY_API_KEY", "").strip()


def _truthy(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_truthy(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else _truthy(value)


def _env_text(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()
    return value or default
