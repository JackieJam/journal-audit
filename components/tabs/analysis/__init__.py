"""序时账分析页签包。

对外暴露 3 个入口，保持与 app.py 原有 import 路径（components.tabs.analysis）兼容：
- render_analysis_tab：页签真正入口
- render_working_capital_main / render_adjustment_main：被 app.py 包装成 helper 后注入
"""

from __future__ import annotations

from .adjustment import render_adjustment_main
from .tab import render_analysis_tab
from .working_capital import render_working_capital_main

__all__ = [
    "render_analysis_tab",
    "render_working_capital_main",
    "render_adjustment_main",
]
