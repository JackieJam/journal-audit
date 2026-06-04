"""
侧边栏渲染模块。
从 app.py 提取而来，保持原有逻辑不变。
"""

from __future__ import annotations

import streamlit as st

from modules import knowledge_base as kb
from modules import llm_config
from modules.runtime_context import storage_namespace_label
from modules.llm_quota import quota_status


def render_sidebar(
    *,
    _save_current_project_state,
    _restore_project_state,
    _reset_current_project,
    _create_blank_project,
    _project_option_label,
    _llm_profile_option_label,
    _save_llm_config,
    _set_llm_config_inputs,
    _initial_llm_config,
    _resolve_api_key,
    _llm_config,
    _llm_model,
    _llm_base_url,
    _keychain_account,
    _has_project_payload,
    _project_name_exists,
    _set_project_name_input,
    DEFAULT_LLM_CONFIG,
):
    with st.sidebar:
        st.title("序时账审计平台")
        st.divider()

        if "_pending_project_name_input" in st.session_state:
            st.session_state.project_name_input = st.session_state.pop("_pending_project_name_input")
        if "_pending_new_project_name" in st.session_state:
            st.session_state.new_project_name = st.session_state.pop("_pending_new_project_name")
        if "project_name_input" not in st.session_state:
            st.session_state.project_name_input = st.session_state.get("engagement_name", "")

        # 当前工作区
        st.subheader("当前项目")
        project_name_input = st.text_input(
            "项目名称",
            key="project_name_input",
            placeholder="如：运载_2023",
        )
        st.session_state.engagement_name = project_name_input.strip()

        active_project_id = st.session_state.get("loaded_project_id")
        if active_project_id:
            st.caption(f"状态：已保存项目 `{active_project_id}`")
        elif st.session_state.engagement_name:
            st.caption("状态：未保存的当前工作区")
        else:
            st.caption("状态：尚未创建项目")

        current_rows = len(st.session_state.df_unified) if st.session_state.get("df_unified") is not None else 0
        current_years = "、".join(str(y) for y in sorted(st.session_state.get("year_map", {}).keys())) or "未上传"
        st.caption(f"数据：{current_years} | {current_rows:,} 行")
        st.caption(f"隔离命名空间：{storage_namespace_label()}")

        save_disabled = not st.session_state.engagement_name
        if st.button("保存当前项目", disabled=save_disabled, use_container_width=True):
            try:
                ok, message = _save_current_project_state()
                if ok:
                    st.success(message)
                    st.rerun()
                else:
                    st.warning(message)
            except Exception as e:
                st.error(f"保存失败：{e}")

        st.divider()

        # 历史项目管理
        with st.expander("📁 载入/删除项目", expanded=False):
            projects = kb.list_projects()
            if projects:
                project_labels = {
                    _project_option_label(p): p["project_id"]
                    for p in projects
                }
                selected_project_label = st.selectbox(
                    "选择项目",
                    options=list(project_labels.keys()),
                    key="project_memory_select",
                    label_visibility="collapsed"
                )
                open_col, delete_col = st.columns(2)
                with open_col:
                    if st.button("载入", use_container_width=True):
                        try:
                            metadata = _restore_project_state(project_labels[selected_project_label])
                            st.success(f"已载入：{metadata.get('project_name', '项目')}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"载入失败：{e}")

                delete_confirmed = st.checkbox("确认删除所选历史项目", key="confirm_delete_project")
                with delete_col:
                    if st.button("删除", disabled=not delete_confirmed, use_container_width=True):
                        project_id = project_labels[selected_project_label]
                        project_name = selected_project_label.split(" | ")[0]
                        try:
                            deleted = kb.delete_project_state(project_id)
                            if deleted:
                                if st.session_state.get("loaded_project_id") == project_id:
                                    _reset_current_project()
                                st.success(f"已删除项目：{project_name}")
                                st.rerun()
                            else:
                                st.warning("未找到要删除的项目缓存。")
                        except Exception as e:
                            st.error(f"删除失败：{e}")
            else:
                st.caption("暂无已保存项目。")

        # 新增项目
        with st.expander("➕ 新增项目", expanded=False):
            new_project_name = st.text_input(
                "新项目名称",
                key="new_project_name",
                placeholder="输入名称后创建空白项目",
                label_visibility="collapsed"
            )
            new_project_name_clean = new_project_name.strip()
            has_current_work = bool(st.session_state.engagement_name or active_project_id or _has_project_payload())
            name_conflict = _project_name_exists(new_project_name_clean) if new_project_name_clean else False
            if name_conflict:
                st.warning("已有同名项目")
            
            discard_confirmed = True
            if has_current_work:
                discard_confirmed = st.checkbox("确认切换到空白项目", key="confirm_new_blank_project")
            
            create_disabled = not new_project_name_clean or name_conflict or (has_current_work and not discard_confirmed)
            if st.button("创建项目", disabled=create_disabled, use_container_width=True):
                try:
                    ok, message = _create_blank_project(new_project_name_clean)
                    if ok:
                        st.success(message)
                        st.rerun()
                    else:
                        st.warning(message)
                except Exception as e:
                    st.error(f"创建失败：{e}")

        # LLM 配置。一个表单 + 一个「保存方案」按钮搞定：方案随本机持久化（刷新自动恢复），
        # API Key 默认记住到本机钥匙串/加密文件，下次会话无需重输。Key 永不写入项目缓存或方案文件。
        with st.expander("🔑 LLM 配置", expanded=not bool(_resolve_api_key()[0])):
            cfg = _llm_config()

            # ── 已保存方案：切换 / 删除 ──
            saved_profiles = kb.list_llm_profiles()
            if saved_profiles:
                profile_by_label = {
                    _llm_profile_option_label(profile): profile
                    for profile in saved_profiles
                }
                profile_options = ["当前编辑方案"] + list(profile_by_label.keys())
                if "llm_profile_select" not in st.session_state:
                    current_profile_id = cfg.get("profile_id", "")
                    matched_label = next(
                        (
                            label
                            for label, profile in profile_by_label.items()
                            if profile.get("profile_id") == current_profile_id
                        ),
                        None,
                    )
                    st.session_state.llm_profile_select = matched_label or profile_options[0]
                elif st.session_state.get("llm_profile_select") not in profile_options:
                    st.session_state.llm_profile_select = profile_options[0]
                selected_profile_label = st.selectbox(
                    "已保存方案",
                    options=profile_options,
                    key="llm_profile_select",
                )
                selected_profile = profile_by_label.get(selected_profile_label)
                load_col, delete_col = st.columns(2)
                with load_col:
                    if st.button(
                        "载入",
                        key="llm_profile_load",
                        disabled=selected_profile is None,
                        use_container_width=True,
                    ):
                        _save_llm_config(selected_profile or {})
                        _set_llm_config_inputs()
                        st.success("已载入 LLM 方案。")
                        st.rerun()
                with delete_col:
                    if st.button(
                        "删除",
                        key="llm_profile_delete",
                        disabled=selected_profile is None,
                        use_container_width=True,
                    ):
                        if kb.delete_llm_profile(str((selected_profile or {}).get("profile_id", ""))):
                            _save_llm_config(_initial_llm_config())
                            _set_llm_config_inputs()
                            st.success("已删除 LLM 方案；本机记住的 API Key 未删除。")
                            st.rerun()
                        else:
                            st.warning("未找到要删除的 LLM 方案。")
            else:
                st.caption("暂无已保存方案。点「保存方案」后，刷新页面会自动恢复。")

            # ── 编辑当前方案 ──
            profile_name = st.text_input(
                "方案名称",
                value=cfg.get("profile_name", DEFAULT_LLM_CONFIG["profile_name"]),
                key="llm_profile_name_input",
            )
            base_url = st.text_input(
                "Base URL",
                value=cfg.get("base_url", DEFAULT_LLM_CONFIG["base_url"]),
                key="llm_base_url_input",
            )
            model = st.text_input(
                "模型",
                value=cfg.get("model", DEFAULT_LLM_CONFIG["model"]),
                key="llm_model_input",
            )
            _save_llm_config({
                "profile_name": profile_name.strip() or DEFAULT_LLM_CONFIG["profile_name"],
                "base_url": base_url.strip() or DEFAULT_LLM_CONFIG["base_url"],
                "model": model.strip() or DEFAULT_LLM_CONFIG["model"],
            })

            # ── API Key ──
            manual_key = st.text_input(
                "API Key",
                type="password",
                placeholder="sk-...",
                key="_manual_api_key",
                help="也可设置环境变量 DEEPSEEK_API_KEY / OPENAI_API_KEY / LLM_API_KEY（优先级最高）。",
            )
            remember_key = st.checkbox(
                "记住密钥到本机（下次免输入）",
                value=True,
                key="llm_remember_key",
                help="存入本机钥匙串/加密文件，仅本机可读；绝不写入项目缓存或方案文件。取消勾选并保存可清除。",
            )

            # ── 单一保存动作：方案 + 密钥一起落地 ──
            if st.button("保存方案", type="primary", use_container_width=True):
                try:
                    saved_profile = kb.save_llm_profile(_llm_config(), set_default=True)
                    _save_llm_config(saved_profile)
                    account = saved_profile.get("keychain_account") or "default"
                    key_msg = ""
                    typed_key = (manual_key or "").strip()
                    if remember_key:
                        if typed_key:
                            if llm_config.remember_key(account, typed_key):
                                key_msg = "，密钥已记住到本机"
                            else:
                                key_msg = "，但密钥保存失败（本机钥匙串不可用）"
                    else:
                        llm_config.forget_key(account)
                        key_msg = "，已清除本机记住的密钥"
                    st.success(f"方案已保存{key_msg}；刷新后自动恢复。")
                    st.rerun()
                except Exception as e:
                    st.error(f"保存失败：{e}")

            # ── 状态（可审计：来源始终可见）──
            api_key, key_source = _resolve_api_key()
            st.session_state["_api_key"] = api_key
            if api_key:
                st.success(f"✅ API Key 已就绪（来源：{key_source}）")
            else:
                st.warning("⚠️ 尚未配置 API Key：在上方输入，或设置环境变量后刷新。")
            if llm_config.has_remembered_key(_keychain_account()):
                st.caption("🔒 本机已记住此方案的密钥")
            st.caption(f"当前方案：{_llm_model()} | {_llm_base_url()}")
            quota = quota_status()
            if quota.get("limit", 0):
                st.caption(
                    f"今日 LLM 调用：{quota.get('current', 0)}/{quota.get('limit', 0)}"
                )

        st.divider()

        # 经验库快速统计
        st.subheader("经验库")
        stats = kb.library_stats()
        col1, col2 = st.columns(2)
        col1.metric("规则总数", stats.get("total_rules", 0))
        col2.metric("平均确认率", f"{stats.get('avg_confirmation_rate', 0):.0%}")

        if stats.get("total_rules", 0) > 0:
            with st.expander("查看经验库"):
                for rule in kb.list_rules()[:5]:
                    rate = rule.get("performance", {}).get("confirmation_rate", 0)
                    st.markdown(f"**{rule['name']}** `{rate:.0%}` — {rule.get('rationale', '')[:40]}…")
