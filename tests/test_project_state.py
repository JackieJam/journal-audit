"""项目状态持久化（保存/载入）的单元测试。

重点验证 autosave 性能优化的正确性与可审计性：
- 重数据（df_unified / year_map）与轻状态拆成两个文件。
- 数据签名未变时跳过重写重数据（autosave 提速的核心），轻状态仍更新。
- 显式 ``data_changed=True`` 或数据结构变化时强制重写重数据（不丢数据）。
- 兼容历史的单文件全量格式，并在下次保存时升级为拆分格式。
- API Key 永不落盘。
"""

from __future__ import annotations

import gzip
import json
import pickle
from pathlib import Path

import pandas as pd
import pytest

from modules import knowledge_base as kb

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _isolate_storage(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(kb, "storage_root", lambda: tmp_path)
    yield


def _df(rows: int = 3) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "凭证编号": [f"V{i:04d}" for i in range(rows)],
            "凭证货币价值": [100.0 * i for i in range(rows)],
            "_year": [2023] * rows,
        }
    )


def _state(df: pd.DataFrame | None = None, **light) -> dict:
    base = {
        "df_unified": df if df is not None else _df(),
        "year_map": {2023: df if df is not None else _df()},
        "candidate_pool": [],
        "rules_config": None,
        "_api_key": "sk-should-not-persist",
    }
    base.update(light)
    return base


def _meta_path(project_id: str, tmp_path: Path) -> Path:
    return tmp_path / "projects" / project_id / "metadata.json"


# ── 拆分文件布局 ───────────────────────────────────────────────────────


def test_save_creates_split_files(tmp_path: Path) -> None:
    meta = kb.save_project_state("演示_2023", _state())
    pid = meta["project_id"]
    proj = tmp_path / "projects" / pid
    assert (proj / "data.pkl.gz").exists()
    assert (proj / "state.pkl.gz").exists()
    assert (proj / "metadata.json").exists()
    assert meta.get("data_signature")  # 元数据记录了签名


def test_light_state_file_excludes_heavy_data(tmp_path: Path) -> None:
    meta = kb.save_project_state("演示_2023", _state())
    pid = meta["project_id"]
    with gzip.open(tmp_path / "projects" / pid / "state.pkl.gz", "rb") as f:
        light = pickle.load(f)
    assert "df_unified" not in light
    assert "year_map" not in light
    assert "candidate_pool" in light


# ── round-trip 完整性 ──────────────────────────────────────────────────


def test_roundtrip_restores_full_state(tmp_path: Path) -> None:
    meta = kb.save_project_state("演示_2023", _state(candidate_pool=[{"id": 1}]))
    loaded = kb.load_project_state(meta["project_id"])
    state = loaded["state"]
    assert state["candidate_pool"] == [{"id": 1}]
    assert isinstance(state["df_unified"], pd.DataFrame)
    assert len(state["df_unified"]) == 3
    assert 2023 in state["year_map"]


def test_api_key_never_persisted(tmp_path: Path) -> None:
    meta = kb.save_project_state("演示_2023", _state())
    loaded = kb.load_project_state(meta["project_id"])
    assert "_api_key" not in loaded["state"]


# ── 性能核心：签名未变跳过重写重数据 ───────────────────────────────────


def test_autosave_skips_data_rewrite_when_unchanged(tmp_path: Path) -> None:
    df = _df()
    meta = kb.save_project_state("演示_2023", _state(df=df))
    pid = meta["project_id"]
    data_file = tmp_path / "projects" / pid / "data.pkl.gz"
    first_mtime = data_file.stat().st_mtime_ns

    # 第二次保存：只改轻状态，df 不变 → 重数据文件不应被重写
    kb.save_project_state("演示_2023", _state(df=df, candidate_pool=[{"id": 9}]), project_id=pid)
    assert data_file.stat().st_mtime_ns == first_mtime  # 跳过 gzip 大头

    # 但轻状态确实更新了
    loaded = kb.load_project_state(pid)
    assert loaded["state"]["candidate_pool"] == [{"id": 9}]


def test_data_changed_flag_forces_rewrite(tmp_path: Path) -> None:
    df = _df()
    meta = kb.save_project_state("演示_2023", _state(df=df))
    pid = meta["project_id"]
    data_file = tmp_path / "projects" / pid / "data.pkl.gz"
    first_mtime = data_file.stat().st_mtime_ns

    kb.save_project_state("演示_2023", _state(df=df), project_id=pid, data_changed=True)
    assert data_file.stat().st_mtime_ns != first_mtime


def test_structural_change_rewrites_data(tmp_path: Path) -> None:
    meta = kb.save_project_state("演示_2023", _state(df=_df(3)))
    pid = meta["project_id"]
    sig1 = meta["data_signature"]

    meta2 = kb.save_project_state("演示_2023", _state(df=_df(10)), project_id=pid)
    assert meta2["data_signature"] != sig1
    loaded = kb.load_project_state(pid)
    assert len(loaded["state"]["df_unified"]) == 10


# ── 向后兼容：历史单文件全量格式 ───────────────────────────────────────


def test_legacy_single_file_loads_and_upgrades(tmp_path: Path) -> None:
    pid = kb.project_id_for_name("旧项目")
    proj = tmp_path / "projects" / pid
    proj.mkdir(parents=True)
    # 历史格式：state.pkl.gz 含全部键（包括 df），无 data.pkl.gz
    legacy = {"df_unified": _df(5), "year_map": {2023: _df(5)}, "candidate_pool": [{"old": True}]}
    with gzip.open(proj / "state.pkl.gz", "wb") as f:
        pickle.dump(legacy, f)
    (proj / "metadata.json").write_text(json.dumps({"project_id": pid, "project_name": "旧项目"}), encoding="utf-8")

    # 读得出完整状态
    loaded = kb.load_project_state(pid)
    assert len(loaded["state"]["df_unified"]) == 5
    assert loaded["state"]["candidate_pool"] == [{"old": True}]

    # 再次保存升级为拆分格式
    kb.save_project_state("旧项目", loaded["state"], project_id=pid)
    assert (proj / "data.pkl.gz").exists()
    with gzip.open(proj / "state.pkl.gz", "rb") as f:
        light = pickle.load(f)
    assert "df_unified" not in light
