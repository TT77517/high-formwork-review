"""按规则缓存 Dify 完整性审查结果，并提供稳定的证据包哈希。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from dotenv import load_dotenv

from .services.dify_client import (
    DifyError,
    validate_review_result_with_warnings,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
DATA_ROOT = Path(os.getenv("DATA_ROOT", PROJECT_ROOT / "data")).expanduser()
if not DATA_ROOT.is_absolute():
    DATA_ROOT = PROJECT_ROOT / DATA_ROOT
CACHE_ROOT = DATA_ROOT / "cache" / "dify"
_CACHE_KEY_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()
_STABLE_PACKAGE_KEYS = (
    "rule_id",
    "item_name",
    "section_aliases",
    "matched_sections",
    "unmatched_aliases",
    "page_ranges",
    "evidence_text",
    "character_count",
)


@dataclass(frozen=True)
class DifyCacheLookup:
    result: dict[str, Any] | None
    warning: dict[str, Any] | None = None


def stable_evidence_package_hash(package: dict[str, Any]) -> str:
    """Hash only stable, business-relevant evidence package fields."""
    stable_package = {
        key: package.get(key)
        for key in _STABLE_PACKAGE_KEYS
        if key in package
    }
    serialized = json.dumps(
        stable_package,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


compute_evidence_package_hash = stable_evidence_package_hash


def build_dify_cache_key(
    source_sha256: str,
    rule_id: str,
    evidence_package_hash: str,
    workflow_version: str,
    prompt_version: str,
    model_identifier: str,
    output_schema_version: str,
) -> str:
    """Build a compact readable key containing every invalidation dimension.

    The full values are also stored in ``metadata.json``.  A compact key keeps
    Windows cache paths below the platform path-length limit while the digest
    preserves differences in long version values.
    """
    source = str(source_sha256).strip()
    if not source:
        raise ValueError("source_sha256 is required for Dify cache")
    values = (
        source,
        rule_id,
        evidence_package_hash,
        workflow_version,
        prompt_version,
        model_identifier,
        output_schema_version,
    )
    serialized = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
    return "-".join(
        (
            _safe_component(source)[:16],
            _safe_component(rule_id)[:24],
            _safe_component(evidence_package_hash)[:16],
            _safe_component(workflow_version)[:12],
            _safe_component(prompt_version)[:12],
            _safe_component(model_identifier)[:12],
            _safe_component(output_schema_version)[:12],
            digest,
        )
    )


build_cache_key = build_dify_cache_key


def cache_directory(
    cache_key: str,
    cache_root: str | Path = CACHE_ROOT,
) -> Path:
    if not cache_key or Path(cache_key).name != cache_key or ".." in cache_key:
        raise ValueError("Dify cache_key is invalid")
    return Path(cache_root) / cache_key


def load_cached_rule_result(
    *,
    cache_key: str,
    source_sha256: str,
    rule_id: str,
    evidence_package_hash: str,
    workflow_version: str,
    prompt_version: str,
    model_identifier: str,
    output_schema_version: str,
    cache_root: str | Path = CACHE_ROOT,
) -> DifyCacheLookup:
    """Return a validated rule result or a warning-bearing cache miss."""
    directory = cache_directory(cache_key, cache_root)
    result_path = directory / "result.json"
    metadata_path = directory / "metadata.json"
    if not result_path.exists() and not metadata_path.exists():
        return DifyCacheLookup(result=None)
    if not result_path.is_file() or not metadata_path.is_file():
        return DifyCacheLookup(
            result=None,
            warning=_warning(rule_id, "Dify 缓存文件不完整，已视为未命中"),
        )

    expected = {
        "cache_key": cache_key,
        "source_sha256": source_sha256,
        "rule_id": rule_id,
        "evidence_package_hash": evidence_package_hash,
        "workflow_version": workflow_version,
        "prompt_version": prompt_version,
        "model_identifier": model_identifier,
        "output_schema_version": output_schema_version,
        "status": "success",
    }
    try:
        if result_path.stat().st_size == 0 or metadata_path.stat().st_size == 0:
            raise ValueError("empty cache file")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("metadata is not an object")
        if any(metadata.get(key) != value for key, value in expected.items()):
            raise ValueError("cache metadata does not match request")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        validated, warnings = validate_review_result_with_warnings(
            {"results": [result]},
            [rule_id],
            allow_unrequested=False,
        )
        if warnings:
            raise ValueError("cached result contains validation warnings")
        items = validated.get("results") if isinstance(validated, dict) else None
        if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
            raise ValueError("cached result has an invalid rule shape")
        return DifyCacheLookup(result=items[0])
    except (OSError, json.JSONDecodeError, TypeError, ValueError, DifyError):
        return DifyCacheLookup(
            result=None,
            warning=_warning(rule_id, "Dify 缓存损坏或结构无效，已视为未命中"),
        )


def save_cached_rule_result(
    *,
    cache_key: str,
    source_sha256: str,
    rule_id: str,
    evidence_package_hash: str,
    workflow_version: str,
    prompt_version: str,
    model_identifier: str,
    output_schema_version: str,
    result: dict[str, Any],
    input_chars: int,
    duration_ms: int,
    cache_root: str | Path = CACHE_ROOT,
) -> None:
    """Validate and atomically write one successful rule result."""
    validated, warnings = validate_review_result_with_warnings(
        {"results": [result]},
        [rule_id],
        allow_unrequested=False,
    )
    if warnings:
        raise ValueError("cannot cache a result with validation warnings")
    items = validated.get("results") if isinstance(validated, dict) else None
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        raise ValueError("cannot cache an invalid rule result")

    directory = cache_directory(cache_key, cache_root)
    directory.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(directory / "result.json", _redact_secret(items[0]))
    _atomic_write_json(
        directory / "metadata.json",
        {
            "cache_key": cache_key,
            "source_sha256": source_sha256,
            "rule_id": rule_id,
            "evidence_package_hash": evidence_package_hash,
            "workflow_version": workflow_version,
            "prompt_version": prompt_version,
            "model_identifier": model_identifier,
            "output_schema_version": output_schema_version,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": "success",
            "input_chars": int(input_chars),
            "duration_ms": int(duration_ms),
        },
    )


save_rule_cache = save_cached_rule_result


@contextmanager
def cache_lock(
    cache_key: str,
    cache_root: str | Path = CACHE_ROOT,
) -> Iterator[None]:
    lock_key = f"{Path(cache_root).resolve()}::{cache_key}"
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(lock_key, threading.Lock())
    with lock:
        yield


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}-",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def _warning(rule_id: str, message: str) -> dict[str, Any]:
    return {
        "code": "DIFY_CACHE_WARNING",
        "rule_id": rule_id,
        "message": message,
    }


def _safe_component(value: Any) -> str:
    component = _CACHE_KEY_SAFE.sub("-", str(value).strip())
    return component.strip(".-") or "unknown"


def _redact_secret(value: Any) -> Any:
    secret = os.getenv("DIFY_API_KEY", "").strip()
    if not secret:
        return value
    if isinstance(value, dict):
        return {key: _redact_secret(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_secret(item) for item in value]
    if isinstance(value, str):
        return value.replace(secret, "[redacted]")
    return value
