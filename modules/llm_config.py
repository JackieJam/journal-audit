"""LLM 配置与密钥解析 —— 单一事实来源。

把两层关注点集中到一处，避免散落在 app.py / sidebar.py 各处重复：

1. 方案（非密钥配置）：``profile_name`` / ``model`` / ``base_url``。
   持久化由 ``knowledge_base`` 负责（``llm_profiles.json``），不含密钥。
2. API Key（密钥）：跟随方案存本机钥匙串/文件后端（``secret_store`` 负责），
   按 ``keychain_account`` 隔离 —— 默认用方案自身的 id 作为账户名，做到「一套方案一把钥匙」。

密钥解析优先级（高 → 低）：
    环境变量 > 本次会话手动输入 > 本机钥匙串

设计约束：
- 本模块**不依赖 streamlit**，纯函数，可单测。
- 密钥永远不进入返回的方案 dict、不写入 ``llm_profiles.json``、不写入项目缓存。
"""

from __future__ import annotations

import os

from config.constants import DEFAULT_LLM_CONFIG
from modules import secret_store

# 兼容多家厂商的环境变量名（按优先级），任一命中即用。
ENV_KEY_VARS: tuple[str, ...] = ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY")

# 方案 dict 的合法字段（不含任何密钥）。
PROFILE_FIELDS: tuple[str, ...] = (
    "profile_id",
    "profile_name",
    "model",
    "base_url",
    "keychain_account",
)


def _clean(value: object) -> str:
    return str(value).strip() if value is not None else ""


def normalize(raw: dict | None = None) -> dict[str, str]:
    """把任意来源的配置规范化为标准方案 dict，缺失字段回退默认值。

    只保留 :data:`PROFILE_FIELDS`，顺手丢弃历史遗留的死字段（如 ``key_source``）。
    """
    src = raw or {}
    return {
        "profile_id": _clean(src.get("profile_id")),
        "profile_name": _clean(src.get("profile_name")) or DEFAULT_LLM_CONFIG["profile_name"],
        "model": _clean(src.get("model")) or DEFAULT_LLM_CONFIG["model"],
        "base_url": _clean(src.get("base_url")) or DEFAULT_LLM_CONFIG["base_url"],
        "keychain_account": _clean(src.get("keychain_account")) or DEFAULT_LLM_CONFIG["keychain_account"],
    }


def key_account(cfg: dict | None) -> str:
    """方案对应的钥匙串账户名：优先 ``keychain_account``，否则退回 ``profile_id``，再否则 ``default``。"""
    norm = normalize(cfg)
    return norm["keychain_account"] or norm["profile_id"] or "default"


def env_api_key() -> tuple[str, str]:
    """从环境变量解析密钥。返回 ``(key, source)``；未命中则 ``("", "")``。"""
    for name in ENV_KEY_VARS:
        value = os.environ.get(name, "").strip()
        if value:
            return value, f"环境变量 {name}"
    return "", ""


def resolve_key(keychain_account: str, *, manual: str = "") -> tuple[str, str]:
    """按优先级解析当前可用的 API Key。

    返回 ``(key, source)``。``source`` 是给 UI 展示的可审计来源说明，
    未配置时返回 ``("", "未配置")``。
    """
    key, source = env_api_key()
    if key:
        return key, source

    manual_key = (manual or "").strip()
    if manual_key:
        return manual_key, "本次会话输入"

    account = (keychain_account or "").strip() or "default"
    stored = secret_store.get_secret(account)
    if stored:
        return stored, f"本机钥匙串：{account}"

    return "", "未配置"


def remember_key(keychain_account: str, key: str) -> bool:
    """把密钥写入本机钥匙串/文件后端，供下次会话自动恢复。"""
    account = (keychain_account or "").strip() or "default"
    return secret_store.set_secret(account, (key or "").strip())


def forget_key(keychain_account: str) -> bool:
    """删除本机存储的密钥（「不再记住」）。"""
    account = (keychain_account or "").strip() or "default"
    return secret_store.delete_secret(account)


def has_remembered_key(keychain_account: str) -> bool:
    """该账户名下是否已有记住的密钥。"""
    account = (keychain_account or "").strip() or "default"
    return bool(secret_store.get_secret(account))
