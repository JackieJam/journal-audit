"""Simple per-namespace LLM call quota tracking."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from modules.locking import file_lock
from modules.runtime_context import namespace_path, storage_namespace_label

USAGE_FILE = "llm_usage.json"


def _usage_path() -> Path:
    return namespace_path(USAGE_FILE)


def _lock_path() -> Path:
    return namespace_path(f".{USAGE_FILE}.lock")


def _daily_limit() -> int:
    raw = os.environ.get("JOURNAL_AUDIT_LLM_DAILY_LIMIT", "").strip()
    if not raw:
        return 0
    try:
        return max(int(raw), 0)
    except Exception:
        return 0


def _load_usage() -> dict[str, Any]:
    path = _usage_path()
    if not path.exists():
        return {"namespace": storage_namespace_label(), "days": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"namespace": storage_namespace_label(), "days": {}}
    if not isinstance(data, dict):
        return {"namespace": storage_namespace_label(), "days": {}}
    data.setdefault("namespace", storage_namespace_label())
    data.setdefault("days", {})
    if not isinstance(data["days"], dict):
        data["days"] = {}
    return data


def _save_usage(data: dict[str, Any]) -> None:
    path = _usage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def quota_status(limit: int | None = None) -> dict[str, Any]:
    data = _load_usage()
    today = date.today().isoformat()
    day_info = data.get("days", {}).get(today, {})
    current = int(day_info.get("count", 0) or 0)
    effective_limit = _daily_limit() if limit is None else max(int(limit), 0)
    return {
        "namespace": data.get("namespace", storage_namespace_label()),
        "date": today,
        "current": current,
        "limit": effective_limit,
        "remaining": None if effective_limit <= 0 else max(effective_limit - current, 0),
    }


def record_llm_call(operation: str, *, limit: int | None = None) -> dict[str, Any]:
    """
    Record one LLM request for the current namespace and enforce optional quota.

    A limit of 0 means unlimited.
    """
    today = date.today().isoformat()
    effective_limit = _daily_limit() if limit is None else max(int(limit), 0)

    with file_lock(_lock_path(), exclusive=True):
        data = _load_usage()
        days = data.setdefault("days", {})
        day_info = days.setdefault(today, {"count": 0, "operations": {}})
        if not isinstance(day_info, dict):
            day_info = {"count": 0, "operations": {}}
            days[today] = day_info

        current_count = int(day_info.get("count", 0) or 0) + 1
        day_info["count"] = current_count
        operations = day_info.setdefault("operations", {})
        operations[operation] = int(operations.get(operation, 0) or 0) + 1
        day_info["last_operation"] = operation
        day_info["namespace"] = storage_namespace_label()
        data["namespace"] = storage_namespace_label()
        _save_usage(data)

    if effective_limit > 0 and current_count > effective_limit:
        raise RuntimeError(
            f"当前命名空间 {storage_namespace_label()} 的 LLM 日调用额度已用尽（{current_count}/{effective_limit}）。"
        )

    return {
        "namespace": storage_namespace_label(),
        "date": today,
        "current": current_count,
        "limit": effective_limit,
        "remaining": None if effective_limit <= 0 else max(effective_limit - current_count, 0),
    }
