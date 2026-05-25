# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas", "openpyxl", "openai", "httpx[socks]", "chinese_calendar", "rich"]
# ///
"""
序时账审计抽样工具 — 主入口
三阶段管道：规则引擎 → LLM 批量核实 → 输出 Excel

用法:
  uv run audit_sampler.py                     # 完整运行
  uv run audit_sampler.py --rules-only        # 仅运行规则引擎（不调 LLM）
  uv run audit_sampler.py --rule financing_trade  # 仅运行指定规则
  uv run audit_sampler.py --sample 5          # 每类规则取 5 条做 LLM 验证
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.table import Table

from config import LLM_BATCH_SIZE, LLM_MODEL
from rules import apply_whitelist, run_all_rules, RuleResult
from output import generate_output


console = Console()

DATA_FILE = Path(__file__).parent / "序时账-运载-2023.1-2023.13.XLSX"


def load_data(filepath: Path) -> pd.DataFrame:
    """加载序时账 Excel 文件"""
    console.print(f"[bold]加载数据:[/bold] {filepath.name}")
    df = pd.read_excel(filepath, engine="openpyxl")

    # 清理：移除全空行
    df = df.dropna(how="all")

    # 类型转换
    df["过账日期"] = pd.to_datetime(df["过账日期"], errors="coerce")
    df["凭证日期"] = pd.to_datetime(df["凭证日期"], errors="coerce")
    df["输入日期"] = pd.to_datetime(df["输入日期"], errors="coerce")
    df["凭证货币价值"] = pd.to_numeric(df["凭证货币价值"], errors="coerce")
    df["公司代码货币价值"] = pd.to_numeric(df["公司代码货币价值"], errors="coerce")

    console.print(f"  总行数: {len(df):,}")
    console.print(f"  凭证数: {df['凭证编号'].nunique():,}")
    console.print(
        f"  金额范围: {df['凭证货币价值'].min():,.0f} ~ {df['凭证货币价值'].max():,.0f}"
    )
    return df


def print_rule_summary(results: list[RuleResult]):
    """打印规则命中统计表"""
    table = Table(title="规则命中统计")
    table.add_column("规则名称", style="cyan")
    table.add_column("命中数", justify="right", style="green")
    table.add_column("凭证数", justify="right", style="yellow")

    total_hits = 0
    total_vouchers: set[float] = set()

    for r in results:
        voucher_count = len({h.voucher_id for h in r.hits})
        table.add_row(r.rule_name, str(r.count), str(voucher_count))
        total_hits += r.count
        total_vouchers.update(h.voucher_id for h in r.hits)

    table.add_row("合计", str(total_hits), str(len(total_vouchers)), style="bold")
    console.print(table)


def run_pipeline(
    rules_only: bool = False,
    rule_filter: str | None = None,
    sample_size: int | None = None,
):
    """执行三阶段管道"""
    start = time.time()

    # ---- 加载数据 ----
    df = load_data(DATA_FILE)

    # ---- 白名单过滤 ----
    console.print("\n[bold]Stage 1: 白名单过滤[/bold]")
    df_filtered, df_whitelisted = apply_whitelist(df)
    console.print(f"  过滤前: {len(df):,} 行")
    console.print(f"  白名单: {len(df_whitelisted):,} 行")
    console.print(f"  过滤后: {len(df_filtered):,} 行")

    # ---- 规则引擎 ----
    console.print("\n[bold]Stage 1: 规则引擎[/bold]")
    rule_results = run_all_rules(df_filtered, rule_filter=rule_filter)
    print_rule_summary(rule_results)

    if rules_only:
        console.print("\n[bold green]✓ --rules-only 模式，跳过 LLM 阶段[/bold green]")
        _print_sample_hits(df_filtered, rule_results, sample_size=20)
        return

    # ---- LLM 核实 ----
    console.print("\n[bold]Stage 2: LLM 批量核实[/bold]")

    if sample_size:
        console.print(f"  [yellow]--sample {sample_size} 模式：每类规则取 {sample_size} 条验证[/yellow]")
        trimmed_results = []
        for r in rule_results:
            trimmed = RuleResult(
                rule_name=r.rule_name,
                hits=r.hits[:sample_size],
            )
            trimmed_results.append(trimmed)
        rule_results = trimmed_results

    from llm_analyzer import verify_with_llm

    llm_judgments = verify_with_llm(
        df=df_filtered,
        rule_results=rule_results,
        batch_size=LLM_BATCH_SIZE,
        model=LLM_MODEL,
    )

    # ---- 输出 ----
    console.print("\n[bold]Stage 3: 生成报告[/bold]")
    timestamp = time.strftime("%Y%m%d_%H%M")
    output_path = Path(__file__).parent / f"审计抽样_运载_2023_{timestamp}.xlsx"
    generate_output(df_filtered, rule_results, llm_judgments, str(output_path))

    elapsed = time.time() - start
    console.print(f"\n[bold green]✓ 完成[/bold green] 耗时 {elapsed:.1f} 秒")


def _print_sample_hits(df: pd.DataFrame, results: list[RuleResult], sample_size: int = 20):
    """rules-only 模式下，打印每个规则的样例命中"""
    for r in results:
        if not r.hits:
            continue

        console.print(f"\n[bold cyan]{r.rule_name}[/bold cyan]（{r.count} 条，显示前 {sample_size} 条）")
        table = Table(show_header=True)
        table.add_column("凭证编号", justify="right")
        table.add_column("规则类型", style="yellow")
        table.add_column("证据", style="dim")
        table.add_column("金额", justify="right")
        table.add_column("文本", max_width=30)

        for hit in r.hits[:sample_size]:
            # 找第一条命中的行
            first_idx = hit.line_indices[0] if hit.line_indices else None
            row = df.loc[first_idx] if first_idx is not None else None

            amt = f"{row['凭证货币价值']:,.0f}" if row is not None else ""
            text = str(row.get("文本", ""))[:40] if row is not None else ""

            table.add_row(
                str(int(hit.voucher_id)),
                hit.rule_type,
                hit.evidence[:50],
                amt,
                text,
            )

        console.print(table)


def main():
    parser = argparse.ArgumentParser(description="序时账审计抽样工具")
    parser.add_argument(
        "--rules-only",
        action="store_true",
        help="仅运行规则引擎，不调用 LLM",
    )
    parser.add_argument(
        "--rule",
        type=str,
        default=None,
        help="仅运行指定规则（如 financing_trade, accrual_anomaly 等）",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="每类规则取 N 条做 LLM 验证（配合调试用）",
    )
    args = parser.parse_args()

    console.print("[bold]═══ 序时账审计抽样工具 ═══[/bold]\n")

    try:
        run_pipeline(
            rules_only=args.rules_only,
            rule_filter=args.rule,
            sample_size=args.sample,
        )
    except FileNotFoundError:
        console.print(f"[bold red]错误:[/bold red] 找不到数据文件 {DATA_FILE}")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]用户中断[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    main()
