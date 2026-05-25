"""Runtime context helpers for per-user storage isolation."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

_SANITIZE_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff._-]+")
_SESSION_KEYS = ("auth_user_id", "user_id", "username", "account", "login_user")


def _session_value() -> str | None:
    try:
        import streamlit as st  # type: ignore
    except Exception:
        return None

    session = getattr(st, "session_state", None)
    if session is None:
        return None

    for key in _SESSION_KEYS:
        value = session.get(key)
        if value:
            return str(value).strip()
    return None


def _sanitize_namespace(value: str) -> str:
    cleaned = _SANITIZE_RE.sub("_", str(value).strip())
    cleaned = cleaned.strip("._-")[:64]
    return cleaned or "shared"


def current_storage_namespace() -> str | None:
    """
    Return an explicit storage namespace when the deployment provides one.

    We intentionally do not fall back to OS username here so that the default
    local single-user behavior keeps using the legacy root path.
    """
    explicit = os.environ.get("JOURNAL_AUDIT_STORAGE_NAMESPACE", "").strip()
    if explicit:
        return _sanitize_namespace(explicit)

    explicit = os.environ.get("JOURNAL_AUDIT_USER_ID", "").strip()
    if explicit:
        return _sanitize_namespace(explicit)

    session_value = _session_value()
    if session_value:
        return _sanitize_namespace(session_value)

    return None


def storage_root() -> Path:
    base = Path.home() / ".audit_tool"
    namespace = current_storage_namespace()
    if not namespace:
        return base
    return base / "users" / namespace


def storage_namespace_label() -> str:
    namespace = current_storage_namespace()
    return namespace or "legacy"


def namespace_path(*parts: Any) -> Path:
    return storage_root().joinpath(*map(str, parts))
