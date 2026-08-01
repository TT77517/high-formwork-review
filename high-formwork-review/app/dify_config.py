"""Dify completeness review mode configuration."""

from __future__ import annotations

import os
from typing import Literal

from dotenv import load_dotenv


DifyCompletenessMode = Literal["off", "on_demand", "full"]
DEFAULT_DIFY_COMPLETENESS_MODE: DifyCompletenessMode = "on_demand"
VALID_DIFY_COMPLETENESS_MODES = {"off", "on_demand", "full"}


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
        load_dotenv()

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


def _truthy(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "on"}
