"""疑点库管理 top sub-tab（_sub_tab_top == 2）。"""

from __future__ import annotations

from typing import Any

import streamlit as st

from modules import candidate_pool as cp


def render_pool_management(*, helpers: dict[str, Any]) -> None:
    _format_money = helpers["_format_money"]
    _autosave_current_project_state = helpers["_autosave_current_project_state"]

    pool = st.session_state.get("candidate_pool", [])
    stats = cp.pool_stats(pool)

    st.markdown("#### 候选池概览")
    stat_cols = st.columns(5)
    stat_cols[0].metric("候选群体", stats["groups"])
    stat_cols[1].metric("有效群体", stats["active_groups"])
    stat_cols[2].metric("有效凭证", stats["active_vouchers"])
    stat_cols[3].metric("人工直入凭证", stats["manual_final_vouchers"])
    stat_cols[4].metric("总金额", _format_money(stats["amount_total"]))

    if not pool:
        st.info("候选池为空。请先在「可疑样本库筛选」中通过图表交互或模型建议将疑点凭证加入候选池。")
    else:
        st.divider()
        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            status_options = ["全部"] + list({g.get("status", "active") for g in pool})
            status_filter = st.selectbox("按状态筛选", status_options, key="pool_status_filter")
        with filter_col2:
            module_options = ["全部"] + list({g.get("source_module", "未知") for g in pool})
            module_filter = st.selectbox("按来源模块筛选", module_options, key="pool_module_filter")

        filtered = pool
        if status_filter != "全部":
            filtered = [g for g in filtered if g.get("status", "active") == status_filter]
        if module_filter != "全部":
            filtered = [g for g in filtered if g.get("source_module", "未知") == module_filter]

        groups_df = cp.groups_to_table(filtered)
        if groups_df.empty:
            st.info("当前筛选条件下没有匹配的疑点群体。")
        else:
            display_cols = [c for c in groups_df.columns if c != "group_id"]
            st.dataframe(groups_df[display_cols], width="stretch", hide_index=True)

            st.divider()
            st.markdown("#### 批量操作")

            def _fmt_gid(gid):
                for g in filtered:
                    if g["group_id"] == gid:
                        s = g.get("status", "?")
                        t = g.get("title", "")
                        vc = g.get("voucher_count", 0)
                        return f"[{s}] {t} ({vc}凭证)"
                return gid

            selected_ids = st.multiselect(
                "选择群体进行批量操作",
                options=[g["group_id"] for g in filtered],
                format_func=_fmt_gid,
                key="pool_batch_select",
            )

            if selected_ids:
                batch_col1, batch_col2, batch_col3 = st.columns(3)
                with batch_col1:
                    if st.button("标记为已审核", width="stretch", key="pool_mark_reviewed"):
                        for gid in selected_ids:
                            st.session_state.candidate_pool = cp.update_candidate_status(
                                st.session_state.candidate_pool, gid, "reviewed"
                            )
                        _autosave_current_project_state()
                        st.rerun()
                with batch_col2:
                    if st.button("排除选中群体", width="stretch", key="pool_mark_excluded"):
                        for gid in selected_ids:
                            st.session_state.candidate_pool = cp.update_candidate_status(
                                st.session_state.candidate_pool, gid, "excluded"
                            )
                        _autosave_current_project_state()
                        st.rerun()
                with batch_col3:
                    if st.button("移除选中群体", type="secondary", width="stretch", key="pool_remove_selected"):
                        for gid in selected_ids:
                            st.session_state.candidate_pool = cp.remove_candidate_group(
                                st.session_state.candidate_pool, gid
                            )
                        _autosave_current_project_state()
                        st.rerun()
