"""Tab 3: 样本抽取 — 规则筛选 + 多种抽样方式 + Excel 报告下载。

从 app.py 内联抽离。依赖的 app.py 私有 helper 通过 **helpers 注入，保持与
upload/rules 页签一致的调用约定。
"""

from __future__ import annotations

import copy
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from components.charts import risk_level_pie, rule_hit_bar
from modules import candidate_pool as cp
from modules.llm_verifier import verify_with_llm
from modules.reporter import generate_report
from modules.rule_engine import RuleHit, RuleResult, hits_summary, run_all_rules
from modules.rule_generator import default_rules_config

# 报告输出目录固定为仓库根目录（与原 app.py 中 Path(__file__).parent 行为一致）。
# 本文件位于 <root>/components/tabs/sampling.py，parents[2] 即仓库根。
_REPORT_DIR = Path(__file__).resolve().parents[2]


def render_sampling_tab(main_tab=None, **helpers):
    """Render the 样本抽取 (Sampling) tab."""
    _has_project_payload = helpers["_has_project_payload"]
    _has_loaded_years = helpers["_has_loaded_years"]
    _candidate_pool_voucher_ids = helpers["_candidate_pool_voucher_ids"]
    _rule_counts = helpers["_rule_counts"]
    _format_money = helpers["_format_money"]
    _can_use_llm = helpers["_can_use_llm"]
    _llm_model = helpers["_llm_model"]
    _llm_base_url = helpers["_llm_base_url"]
    _autosave_current_project_state = helpers["_autosave_current_project_state"]
    _reset_current_project = helpers["_reset_current_project"]

    if main_tab is not None:
        main_tab.__enter__()

    if not (_has_project_payload() and _has_loaded_years()):
        st.info("请先在「上传数据」页签中上传序时账文件。")
        return

    st.title("🎯 样本抽取")
    st.caption("从可疑样本库中选择规则和抽样方式，一键生成最终审计样本。")

    pool = st.session_state.get("candidate_pool", [])
    df = st.session_state.df_unified
    candidate_voucher_ids = _candidate_pool_voucher_ids()
    pool_stat = cp.get_pool_statistics(pool)

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        rule_source = st.selectbox(
            "规则来源",
            options=["default_rules", "calibrated_rules", "no_rule"],
            format_func=lambda x: {
                "default_rules": "🏛 系统默认规则",
                "calibrated_rules": "🤖 LLM 校准后规则",
                "no_rule": "❌ 不使用规则（仅随机/全量）",
            }.get(x, x),
            help="选择用于筛选样本的规则集。",
        )
    with col_b:
        sample_method = st.selectbox(
            "抽样方式",
            options=["by_rule", "by_account_weight", "monetary_unit", "stratified", "random", "all"],
            format_func=lambda x: {
                "by_rule": "🔍 按规则筛选",
                "by_account_weight": "📊 科目权重抽样",
                "monetary_unit": "💰 货币单元抽样 (MUS)",
                "stratified": "📑 分层抽样",
                "random": "🎲 随机抽样",
                "all": "📦 全量（不抽样）",
            }.get(x, x),
            help="从候选凭证中选择最终样本的方式。",
        )
    with col_c:
        max_sample_size = st.number_input(
            "样本量上限（凭证数）",
            min_value=1,
            max_value=500,
            value=min((st.session_state.rules_config or {}).get("max_sample_size", 50), 200),
            key="sample_max_size",
            help="最终输出的最大凭证数量。",
        )
        max_sample_size = int(max_sample_size)

    if rule_source == "calibrated_rules":
        if st.session_state.rules_config:
            enabled_count, _ = _rule_counts(st.session_state.rules_config)
            st.caption(f"已加载校准规则 {enabled_count} 条（可在「规则管理」页签中调整）。")
        else:
            st.warning("尚未生成校准规则，将回退到系统默认规则。")
    elif rule_source == "default_rules":
        st.caption("使用系统内置默认规则集。")

    if sample_method == "random":
        st.info("随机抽样：对候选池中所有凭证按指定样本量随机抽取，不依赖规则引擎。")
    elif sample_method == "by_rule":
        st.info("按规则筛选：使用选定规则集对候选池（或全量数据）执行规则引擎，命中凭证作为样本。")
    elif sample_method == "all":
        st.info("全量抽取：将候选池中所有凭证直接作为最终样本，不做筛选。")
    elif sample_method == "by_account_weight":
        st.info("科目权重抽样：按科目大类分配样本名额，每类内取金额最大的凭证。可调整下方权重。")
        # 权重滑块
        weights = st.session_state.get("_sample_weights", dict(cp.DEFAULT_ACCOUNT_WEIGHTS))
        st.caption("调整各科目大类的抽样权重（将自动归一化）：")
        weight_cols = st.columns(len(weights))
        new_weights = {}
        for (cat, default_w), col in zip(weights.items(), weight_cols, strict=True):
            with col:
                new_weights[cat] = st.slider(
                    cat, 0.0, 1.0, default_w, 0.05,
                    key=f"weight_{cat}",
                )
        st.session_state["_sample_weights"] = new_weights
    elif sample_method == "monetary_unit":
        st.info("货币单元抽样 (MUS)：以金额为抽样单元，金额越大的凭证被抽中概率越高。经典审计抽样方法。")
    elif sample_method == "stratified":
        st.info("分层抽样：按指定属性将候选凭证分层，每层按比例或等量抽取。")
        strat_col1, strat_col2 = st.columns(2)
        with strat_col1:
            stratify_by = st.selectbox(
                "分层属性",
                options=["凭证类型", "科目大类", "月份", "用户名"],
                key="stratify_by",
            )
        with strat_col2:
            stratify_mode = st.selectbox(
                "分配方式",
                options=["proportional", "equal"],
                format_func=lambda x: "按层规模比例" if x == "proportional" else "每层等量",
                key="stratify_mode",
            )
        st.session_state["_stratify_by"] = stratify_by
        st.session_state["_stratify_mode"] = stratify_mode

    scope_desc = f"当前候选池有效凭证：{len(candidate_voucher_ids):,} 个" if candidate_voucher_ids else "候选池为空，将对全量数据执行规则引擎。"
    st.caption(f"📊 {scope_desc} | 候选群体：{pool_stat['total_groups']} 个 | 总金额：{_format_money(pool_stat['total_amount'])}")

    use_candidate_scope = False
    if sample_method == "by_rule":
        use_candidate_scope = st.checkbox(
            "仅在疑点库范围内执行规则",
            value=bool(candidate_voucher_ids),
            disabled=not bool(candidate_voucher_ids),
            key="sample_use_scope",
        )
        if candidate_voucher_ids:
            st.caption(f"启用后仅在 {len(candidate_voucher_ids):,} 个候选凭证上运行规则，否则回退全量。")

    run_llm = st.checkbox(
        "启用智能辅助核实 (LLM Verification)",
        value=_can_use_llm(),
        disabled=not _can_use_llm(),
        key="sample_run_llm",
    )

    st.divider()

    if st.button("🚀 执行样本抽取", type="primary", width="stretch"):
        if rule_source == "calibrated_rules" and st.session_state.rules_config:
            cfg = copy.deepcopy(st.session_state.rules_config)
        else:
            cfg = default_rules_config()
        cfg["max_sample_size"] = max_sample_size

        with st.spinner("正在执行样本抽取..."):
            st.session_state.sample_max_size_effective = max_sample_size
            if sample_method == "by_rule":
                scope_ids = candidate_voucher_ids if use_candidate_scope else None
                rule_results = run_all_rules(
                    df, cfg,
                    cross_year_findings=st.session_state.cross_year_findings,
                    candidate_voucher_ids=scope_ids,
                )
                st.session_state.rule_results = rule_results

                if run_llm:
                    progress_bar = st.progress(0)
                    progress_text = st.empty()

                    def on_progress(batch_num, total_batches):
                        pct = int(batch_num / total_batches * 100)
                        progress_bar.progress(pct)
                        progress_text.text(f"智能核实进度：{batch_num}/{total_batches} 批次 ({pct}%)")

                    judgments = verify_with_llm(
                        df=df,
                        rule_results=rule_results,
                        api_key=st.session_state["_api_key"],
                        model=_llm_model(),
                        base_url=_llm_base_url(),
                        batch_size=10,
                        max_verify=50,
                        progress_callback=on_progress,
                    )
                    progress_bar.progress(100)
                    progress_text.text("✅ 智能核实已完成")
                    st.session_state.llm_judgments = judgments
                else:
                    st.session_state.llm_judgments = {}

                samples = cp.sample_from_rule_results(
                    rule_results,
                    df,
                    size=max_sample_size,
                    pool=pool,
                )
                st.session_state.final_samples = samples
            elif sample_method == "by_account_weight":
                samples = cp.sample_from_pool(
                    pool, df,
                    method="by_account_weight",
                    size=max_sample_size,
                    account_weights=st.session_state.get("_sample_weights"),
                )
                st.session_state.final_samples = samples
            elif sample_method == "monetary_unit":
                samples = cp.sample_from_pool(
                    pool, df,
                    method="monetary_unit",
                    size=max_sample_size,
                )
                st.session_state.final_samples = samples
            elif sample_method == "stratified":
                samples = cp.sample_from_pool(
                    pool, df,
                    method="stratified",
                    size=max_sample_size,
                    stratify_by=st.session_state.get("_stratify_by"),
                    stratify_mode=st.session_state.get("_stratify_mode", "proportional"),
                )
                st.session_state.final_samples = samples
            elif sample_method == "random":
                samples = cp.sample_from_pool(
                    pool, df,
                    method="random",
                    size=max_sample_size,
                )
                st.session_state.final_samples = samples
            elif sample_method == "all":
                samples = cp.sample_from_pool(
                    pool, df,
                    method="all",
                )
                st.session_state.final_samples = samples

            st.session_state.report_stats = {}
            st.session_state.report_path = None
            _autosave_current_project_state()
            st.rerun()

    # 展示抽样结果
    if st.session_state.get("final_samples"):
        samples = st.session_state.final_samples
        st.divider()
        st.subheader(f"📊 抽样结果（{len(samples)} 条凭证）")

        source_counts = {}
        for s in samples:
            src = s.get("来源模块", "未知")
            source_counts[src] = source_counts.get(src, 0) + 1

        stats_cols = st.columns(3)
        stats_cols[0].metric("样本凭证总数", len(samples))
        stats_cols[1].metric("人工直入数量", sum(1 for s in samples if s.get("是否为人工直入")))
        if source_counts:
            stats_cols[2].metric("来源模块数", len(source_counts))

        result_df = cp.sample_to_table(samples)
        if not result_df.empty:
            display_df = result_df.copy()
            display_df["借方金额"] = display_df["借方金额"] / 1e4
            display_df["贷方金额"] = display_df["贷方金额"] / 1e4
            st.dataframe(
                display_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "凭证编号": st.column_config.TextColumn("凭证编号"),
                    "过账日期": st.column_config.TextColumn("过账日期"),
                    "总账科目": st.column_config.TextColumn("总账科目"),
                    "科目名称": st.column_config.TextColumn("科目名称"),
                    "借方金额(万)": st.column_config.NumberColumn("借方金额(万)", format="%,.1f"),
                    "贷方金额(万)": st.column_config.NumberColumn("贷方金额(万)", format="%,.1f"),
                    "来源模块": st.column_config.TextColumn("来源模块"),
                    "是否为人工直入": st.column_config.CheckboxColumn("是否为人工直入"),
                },
            )

        if st.session_state.rule_results:
            results = st.session_state.rule_results
            summary_data = hits_summary(results)
            c1, c2 = st.columns([1, 1.5])
            with c1:
                st.markdown("##### 规则命中摘要")
                st.dataframe(pd.DataFrame(summary_data), width="stretch", hide_index=True)
                total_hits = sum(r.count for r in results)
                total_vouchers = len({h.voucher_id for r in results for h in r.hits})
                st.info(f"💡 规则共命中 **{total_hits}** 行分录，涉及 **{total_vouchers}** 个凭证。")
            with c2:
                st.plotly_chart(rule_hit_bar(summary_data), width="stretch")

            if st.session_state.llm_judgments:
                st.plotly_chart(risk_level_pie(st.session_state.llm_judgments), width="stretch")

    st.divider()
    st.subheader("📄 报告下载")

    cfg = st.session_state.rules_config or {}
    max_sample = int(st.session_state.get("sample_max_size_effective") or cfg.get("max_sample_size", 50))

    if not st.session_state.report_stats:
        with st.spinner("正在汇总数据并生成 Excel 报告..."):
            engagement = st.session_state.engagement_name or "unnamed"
            ts = datetime.now().strftime("%Y%m%d_%H%M")
            out_path = _REPORT_DIR / f"样本清单_{engagement}_{ts}.xlsx"

            rule_results = st.session_state.rule_results
            # 如果规则结果为空但有最终样本，用样本凭证号构建最小 RuleHit 集合
            if (not rule_results) and st.session_state.get("final_samples"):
                sample_vids = {str(s["凭证编号"]) for s in st.session_state.final_samples if s.get("凭证编号")}
                if sample_vids:
                    hits = [
                        RuleHit(voucher_id=vid, rule_type="人工/随机抽样", evidence="来自最终样本",
                                line_indices=(), priority=1)
                        for vid in sorted(sample_vids)
                    ]
                    rule_results = [RuleResult(rule_name="抽样结果", hits=hits)]

            stats = generate_report(
                df=st.session_state.df_unified,
                rule_results=rule_results,
                llm_judgments=st.session_state.llm_judgments,
                output_path=str(out_path),
                max_sample_size=max_sample,
                manual_final_samples=cp.manual_final_groups(st.session_state.get("candidate_pool", [])),
            )
            st.session_state.report_path = str(out_path)
            st.session_state.report_stats = stats
            _autosave_current_project_state()

    stats = st.session_state.report_stats

    with st.container(border=True):
        st.markdown("##### 报告统计摘要")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("最终样本凭证", stats.get("sample_vouchers", 0))
        col2.metric("规则命中凭证", stats.get("total_unique_vouchers", stats.get("total_rule_hits", 0)))
        col3.metric("高风险凭证", stats.get("high_risk", 0))
        col4.metric("人工直入凭证", stats.get("manual_final_vouchers", 0))

    # 下载报告
    report_path = st.session_state.report_path
    if report_path and Path(report_path).exists():
        with open(report_path, "rb") as f:
            st.download_button(
                "📥 下载样本清单 (Excel)",
                data=f.read(),
                file_name=Path(report_path).name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                width="stretch"
            )

    st.divider()

    # 重置，开始新项目
    if st.button("🔄 开始新审计项目", width="stretch"):
        _reset_current_project()
        st.rerun()
