"""
数据摄入模块：加载单/多个 Excel 文件，自动识别年份，输出统一 DataFrame。

支持：
- 单文件单年
- 单文件多年（按 过账日期 拆分）
- 多文件（每文件任意年份，自动合并去重）
- SAP Period 13 归入当年，标记 _is_period13
"""

from __future__ import annotations

from pathlib import Path
from typing import IO

import pandas as pd

REQUIRED_COLUMNS = [
    "凭证编号",
    "过账日期",
    "凭证类型",
    "文本",
    "总账科目",
    "凭证货币价值",
]

# 借贷方向推断：如果缺少 借/贷标识 列，可以靠这两列来识别方向
DC_AMOUNT_COLUMNS = ["借方金额", "贷方金额"]

COLUMN_ALIASES: dict[str, str] = {
    "过帐日期": "过账日期",
    "摘要": "文本",
    "总账科目：短文本": "总账科目：长文本",
    "供应商": "供应商编号",
}
DATE_COLUMNS = ["过账日期", "凭证日期", "输入日期"]
NUMERIC_COLUMNS = ["凭证货币价值", "公司代码货币价值", "集团货币价值"]


def load_files(sources: list[str | Path | IO]) -> tuple[pd.DataFrame, dict[int, pd.DataFrame]]:
    """
    加载一个或多个 Excel 文件，返回：
    - df_unified: 合并后的全部数据（含 _year, _is_period13 列）
    - year_map: {year: df_for_that_year}
    """
    frames: list[pd.DataFrame] = []
    for src in sources:
        df = _read_single_file(src)
        frames.append(df)

    df_all = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0].copy()
    df_all = _deduplicate(df_all)
    df_all = _tag_years(df_all)

    year_map = {
        year: df_all[df_all["_year"] == year].copy()
        for year in sorted(df_all["_year"].dropna().unique())
    }
    return df_all, year_map


def _read_single_file(src: str | Path | IO) -> pd.DataFrame:
    df = pd.read_excel(src, engine="openpyxl", dtype={"总账科目": str, "凭证编号": str})
    df = df.dropna(how="all")

    # 列名标准化：SAP 导出列名可能与内部规范不一致
    df = df.rename(columns={k: v for k, v in COLUMN_ALIASES.items() if k in df.columns})

    for col in DATE_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # 凭证编号统一为字符串，去掉小数点（SAP 导出有时带 .0）
    if "凭证编号" in df.columns:
        df["凭证编号"] = df["凭证编号"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()

    # 总账科目：去掉小数点
    if "总账科目" in df.columns:
        df["总账科目"] = df["总账科目"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()

    # ── 借/贷标识列处理 ──
    # 三级降级：借方/贷方金额列 → 凭证货币价值正负号 → 报错
    if "借/贷标识" not in df.columns:
        df = _synthesize_dc_from_amounts(df)
    if "借/贷标识" not in df.columns:
        df = _synthesize_dc_from_sign(df)
    if "借/贷标识" not in df.columns:
        missing = ["借/贷标识（也尝试了'借方金额'+'贷方金额'列，以及凭证货币价值正负号）"]
        raise ValueError(f"文件缺少必要列：{missing}")

    # 若缺少 凭证货币价值 列，尝试从借方/贷方金额列合成
    if "凭证货币价值" not in df.columns:
        df = _synthesize_amount_from_dc(df)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"文件缺少必要列：{missing}")

    return df


def _synthesize_dc_from_amounts(df: pd.DataFrame) -> pd.DataFrame:
    """从 借方金额 / 贷方金额 列推断 借/贷标识（优先级 1）。

    规则：
    - 借方金额有值（非空、非零），贷方金额为空/零 → S（借方）
    - 贷方金额有值（非空、非零），借方金额为空/零 → H（贷方）
    - 两者都有值 → 取金额较大的方向
    - 两列都不存在 → 返回原 DataFrame，交给下一级（正负号推断）
    """
    # 列名标准化：部分 ERP 导出用「借方」「贷方」或「Debit」「Credit」
    debit_col = _find_column(df, ["借方金额", "借方", "Debit", "借方发生额"])
    credit_col = _find_column(df, ["贷方金额", "贷方", "Credit", "贷方发生额"])

    if debit_col is None and credit_col is None:
        return df

    debit_vals = pd.to_numeric(df[debit_col], errors="coerce").fillna(0) if debit_col else pd.Series(0, index=df.index)
    credit_vals = pd.to_numeric(df[credit_col], errors="coerce").fillna(0) if credit_col else pd.Series(0, index=df.index)

    # 向量化推断借贷方向
    dc = pd.Series("", index=df.index, dtype=str)

    mask_debit_only = (debit_vals > 0) & (credit_vals == 0)
    mask_credit_only = (credit_vals > 0) & (debit_vals == 0)
    mask_both = (debit_vals > 0) & (credit_vals > 0)

    dc[mask_debit_only] = "S"
    dc[mask_credit_only] = "H"
    dc[mask_both] = pd.Series(
        ["S" if d >= c else "H" for d, c in zip(debit_vals[mask_both], credit_vals[mask_both])],
        index=dc[mask_both].index,
    )

    df["借/贷标识"] = dc
    return df


def _synthesize_dc_from_sign(df: pd.DataFrame) -> pd.DataFrame:
    """从 凭证货币价值 的正负号推断 借/贷标识。

    部分 ERP 导出的序时账用正负号表示借贷方向：
    - 正数 → S（借方）
    - 负数 → H（贷方）
    - 零 → 空字符串（无法判断）
    """
    if "凭证货币价值" not in df.columns:
        return df

    amount = pd.to_numeric(df["凭证货币价值"], errors="coerce").fillna(0)
    dc = pd.Series("", index=df.index, dtype=str)
    dc[amount > 0] = "S"
    dc[amount < 0] = "H"
    df["借/贷标识"] = dc
    return df


def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """在 DataFrame 中查找第一个匹配的列名。"""
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _synthesize_amount_from_dc(df: pd.DataFrame) -> pd.DataFrame:
    """从 借方金额 / 贷方金额 列合成 凭证货币价值。

    如果有 借/贷标识 列且为 S，取借方金额；否则取贷方金额。
    金额统一取正值（与 SAP 导出一致），方向由 借/贷标识 控制。
    """
    debit_col = _find_column(df, ["借方金额", "借方", "Debit", "借方发生额"])
    credit_col = _find_column(df, ["贷方金额", "贷方", "Credit", "贷方发生额"])

    if debit_col is None and credit_col is None:
        return df

    debit_vals = pd.to_numeric(df[debit_col], errors="coerce").fillna(0) if debit_col else pd.Series(0, index=df.index)
    credit_vals = pd.to_numeric(df[credit_col], errors="coerce").fillna(0) if credit_col else pd.Series(0, index=df.index)

    dc = df["借/贷标识"].astype(str).str.strip()
    df["凭证货币价值"] = 0.0
    df.loc[dc == "S", "凭证货币价值"] = debit_vals[dc == "S"]
    df.loc[dc == "H", "凭证货币价值"] = credit_vals[dc == "H"]
    # 两者都有值的方向，取较大者
    mask_both = (dc != "S") & (dc != "H")
    df.loc[mask_both, "凭证货币价值"] = debit_vals[mask_both].combine(credit_vals[mask_both], max)

    return df


def _deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    key_cols = [c for c in ["凭证编号", "行项目", "过账日期"] if c in df.columns]
    if key_cols:
        before = len(df)
        df = df.drop_duplicates(subset=key_cols)
        removed = before - len(df)
        if removed > 0:
            import warnings
            warnings.warn(f"去重移除 {removed} 行重复记录")
    return df


def _tag_years(df: pd.DataFrame) -> pd.DataFrame:
    """
    根据 过账日期 打 _year 和 _is_period13 标签。
    SAP Period 13（过账期间=13 或 文本含 'period 13'/'期间13'）归入当年。
    """
    df = df.copy()

    # 尝试从过账期间列识别 period 13
    period13_mask = pd.Series(False, index=df.index)
    if "过账期间" in df.columns:
        period_vals = pd.to_numeric(df["过账期间"], errors="coerce")
        period13_mask = period_vals == 13

    df["_is_period13"] = period13_mask
    df["_year"] = df["过账日期"].dt.year

    # period 13 的年份直接用 过账日期 的年份（SAP 会给正确的日历年）
    return df


def summarize_years(df_unified: pd.DataFrame) -> list[dict]:
    """返回各年份摘要，供 UI 确认展示。"""
    rows = []
    for year, grp in df_unified.groupby("_year"):
        rows.append({
            "年份": int(year),
            "行数": len(grp),
            "凭证数": grp["凭证编号"].nunique(),
            "Period13行数": int(grp["_is_period13"].sum()),
            "金额合计": grp["凭证货币价值"].abs().sum(),
            "日期范围": f"{grp['过账日期'].min().date()} ~ {grp['过账日期'].max().date()}",
        })
    return rows
