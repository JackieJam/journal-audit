"""Tab 3: 规则管理 — 交互式增删改查"""

from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
import streamlit as st

from modules.rule_generator import generate_rules_config, default_rules_config
from modules.rule_engine import run_all_rules, hits_summary
from modules.llm_verifier import verify_with_llm
from modules.profiler import profiles_to_summary_text, financials_to_summary_text
from modules.cross_year import findings_to_summary_text
from modules import knowledge_base as kb
from modules import candidate_pool as cp
from config.constants import RULE_ORDER, RULE_META, PARAM_LABELS, PARAM_HELP


def render_rules_tab(main_tab, **helpers):
    """Render the 规则管理 (Rule Management) tab."""
    _require_loaded_data = helpers["_require_loaded_data"]
    _can_use_llm = helpers["_can_use_llm"]
    _resolve_api_key = helpers["_resolve_api_key"]
    _llm_model = helpers["_llm_model"]
    _llm_base_url = helpers["_llm_base_url"]
    _autosave_current_project_state = helpers["_autosave_current_project_state"]
    _rule_counts = helpers["_rule_counts"]
    _collect_rule_changes = helpers["_collect_rule_changes"]
    _render_library_rules = helpers["_render_library_rules"]

    if main_tab is not None:
        main_tab.__enter__()

    if not _require_loaded_data():
        return

    st.title("⚙️ 规则管理")
    st.caption("启用/关闭、调整参数、克隆规则、删除规则。修改自动保存到当前项目。")

    # ── 确保规则已初始化 ──
    base_cfg = default_rules_config()
    if not st.session_state.rules_config:
        st.session_state.rules_config = base_cfg.copy()

    # ── 自定义规则索引 ──
    if "custom_rule_keys" not in st.session_state:
        st.session_state.custom_rule_keys = []
    if "custom_rule_counter" not in st.session_state:
        st.session_state.custom_rule_counter = 0

    cfg = st.session_state.rules_config
    custom_keys = st.session_state.custom_rule_keys

    # ── 顶部操作栏 ──
    col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 0.6, 0.4])
    with col1:
        if st.button("🚀 智能校准（LLM 分析画像后自动设参）", disabled=not _can_use_llm(), use_container_width=True):
            with st.spinner("LLM 正在分析画像特征并校准阈值..."):
                try:
                    lib_rules = kb.get_recommendations("", top_n=8)
                    profiles_text = profiles_to_summary_text(st.session_state.profiles)
                    fin_text = financials_to_summary_text(st.session_state.financials)
                    cross_text = findings_to_summary_text(st.session_state.cross_year_findings)
                    candidate_text = cp.candidate_pool_summary_text(st.session_state.get("candidate_pool", []))
                    cfg = generate_rules_config(
                        profiles_text=fin_text + "\n\n" + profiles_text,
                        cross_year_text=cross_text,
                        library_rules=lib_rules,
                        api_key=st.session_state["_api_key"],
                        candidate_pool_text=candidate_text,
                        model=_llm_model(),
                        base_url=_llm_base_url(),
                    )
                    st.session_state.rules_config = cfg
                    _autosave_current_project_state()
                    st.success("校准完成！参数已更新到下方各规则卡片中。")
                    st.rerun()
                except Exception as e:
                    st.error(f"校准失败：{e}")
    with col2:
        if st.button("🔄 恢复全部默认", use_container_width=True):
            st.session_state.rules_config = base_cfg.copy()
            st.session_state.custom_rule_keys = []
            st.session_state.custom_rule_counter = 0
            _autosave_current_project_state()
            st.success("已恢复默认参数（自定义规则已清除）。")
            st.rerun()
    with col3:
        total_rules = len(RULE_ORDER) + len(custom_keys)
        enabled_count = sum(
            1 for k in list(RULE_ORDER) + custom_keys
            if cfg.get(k, {}).get("enabled", False)
        )
        st.metric("已启用", f"{enabled_count}/{total_rules}")
    with col4:
        st.metric("样本上限", cfg.get("max_sample_size", 50))
    with col5:
        with st.popover("＋", use_container_width=True):
            _render_create_rule_form(base_cfg)

    # ── 白名单 & 全局设置 ──
    with st.expander("🔧 全局白名单 & 样本量", expanded=False):
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            whitelist_kw = st.text_area(
                "关键词白名单（每行一个）",
                value="\n".join(cfg.get("whitelist_keywords", [])),
                height=120,
                key="cfg_whitelist_kw",
            )
            cfg["whitelist_keywords"] = [k.strip() for k in whitelist_kw.split("\n") if k.strip()]
        with c2:
            whitelist_types = st.text_area(
                "凭证类型白名单（每行一个）",
                value="\n".join(cfg.get("whitelist_voucher_types", [])),
                height=120,
                key="cfg_whitelist_types",
            )
            cfg["whitelist_voucher_types"] = [t.strip() for t in whitelist_types.split("\n") if t.strip()]
        with c3:
            new_max = st.number_input("样本量上限", min_value=10, max_value=500, step=10,
                                       value=cfg.get("max_sample_size", 50), key="cfg_max_sample")
            cfg["max_sample_size"] = int(new_max)

    st.divider()

    # ── 规则列表（3列网格 + popover 弹窗编辑）──
    all_rule_keys = list(RULE_ORDER) + [k for k in custom_keys if k in cfg]
    if all_rule_keys:
        chunks = [all_rule_keys[i:i+3] for i in range(0, len(all_rule_keys), 3)]
        for chunk in chunks:
            cols = st.columns(3)
            for rule_key, col in zip(chunk, cols):
                with col:
                    is_builtin = rule_key in RULE_ORDER
                    _render_rule_popover(rule_key, base_cfg, is_builtin)

    # ── 规则沉淀与经验库 ──
    st.divider()
    st.subheader("📊 规则沉淀与经验库")

    # 经验库累计统计
    all_lib_rules = kb.list_rules()
    if all_lib_rules:
        st.markdown("##### 经验库规则累计命中率")
        lib_rows = []
        for r in all_lib_rules:
            perf = r.get("performance", {})
            lib_rows.append({
                "规则名称": r.get("name", ""),
                "类别": r.get("category", ""),
                "累计命中": perf.get("total_hits", 0),
                "累计确认": perf.get("total_confirmed", 0),
                "累计确认率": f"{perf.get('confirmation_rate', 0):.1%}",
                "使用项目数": perf.get("engagements_used", 0),
                "最近项目": r.get("last_engagement", ""),
            })
        st.dataframe(
            pd.DataFrame(lib_rows),
            use_container_width=True, hide_index=True,
            column_config={
                "规则名称": st.column_config.TextColumn("规则名称", width="medium"),
                "类别": st.column_config.TextColumn("类别", width="small"),
                "累计命中": st.column_config.NumberColumn("累计命中", format="%,d"),
                "累计确认": st.column_config.NumberColumn("累计确认", format="%,d"),
                "累计确认率": st.column_config.TextColumn("累计确认率", width="small"),
                "使用项目数": st.column_config.NumberColumn("项目数", format="%d"),
                "最近项目": st.column_config.TextColumn("最近项目", width="small"),
            },
        )
    else:
        st.info("经验库暂无沉淀规则。执行抽样后可在下方将有效规则保存至经验库。")

    # 高确认率推荐
    lib_rules = kb.get_recommendations("", top_n=5)
    if lib_rules:
        st.markdown("##### 高确认率推荐")
        _render_library_rules(lib_rules)

    # ── 保存当前项目规则到经验库 ──
    with st.expander("💾 将当前项目规则沉淀至经验库", expanded=False):
        rule_results = st.session_state.get("rule_results", [])
        judgments = st.session_state.get("llm_judgments", {})
        if not rule_results:
            st.info("尚未执行规则抽样。请先在「样本抽取」页签执行抽样，再回到此处沉淀规则。")
        else:
            st.caption("勾选确认率较高的规则保存到全局经验库，供后续项目参考。")
            rules_to_save = []
            for rr in rule_results:
                if rr.count == 0:
                    continue
                voucher_count = len({h.voucher_id for h in rr.hits})
                confirmed_count = len(judgments.get(rr.rule_name, []))
                rate = confirmed_count / voucher_count if voucher_count > 0 else 0

                col_chk, col_name, col_hit, col_rate = st.columns([0.5, 3, 1, 1])
                selected = col_chk.checkbox(
                    "", value=rate >= 0.5, key=f"save_lib_{rr.rule_name}"
                )
                col_name.markdown(f"**{rr.rule_name}**")
                col_hit.caption(f"命中 {voucher_count}")
                col_rate.caption(f"确认率 {rate:.0%}")

                if selected:
                    rules_to_save.append((rr.rule_name, voucher_count, confirmed_count))

            if rules_to_save:
                engagement = st.session_state.get("engagement_name", "unnamed")
                notes = st.text_input("项目备注", placeholder="如：SAP系统，制造业，存在大量暂估入账",
                                      key="lib_notes")
                if st.button("💾 保存选中规则到经验库", use_container_width=True, key="btn_save_lib"):
                    saved_count = 0
                    cfg = st.session_state.rules_config or {}
                    for rule_name, hits_n, confirmed_n in rules_to_save:
                        cat = rule_name.split("(")[0].strip()
                        cat_key = cat.replace("大额异常", "large_amount") \
                                     .replace("化整为零", "splitting") \
                                     .replace("手工凭证", "manual_entry") \
                                     .replace("计提异常", "accrual_anomaly") \
                                     .replace("收入突增", "yearend_surge") \
                                     .replace("融资性贸易", "financing_trade") \
                                     .replace("资金池划转", "cash_pool") \
                                     .replace("用户集中度异常", "user_concentration") \
                                     .replace("冲销反记账异常", "reversal_pattern") \
                                     .replace("敏感费用筛查", "sensitive_fees") \
                                     .replace("跨年异常", "cross_year_accrual")
                        rule_cfg = cfg.get(cat_key, {})
                        kb.save_rule(
                            name=rule_name,
                            category=cat,
                            parameters={k: v for k, v in rule_cfg.items()
                                        if k not in ("enabled", "rationale")},
                            rationale=rule_cfg.get("rationale", ""),
                            engagement=engagement,
                            hits=hits_n,
                            confirmed=confirmed_n,
                            company_notes=notes,
                        )
                        saved_count += 1
                    st.success(f"已保存 {saved_count} 条规则到经验库。刷新后可查看累计命中率。")
                    st.rerun()

    _autosave_current_project_state()


def _render_rule_popover(rule_key: str, base_cfg: dict, is_builtin: bool = True):
    """规则卡片 v3：按钮触发 popover 弹窗编辑，3 列网格布局。"""
    cfg = st.session_state.rules_config
    rule = cfg.get(rule_key, {})
    meta = RULE_META.get(rule_key, {})
    title = meta.get("title", rule_key)
    enabled = rule.get("enabled", False)
    suffix = " · 自定义" if not is_builtin else ""

    icon = "✅" if enabled else "⬜"
    label = f"{icon} {title}{suffix}"

    with st.popover(label, use_container_width=True):
        # 头部：启用 + 删除
        c_en, c_del = st.columns([3, 1])
        with c_en:
            new_enabled = st.checkbox("启用此规则", value=enabled, key=f"rule3_en_{rule_key}")
            if new_enabled != enabled:
                cfg[rule_key] = {**rule, "enabled": new_enabled}
                st.rerun()
        with c_del:
            if not is_builtin:
                if st.button("🗑️", key=f"rule3_del_{rule_key}", help=f"删除 {title}"):
                    _delete_rule(rule_key, title)
                    st.rerun()

        purpose = meta.get("purpose", "")
        if purpose:
            st.caption(f"📌 {purpose}")

        if not cfg[rule_key].get("enabled", False):
            st.info("规则已关闭，启用后可编辑参数。")
            return

        rationale = st.text_area(
            "审计理由", value=rule.get("rationale", ""),
            key=f"rule3_rationale_{rule_key}", height=55,
        )
        cfg[rule_key]["rationale"] = rationale

        params = {k: v for k, v in rule.items() if k not in ("enabled", "rationale")}
        base_params = {k: v for k, v in base_cfg.get(rule_key, {}).items()
                       if k not in ("enabled", "rationale")}

        if params:
            _render_params_grid(cfg[rule_key], params, base_params, rule_key)
        else:
            st.caption("无额外参数。")

        b1, b2 = st.columns(2)
        with b1:
            if is_builtin and base_cfg.get(rule_key):
                if st.button("↩ 恢复默认", key=f"rule3_reset_{rule_key}", use_container_width=True):
                    cfg[rule_key] = base_cfg[rule_key].copy()
                    st.success(f"「{title}」已恢复默认。")
                    st.rerun()
            else:
                if st.button("📋 克隆", key=f"rule3_clone_{rule_key}", use_container_width=True):
                    _clone_rule(rule_key)
                    st.rerun()
        with b2:
            if not is_builtin:
                if st.button("🗑️ 删除", key=f"rule3_del2_{rule_key}", use_container_width=True):
                    _delete_rule(rule_key, title)
                    st.rerun()


def _render_rule_card_v2(rule_key: str, base_cfg: dict, is_builtin: bool = True):
    """新规则卡片：expander 标题即规则名，点击展开查看/编辑参数。"""
    cfg = st.session_state.rules_config
    rule = cfg.get(rule_key, {})
    base_rule = base_cfg.get(rule_key, {})
    meta = RULE_META.get(rule_key, {})
    title = meta.get("title", rule_key)
    enabled = rule.get("enabled", False)
    suffix = " ⋅ 自定义" if not is_builtin else ""

    # ── Expander 作为规则标题 ──
    icon = "✅" if enabled else "⬜"
    expander_label = f"{icon} {title}{suffix}"

    with st.expander(expander_label, expanded=False):
        # 第一行：启用开关 + 操作按钮
        c_enable, c_actions = st.columns([3, 1])
        with c_enable:
            new_enabled = st.checkbox(
                "启用此规则", value=enabled, key=f"rule2_en_{rule_key}",
                help=meta.get("purpose", "")
            )
            if new_enabled != enabled:
                cfg[rule_key] = {**rule, "enabled": new_enabled}
                st.rerun()
        with c_actions:
            if not is_builtin:
                if st.button("🗑️ 删除", key=f"rule2_del_{rule_key}", use_container_width=True):
                    _delete_rule(rule_key, title)
                    st.rerun()

        # 规则目的说明
        purpose = meta.get("purpose", "")
        if purpose:
            st.caption(f"📌 {purpose}")

        # ── 参数编辑区 ──
        if not cfg[rule_key].get("enabled", False):
            st.info("规则已关闭。启用后可编辑参数。")
            return

        # rationale
        rationale = st.text_area(
            "审计理由（为什么设这个阈值？）",
            value=rule.get("rationale", ""),
            key=f"rule2_rationale_{rule_key}", height=60,
        )
        cfg[rule_key]["rationale"] = rationale

        params = {k: v for k, v in rule.items() if k not in ("enabled", "rationale")}
        base_params = {k: v for k, v in base_rule.items() if k not in ("enabled", "rationale")}

        if not params:
            st.caption("此规则无额外参数。")
        else:
            _render_params_grid(cfg[rule_key], params, base_params, rule_key)

        # ── 底部按钮 ──
        b1, b2 = st.columns(2)
        with b1:
            if is_builtin and base_rule:
                if st.button(f"↩ 恢复默认", key=f"rule2_reset_{rule_key}", use_container_width=True):
                    cfg[rule_key] = base_rule.copy()
                    st.success(f"「{title}」已恢复默认参数。")
                    st.rerun()
            else:
                if st.button(f"📋 克隆", key=f"rule2_clone_{rule_key}", use_container_width=True):
                    _clone_rule(rule_key)
                    st.rerun()
        with b2:
            if not is_builtin:
                if st.button(f"🗑️ 删除规则", key=f"rule2_del2_{rule_key}", use_container_width=True):
                    _delete_rule(rule_key, title)
                    st.rerun()


def _render_rule_card(rule_key: str, base_cfg: dict, is_builtin: bool = True):
    """渲染单条规则的交互式编辑卡片。"""
    cfg = st.session_state.rules_config
    rule = cfg.get(rule_key, {})
    base_rule = base_cfg.get(rule_key, {})
    meta = RULE_META.get(rule_key, {})
    title = meta.get("title", rule_key)
    suffix = " (自定义)" if not is_builtin else ""

    # ── 标题栏：checkbox + 操作按钮 ──
    c_title, c_actions = st.columns([4, 1])
    with c_title:
        enabled = rule.get("enabled", False)
        new_enabled = st.checkbox(
            f"**{title}{suffix}**",
            value=enabled,
            key=f"rule_enabled_{rule_key}",
            help=meta.get("purpose", "")
        )
        if new_enabled != enabled:
            cfg[rule_key] = {**rule, "enabled": new_enabled}

    with c_actions:
        if not is_builtin:
            if st.button("🗑️", key=f"rule_del_{rule_key}", help=f"删除 {title}", use_container_width=True):
                _delete_rule(rule_key, title)
                st.rerun()

    if not cfg[rule_key].get("enabled", False):
        return

    # ── 参数编辑区 ──
    with st.expander(f"⚙️ {title}{suffix} 参数", expanded=not is_builtin):
        # rationale
        rationale = st.text_area(
            "审计理由（为什么设这个阈值？）", value=rule.get("rationale", ""),
            key=f"rule_rationale_{rule_key}", height=60,
        )
        cfg[rule_key]["rationale"] = rationale

        params = {k: v for k, v in rule.items() if k not in ("enabled", "rationale")}
        base_params = {k: v for k, v in base_rule.items() if k not in ("enabled", "rationale")}

        if not params:
            st.caption("此规则无额外参数。")
        else:
            _render_params_grid(cfg[rule_key], params, base_params, rule_key)

        # ── 底部按钮 ──
        b1, b2 = st.columns(2)
        with b1:
            if is_builtin and base_rule:
                if st.button(f"↩ 恢复 {title} 默认", key=f"rule_reset_{rule_key}", use_container_width=True):
                    cfg[rule_key] = base_rule.copy()
                    st.success(f"{title} 已恢复默认。")
                    st.rerun()
            else:
                if st.button(f"📋 克隆 {title}", key=f"rule_clone_{rule_key}", use_container_width=True):
                    _clone_rule(rule_key)
                    st.rerun()
        with b2:
            if not is_builtin:
                if st.button(f"🗑️ 删除 {title}", key=f"rule_del2_{rule_key}", use_container_width=True):
                    _delete_rule(rule_key, title)
                    st.rerun()


def _render_params_grid(cfg_section: dict, params: dict, base_params: dict, rule_key: str):
    """将规则参数分组为 2-3 列并排显示，减少空白区域。"""
    # 分开简单参数和复杂参数（dict/list）
    simple_params = []
    complex_params = []
    for pk, pv in params.items():
        if isinstance(pv, dict):
            complex_params.append((pk, pv))
        elif isinstance(pv, list) and len(pv) > 5:
            complex_params.append((pk, pv))
        else:
            simple_params.append((pk, pv))

    # 简单参数：按数量分组为 2 或 3 列
    if simple_params:
        cols_per_row = 2 if len(simple_params) <= 4 else 3
        chunks = [simple_params[i:i+cols_per_row] for i in range(0, len(simple_params), cols_per_row)]
        for chunk in chunks:
            cols = st.columns(cols_per_row)
            for (pk, pv), col in zip(chunk, cols):
                with col:
                    _render_single_param(cfg_section, pk, pv, base_params.get(pk), rule_key)

    # 复杂参数（dict / 长列表）：单行显示
    for pk, pv in complex_params:
        label = PARAM_LABELS.get(pk, pk)
        if isinstance(pv, dict):
            st.caption(f"📂 {label}")
            _render_nested_dict(cfg_section, pk, pv, rule_key, base_params.get(pk))
        elif isinstance(pv, list):
            help_text = PARAM_HELP.get(pk, "")
            text_val = st.text_area(
                f"{label}（每行一个）", value="\n".join(str(x) for x in pv),
                key=f"rule_{rule_key}_{pk}", height=80, help=help_text,
            )
            new_list = [x.strip() for x in text_val.split("\n") if x.strip()]
            if new_list != pv:
                cfg_section[pk] = new_list


def _render_single_param(cfg_section: dict, pk: str, pv, base_val, rule_key: str):
    """渲染单个参数控件（在 grid 列内调用）。"""
    label = PARAM_LABELS.get(pk, pk)
    help_text = PARAM_HELP.get(pk, "")

    if isinstance(pv, bool):
        new_val = st.checkbox(label, value=pv, key=f"rule_{rule_key}_{pk}", help=help_text)
        if new_val != pv:
            cfg_section[pk] = new_val

    elif isinstance(pv, int):
        new_val = st.number_input(label, value=pv, step=1, key=f"rule_{rule_key}_{pk}", help=help_text)
        if new_val != pv:
            cfg_section[pk] = int(new_val)

    elif isinstance(pv, float):
        new_val = st.number_input(label, value=pv, step=0.01, format="%.4f",
                                  key=f"rule_{rule_key}_{pk}", help=help_text)
        if new_val != pv:
            cfg_section[pk] = float(new_val)

    elif isinstance(pv, list):
        text_val = st.text_area(
            f"{label}（每行一个）", value="\n".join(str(x) for x in pv),
            key=f"rule_{rule_key}_{pk}", height=60, help=help_text,
        )
        new_list = [x.strip() for x in text_val.split("\n") if x.strip()]
        if new_list != pv:
            cfg_section[pk] = new_list

    else:
        st.caption(f"{label}: {pv}")


def _render_nested_dict(parent: dict, key: str, value: dict, rule_key: str, base_val=None):
    """渲染嵌套字典（如 sensitive_fees 的 categories）。"""
    if base_val is None:
        base_val = {}

    for sub_key, sub_val in value.items():
        if not isinstance(sub_val, dict):
            continue
        base_sub = base_val.get(sub_key, {})

        col_a, col_b, col_c = st.columns([3, 2, 2])
        with col_a:
            st.caption(f"**{sub_key}**")
        with col_b:
            kw_text = st.text_input(
                "关键词",
                value=", ".join(sub_val.get("keywords", [])),
                key=f"rule_{rule_key}_{key}_{sub_key}_kw",
                label_visibility="collapsed",
            )
            new_kw = [k.strip() for k in kw_text.split(",") if k.strip()]
            if new_kw != sub_val.get("keywords", []):
                parent[key][sub_key]["keywords"] = new_kw
        with col_c:
            new_th = st.number_input(
                "阈值", value=int(sub_val.get("threshold", 0)), step=1000,
                key=f"rule_{rule_key}_{key}_{sub_key}_th", label_visibility="collapsed",
            )
            if new_th != sub_val.get("threshold", 0):
                parent[key][sub_key]["threshold"] = int(new_th)

        exclude_text = st.text_input(
            f"排除词（{sub_key}）",
            value=", ".join(sub_val.get("exclude", [])),
            key=f"rule_{rule_key}_{key}_{sub_key}_ex",
        )
        new_ex = [e.strip() for e in exclude_text.split(",") if e.strip()]
        if new_ex != sub_val.get("exclude", []):
            parent[key][sub_key]["exclude"] = new_ex


def _render_create_rule_form(base_cfg: dict):
    """渲染新增自定义规则的表单。"""
    st.markdown("#### 创建新规则")
    st.caption("基于现有规则类型创建变体，使用不同的参数阈值。")

    col1, col2 = st.columns([2, 3])
    with col1:
        base_rule_type = st.selectbox(
            "规则类型（选择基础模板）",
            options=RULE_ORDER,
            format_func=lambda k: RULE_META.get(k, {}).get("title", k),
            key="new_rule_type",
        )
        custom_name = st.text_input(
            "自定义规则名称",
            value="",
            key="new_rule_name",
            placeholder=f"如：{RULE_META.get(base_rule_type, {}).get('title', base_rule_type)}—高敏感",
        )
    with col2:
        st.caption("参数将从选中的基础模板复制。创建后可在规则卡片中进一步调整。")
        st.caption(f"基础模板: **{RULE_META.get(base_rule_type, {}).get('title', base_rule_type)}**")
        st.caption(f"审计目的: {RULE_META.get(base_rule_type, {}).get('purpose', '')}")

    if st.button("➕ 创建规则", type="primary", use_container_width=True, key="btn_create_rule"):
        if not custom_name.strip():
            st.warning("请输入规则名称。")
            return

        # Generate unique key
        st.session_state.custom_rule_counter += 1
        counter = st.session_state.custom_rule_counter
        new_key = f"{base_rule_type}_custom_{counter}"

        # Clone from base config or current config
        source_rule = st.session_state.rules_config.get(base_rule_type, base_cfg.get(base_rule_type, {}))
        new_rule = {**source_rule, "enabled": True}
        new_rule["rationale"] = f"自定义规则：{custom_name.strip()}（基于{RULE_META.get(base_rule_type, {}).get('title', base_rule_type)}）"

        st.session_state.rules_config[new_key] = new_rule
        if new_key not in st.session_state.custom_rule_keys:
            st.session_state.custom_rule_keys.append(new_key)

        # Add meta info for display
        RULE_META[new_key] = {
            "title": custom_name.strip(),
            "purpose": f"自定义规则，基于 {RULE_META.get(base_rule_type, {}).get('title', base_rule_type)}",
        }

        st.success(f"已创建自定义规则：{custom_name.strip()}（键名：{new_key}）")
        st.rerun()


def _clone_rule(rule_key: str):
    """克隆一条规则。"""
    cfg = st.session_state.rules_config
    source = cfg.get(rule_key, {})
    if not source:
        return

    st.session_state.custom_rule_counter += 1
    counter = st.session_state.custom_rule_counter
    base = rule_key.split("_custom_")[0] if "_custom_" in rule_key else rule_key
    new_key = f"{base}_custom_{counter}"

    new_rule = {**source, "enabled": True}
    old_title = RULE_META.get(rule_key, {}).get("title", rule_key)
    new_rule["rationale"] = f"克隆自 {old_title} — {source.get('rationale', '')}"

    cfg[new_key] = new_rule
    if new_key not in st.session_state.custom_rule_keys:
        st.session_state.custom_rule_keys.append(new_key)

    RULE_META[new_key] = {
        "title": f"{old_title} (克隆)",
        "purpose": RULE_META.get(rule_key, {}).get("purpose", ""),
    }

    st.success(f"已克隆：{old_title} → {RULE_META[new_key]['title']}")


def _delete_rule(rule_key: str, title: str):
    """删除一条自定义规则。"""
    cfg = st.session_state.rules_config
    if rule_key in cfg:
        del cfg[rule_key]
    if rule_key in st.session_state.custom_rule_keys:
        st.session_state.custom_rule_keys.remove(rule_key)
    if rule_key in RULE_META and "_custom_" in rule_key:
        del RULE_META[rule_key]
    st.success(f"已删除：{title}")
