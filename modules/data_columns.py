"""
共享分析列补充模块。

将 add_analysis_columns() 从 visual_analysis.py 提取到此模块，
消除 profiler → visual_analysis 的反向依赖。
"""

from __future__ import annotations

import pandas as pd

from modules.account_classifier import auto_classify


def _account_text_col(df: pd.DataFrame) -> str | None:
    for col in ("总账科目：长文本", "总账科目：短文本"):
        if col in df.columns:
            return col
    return None


def _safe_text(df: pd.DataFrame, col: str) -> pd.Series:
    if col in df.columns:
        return df[col].fillna("").astype(str)
    return pd.Series("", index=df.index)


def _category_overrides() -> dict[str, str]:
    """从 session_state 读取用户的科目分类覆盖；非 streamlit 环境返回空。"""
    try:
        import streamlit as st  # type: ignore

        raw = st.session_state.get("account_category_overrides")
    except Exception:
        return {}
    if isinstance(raw, dict):
        return {str(k).strip(): str(v).strip() for k, v in raw.items() if str(k).strip()}
    return {}


def _display_party(code: object, name: object) -> str:
    code_s = "" if pd.isna(code) else str(code).replace(".0", "").strip()
    name_s = "" if pd.isna(name) else str(name).strip()
    if code_s and name_s:
        return f"{code_s} - {name_s}"
    return code_s or name_s or "未维护"


def _related_party_category(account_name: object, default: str = "") -> str:
    text = "" if pd.isna(account_name) else str(account_name)
    if "内部关联" in text:
        return "内部关联方"
    if "外部关联" in text:
        return "外部关联方"
    if "第三方" in text:
        return "第三方"
    if "其他" in text and default != "第三方":
        return "其他"
    return default


def _pnl_category(acct4: object, account_name: object) -> str:
    acct4_s = "" if pd.isna(acct4) else str(acct4)
    if acct4_s in ("6001", "6401"):
        return f"主营业务-{_related_party_category(account_name, default='第三方')}"
    if acct4_s in ("6051", "6402"):
        related = _related_party_category(account_name)
        return f"其他业务-{related}" if related else "其他业务"
    return ""


def add_analysis_columns(df: pd.DataFrame) -> pd.DataFrame:
    """补充审计可视化常用列，不修改原始 DataFrame。"""
    out = df.copy()
    out["_acct"] = out["总账科目"].astype(str).str.strip()
    out["_acct4"] = out["_acct"].str[:4]
    out["_month"] = out["过账日期"].dt.month
    amount_col = "公司代码货币价值" if "公司代码货币价值" in out.columns else "凭证货币价值"
    out["_amount_raw"] = pd.to_numeric(out[amount_col], errors="coerce").fillna(0)
    out["_amount_abs"] = out["_amount_raw"].abs()
    out["_dc"] = out["借/贷标识"].astype(str).str.strip()
    out["_debit_amount"] = out["_amount_raw"].where(out["_dc"] == "S", 0)
    out["_credit_amount"] = out["_amount_raw"].where(out["_dc"] == "H", 0)
    out["_debit_abs"] = out["_amount_abs"].where(out["_dc"] == "S", 0)
    out["_credit_abs"] = out["_amount_abs"].where(out["_dc"] == "H", 0)
    out["_pnl_effect"] = -out["_amount_raw"]

    account_text = _account_text_col(out)
    out["_account_name"] = _safe_text(out, account_text) if account_text else ""
    out["_pnl_category"] = [
        _pnl_category(acct4, account_name)
        for acct4, account_name in zip(out["_acct4"], out["_account_name"], strict=False)
    ]

    # ── 自动分类 + 用户覆盖 ──
    overrides = _category_overrides()
    auto_cats = out["_account_name"].map(auto_classify)
    if overrides:
        manual = out["_acct"].map(overrides)
        out["_acct_category"] = manual.where(manual.notna() & manual.astype(bool), auto_cats)
    else:
        out["_acct_category"] = auto_cats

    out["_header_text"] = _safe_text(out, "凭证抬头摘要")
    out["_line_text"] = _safe_text(out, "文本")
    out["_combined_text"] = (out["_header_text"] + " " + out["_line_text"]).str.strip()

    customer_code = _safe_text(out, "客户")
    customer_name = _safe_text(out, "客户科目：姓名 1")
    vendor_code = _safe_text(out, "供应商编号")
    vendor_name = _safe_text(out, "供应商科目：名称 1")
    out["_customer_display"] = [
        _display_party(code, name) for code, name in zip(customer_code, customer_name, strict=False)
    ]
    out["_vendor_display"] = [
        _display_party(code, name) for code, name in zip(vendor_code, vendor_name, strict=False)
    ]
    material_code = _safe_text(out, "物料")
    material_name = _safe_text(out, "物料：描述")
    material_group_code = _safe_text(out, "物料组")
    material_group_name = _safe_text(out, "物料组描述")
    cost_center_code = _safe_text(out, "成本中心")
    cost_center_name = _safe_text(out, "成本中心：长文本")
    out["_material_display"] = [
        _display_party(code, name) for code, name in zip(material_code, material_name, strict=False)
    ]
    out["_material_group_display"] = [
        _display_party(code, name) for code, name in zip(material_group_code, material_group_name, strict=False)
    ]
    out["_cost_center_display"] = [
        _display_party(code, name) for code, name in zip(cost_center_code, cost_center_name, strict=False)
    ]
    out["_cost_account_display"] = [
        _display_party(code, name) for code, name in zip(out["_acct"], out["_account_name"], strict=False)
    ]

    reversal_cols = [c for c in ("反记账", "反记帐", "冲销标识") if c in out.columns]
    if reversal_cols:
        out["_reversal_text"] = out[reversal_cols].fillna("").astype(str).agg(" ".join, axis=1).str.strip()
    else:
        out["_reversal_text"] = ""

    return out


REQUIRED_ANALYSIS_COLUMNS = {
    "_acct",
    "_acct4",
    "_acct_category",
    "_month",
    "_amount_raw",
    "_amount_abs",
    "_dc",
    "_debit_amount",
    "_credit_amount",
    "_debit_abs",
    "_credit_abs",
    "_pnl_effect",
    "_account_name",
    "_pnl_category",
    "_header_text",
    "_line_text",
    "_combined_text",
    "_customer_display",
    "_vendor_display",
    "_material_display",
    "_material_group_display",
    "_cost_center_display",
    "_cost_account_display",
    "_reversal_text",
}


def ensure_analysis_columns(work: pd.DataFrame) -> pd.DataFrame:
    """旧版 Streamlit 缓存可能缺少新增派生列；这里自动补齐。"""
    if REQUIRED_ANALYSIS_COLUMNS.issubset(set(work.columns)):
        return work
    return add_analysis_columns(work)
