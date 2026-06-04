"""LLM 配置单一事实来源（modules/llm_config.py）的单元测试。

重点验证：
- 配置规范化：缺失字段回退默认、死字段被丢弃。
- 密钥解析优先级：环境变量 > 本次会话输入 > 本机钥匙串。
- 记住/遗忘密钥正确委托给 secret_store。
- 密钥永不出现在方案 dict 中（可审计的安全不变量）。
"""

from __future__ import annotations

import pytest

from modules import llm_config

pytestmark = pytest.mark.unit


# ── normalize ──────────────────────────────────────────────────────────


def test_normalize_fills_defaults_when_empty() -> None:
    cfg = llm_config.normalize(None)
    assert cfg["model"] == "deepseek-chat"
    assert cfg["base_url"] == "https://api.deepseek.com"
    assert cfg["profile_name"] == "默认"
    assert cfg["keychain_account"] == "default"
    assert cfg["profile_id"] == ""


def test_normalize_drops_dead_and_unknown_fields() -> None:
    cfg = llm_config.normalize(
        {
            "model": "gpt-4o",
            "key_source": "env_or_keychain",  # 已废弃的死字段
            "api_key": "sk-should-not-survive",  # 密钥绝不能进方案
            "garbage": 123,
        }
    )
    assert cfg["model"] == "gpt-4o"
    assert "key_source" not in cfg
    assert "api_key" not in cfg
    assert "garbage" not in cfg
    assert set(cfg.keys()) == set(llm_config.PROFILE_FIELDS)


def test_normalize_strips_whitespace() -> None:
    cfg = llm_config.normalize({"model": "  glm-4  ", "base_url": "  http://x  "})
    assert cfg["model"] == "glm-4"
    assert cfg["base_url"] == "http://x"


# ── key_account ────────────────────────────────────────────────────────


def test_key_account_prefers_explicit_account() -> None:
    assert llm_config.key_account({"keychain_account": "openai-prod", "profile_id": "llm_x"}) == "openai-prod"


def test_key_account_falls_back_to_profile_id_then_default() -> None:
    # normalize 会把空 keychain_account 填成 "default"，所以这里验证显式 default 时退回 profile_id
    assert llm_config.key_account({"keychain_account": "default", "profile_id": "llm_x"}) == "default"
    assert llm_config.key_account({"profile_id": "llm_x", "keychain_account": ""})  # 非空即可
    assert llm_config.key_account(None) == "default"


# ── resolve_key 优先级 ─────────────────────────────────────────────────


def test_resolve_key_env_wins(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
    key, source = llm_config.resolve_key("default", manual="sk-manual")
    assert key == "sk-env"
    assert "环境变量" in source


def test_resolve_key_env_priority_order(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("LLM_API_KEY", "sk-generic")
    key, source = llm_config.resolve_key("default")
    assert key == "sk-openai"
    assert "OPENAI_API_KEY" in source


def test_resolve_key_manual_when_no_env(monkeypatch) -> None:
    for name in llm_config.ENV_KEY_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(llm_config.secret_store, "get_secret", lambda account: "")
    key, source = llm_config.resolve_key("default", manual="  sk-manual  ")
    assert key == "sk-manual"
    assert source == "本次会话输入"


def test_resolve_key_keychain_when_no_env_no_manual(monkeypatch) -> None:
    for name in llm_config.ENV_KEY_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(llm_config.secret_store, "get_secret", lambda account: "sk-stored" if account == "acct1" else "")
    key, source = llm_config.resolve_key("acct1")
    assert key == "sk-stored"
    assert "本机钥匙串：acct1" in source


def test_resolve_key_unconfigured(monkeypatch) -> None:
    for name in llm_config.ENV_KEY_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(llm_config.secret_store, "get_secret", lambda account: "")
    key, source = llm_config.resolve_key("default")
    assert key == ""
    assert source == "未配置"


# ── remember / forget / has ────────────────────────────────────────────


def test_remember_key_delegates_to_secret_store(monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr(
        llm_config.secret_store,
        "set_secret",
        lambda account, secret: captured.update(account=account, secret=secret) or True,
    )
    assert llm_config.remember_key("acct1", "  sk-1  ") is True
    assert captured == {"account": "acct1", "secret": "sk-1"}


def test_remember_key_blank_account_uses_default(monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr(
        llm_config.secret_store,
        "set_secret",
        lambda account, secret: captured.update(account=account) or True,
    )
    llm_config.remember_key("", "sk-1")
    assert captured["account"] == "default"


def test_forget_key_delegates(monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr(
        llm_config.secret_store,
        "delete_secret",
        lambda account: captured.update(account=account) or True,
    )
    assert llm_config.forget_key("acct1") is True
    assert captured["account"] == "acct1"


def test_has_remembered_key(monkeypatch) -> None:
    monkeypatch.setattr(llm_config.secret_store, "get_secret", lambda account: "sk" if account == "acct1" else "")
    assert llm_config.has_remembered_key("acct1") is True
    assert llm_config.has_remembered_key("acct2") is False
