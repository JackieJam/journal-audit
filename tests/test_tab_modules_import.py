"""页签模块导入冒烟测试。

app.py 把页签渲染逻辑抽到 components/tabs/，这些模块本身是 Streamlit UI 代码、
难以单测，但至少要保证「能 import、入口函数存在」——防止重构时引错名/漏依赖
导致整个页签在运行时才崩。
"""

from __future__ import annotations

import importlib

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "module_name, entry",
    [
        ("components.tabs.upload", "render_upload_tab"),
        ("components.tabs.rules", "render_rules_tab"),
        ("components.tabs.sampling", "render_sampling_tab"),
        ("components.tabs.analysis", "render_working_capital_main"),
    ],
)
def test_tab_module_imports(module_name: str, entry: str) -> None:
    module = importlib.import_module(module_name)
    assert callable(getattr(module, entry))


def test_sampling_report_dir_is_repo_root() -> None:
    from components.tabs import sampling

    # 报告必须落在仓库根目录（与原 app.py 行为一致），而非 components/tabs/
    assert (sampling._REPORT_DIR / "app.py").exists()
