"""全局 CSS 注入。

从 app.py 抽离的纯静态样式表，不含任何业务逻辑。
调用 inject_global_css() 须在 st.set_page_config() 之后、其他 UI 渲染之前。
"""

from __future__ import annotations

import streamlit as st

# ── 全局样式表 ──
GLOBAL_CSS = """
<style>
/* ── 根变量 ── */
:root {
    --accent: #4f8ef7;
    --accent-soft: rgba(79, 142, 247, 0.12);
    --gold: #d4a853;
    --gold-soft: rgba(212, 168, 83, 0.10);
    --red: #f87171;
    --green: #4ade80;
    --radius: 6px;
    --radius-lg: 10px;
}

/* ── 全局字体 ── */
html, body, .stApp {
    font-feature-settings: "cv02", "cv03", "cv04", "cv11";
}

/* ── 卡片容器 ── */
[data-testid="stExpander"] details,
div[data-testid="stVerticalBlockBorderWrapper"] {
    border: 1px solid rgba(255,255,255,0.06) !important;
    border-radius: var(--radius-lg) !important;
    background: rgba(255,255,255,0.015) !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.2) !important;
    transition: border-color 0.2s ease;
}
[data-testid="stExpander"] details:hover,
div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    border-color: rgba(255,255,255,0.12) !important;
}

/* ── Metrics 指标卡 ── */
[data-testid="stMetric"] {
    background: linear-gradient(135deg, rgba(79,142,247,0.06), rgba(79,142,247,0.02));
    border: 1px solid rgba(79,142,247,0.10);
    border-radius: var(--radius-lg);
    padding: 0.6rem 0.8rem;
    transition: border-color 0.2s ease;
}
[data-testid="stMetric"]:hover {
    border-color: rgba(79,142,247,0.22);
}
[data-testid="stMetric"] label {
    font-size: 0.7rem !important;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: rgba(220,226,234,0.55) !important;
}
[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-size: 1.4rem !important;
    font-weight: 600 !important;
}

/* ── 按钮（圆角胶囊形）── */
.stButton > button {
    border-radius: 24px !important;
    font-weight: 500 !important;
    letter-spacing: 0.3px;
    transition: all 0.15s ease !important;
}
.stButton > button[kind="primary"] {
    border: none !important;
}
.stButton > button[kind="primary"]:hover {
    filter: brightness(1.1);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(79,142,247,0.3);
}

/* ── 数据表格 ── */
[data-testid="stDataFrame"] {
    border-radius: var(--radius-lg) !important;
    overflow: hidden;
    border: 1px solid rgba(255,255,255,0.06) !important;
}

/* ── 分割线 ── */
hr, [data-testid="stDivider"] {
    border-color: rgba(255,255,255,0.06) !important;
    margin: 1.2rem 0 !important;
}

/* ── Checkbox / Toggle ── */
[data-testid="stCheckbox"] label {
    font-weight: 500 !important;
}

/* ── Expander 头部 ── */
[data-testid="stExpander"] summary {
    font-weight: 500 !important;
    font-size: 0.9rem !important;
    color: rgba(220,226,234,0.85) !important;
}

/* ── 进度条 ── */
[data-testid="stProgress"] > div > div {
    background: linear-gradient(90deg, var(--accent), #818cf8) !important;
    border-radius: 4px !important;
}

/* ── Radio / Segmented control ── */
[data-testid="stSegmentedControl"] {
    background: rgba(255,255,255,0.03) !important;
    border-radius: var(--radius) !important;
    padding: 3px !important;
}
[data-testid="stSegmentedControl"] label {
    border-radius: calc(var(--radius) - 2px) !important;
    transition: all 0.2s ease !important;
}

/* ── Selectbox / Text input ── */
[data-testid="stSelectbox"] > div > div,
[data-testid="stTextInput"] input,
.stTextArea textarea,
.stNumberInput input {
    border-radius: var(--radius) !important;
    border-color: rgba(255,255,255,0.10) !important;
}
[data-testid="stSelectbox"] > div > div:focus-within,
[data-testid="stTextInput"] input:focus,
.stTextArea textarea:focus,
.stNumberInput input:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 2px rgba(79,142,247,0.15) !important;
}

/* ── Tab 内部 st.tabs ── */
.stTabs [data-baseweb="tab"] {
    font-size: 0.85rem;
    font-weight: 500;
}
.stTabs [data-baseweb="tab-highlight"] {
    background: var(--accent) !important;
}

/* ── 侧边栏优化 ── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d1320 0%, #0c1117 100%);
    border-right: 1px solid rgba(255,255,255,0.05);
}
[data-testid="stSidebar"] .stMetric {
    background: rgba(255,255,255,0.03) !important;
    border: 1px solid rgba(255,255,255,0.04) !important;
}

/* ── 图表容器 ── */
.js-plotly-plot {
    border-radius: var(--radius-lg);
    overflow: hidden;
}

/* ── 滚动条 ── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
    background: rgba(255,255,255,0.08);
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.15); }
</style>
"""


def inject_global_css() -> None:
    """注入全局样式。须在 st.set_page_config() 之后调用。"""
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
