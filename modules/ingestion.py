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
    "借/贷标识",
    "凭证货币价值",
]

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

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"文件缺少必要列：{missing}")

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
