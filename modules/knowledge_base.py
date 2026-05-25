"""
经验库模块：跨项目持久化有效规则，存储在 ~/.audit_tool/rule_library.json。
所有经验库读写操作通过本模块，其他模块不直接操作文件。
"""

from __future__ import annotations

import gzip
import hashlib
import json
import pickle
import re
import shutil
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from modules.locking import file_lock
from modules.runtime_context import storage_root

def _root() -> Path:
    return storage_root()


def _library_path() -> Path:
    return _root() / "rule_library.json"


def _library_lock_path() -> Path:
    return _root() / ".rule_library.lock"


def _projects_dir() -> Path:
    return _root() / "projects"


def _project_lock_path(project_id: str) -> Path:
    return _projects_dir() / project_id / ".project.lock"


def _llm_profiles_path() -> Path:
    return _root() / "llm_profiles.json"


def _llm_profiles_lock_path() -> Path:
    return _root() / ".llm_profiles.lock"


def _llm_profile_id(profile_name: str) -> str:
    base = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", profile_name.strip())
    base = base.strip("_")[:40] or "llm_profile"
    digest = hashlib.sha1(profile_name.strip().encode("utf-8")).hexdigest()[:8]
    return f"llm_{base}_{digest}"


def _load_llm_profiles() -> list[dict[str, Any]]:
    path = _llm_profiles_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    profiles: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict) and item.get("profile_name"):
            profiles.append(item)
    return profiles


def _save_llm_profiles(profiles: list[dict[str, Any]]) -> None:
    path = _llm_profiles_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_profiles = []
    for profile in profiles:
        safe_profiles.append({
            "profile_id": str(profile.get("profile_id", "")).strip(),
            "profile_name": str(profile.get("profile_name", "")).strip(),
            "base_url": str(profile.get("base_url", "")).strip(),
            "model": str(profile.get("model", "")).strip(),
            "key_source": str(profile.get("key_source", "env_or_keychain")).strip() or "env_or_keychain",
            "keychain_account": str(profile.get("keychain_account", "default")).strip() or "default",
            "is_default": bool(profile.get("is_default", False)),
            "updated_at": str(profile.get("updated_at", "")),
        })
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(json.dumps(safe_profiles, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)
    try:
        path.chmod(0o600)
    except Exception:
        pass


def list_llm_profiles() -> list[dict[str, Any]]:
    """列出本机保存的 LLM 方案。不会包含 API Key 明文。"""
    profiles = _load_llm_profiles()
    return sorted(
        profiles,
        key=lambda p: (bool(p.get("is_default")), p.get("updated_at", "")),
        reverse=True,
    )


def get_llm_profile(profile_id: str) -> dict[str, Any] | None:
    """按 ID 读取 LLM 方案。"""
    clean_id = str(profile_id or "").strip()
    if not clean_id:
        return None
    for profile in _load_llm_profiles():
        if profile.get("profile_id") == clean_id:
            return dict(profile)
    return None


def get_default_llm_profile() -> dict[str, Any] | None:
    """读取默认 LLM 方案；若未设置默认，则取最近更新的一条。"""
    profiles = list_llm_profiles()
    if not profiles:
        return None
    for profile in profiles:
        if profile.get("is_default"):
            return dict(profile)
    return dict(profiles[0])


def save_llm_profile(profile: dict[str, Any], set_default: bool = False) -> dict[str, Any]:
    """保存/更新 LLM 方案。API Key 明文会被忽略。"""
    profile_name = str(profile.get("profile_name", "")).strip()
    if not profile_name:
        raise ValueError("方案名称不能为空")

    with file_lock(_llm_profiles_lock_path(), exclusive=True):
        profiles = _load_llm_profiles()
        profile_id = str(profile.get("profile_id", "")).strip()
        if not profile_id:
            existing = next((p for p in profiles if p.get("profile_name") == profile_name), None)
            profile_id = existing.get("profile_id") if existing else _llm_profile_id(profile_name)

        saved = {
            "profile_id": profile_id,
            "profile_name": profile_name,
            "base_url": str(profile.get("base_url", "")).strip(),
            "model": str(profile.get("model", "")).strip(),
            "key_source": str(profile.get("key_source", "env_or_keychain")).strip() or "env_or_keychain",
            "keychain_account": str(profile.get("keychain_account", "default")).strip() or "default",
            "is_default": bool(set_default or profile.get("is_default", False)),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }

        profiles = [p for p in profiles if p.get("profile_id") != profile_id]
        if saved["is_default"] or not profiles:
            for item in profiles:
                item["is_default"] = False
            saved["is_default"] = True
        profiles.append(saved)
        _save_llm_profiles(profiles)
        return dict(saved)


def delete_llm_profile(profile_id: str) -> bool:
    """删除本机 LLM 方案。不会删除钥匙串中的 API Key。"""
    clean_id = str(profile_id or "").strip()
    if not clean_id:
        return False
    with file_lock(_llm_profiles_lock_path(), exclusive=True):
        profiles = _load_llm_profiles()
        kept = [p for p in profiles if p.get("profile_id") != clean_id]
        if len(kept) == len(profiles):
            return False
        if kept and not any(p.get("is_default") for p in kept):
            kept[0]["is_default"] = True
        _save_llm_profiles(kept)
        return True


def _load() -> list[dict]:
    path = _library_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return data


def _save(rules: list[dict]) -> None:
    path = _library_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(
        json.dumps(rules, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(path)
    try:
        path.chmod(0o600)
    except Exception:
        pass


def list_rules(category: str | None = None, tags: list[str] | None = None) -> list[dict]:
    """查询经验库，可按分类或标签过滤。"""
    rules = _load()
    if category:
        rules = [r for r in rules if r.get("category") == category]
    if tags:
        rules = [r for r in rules if any(t in r.get("tags", []) for t in tags)]
    return sorted(rules, key=lambda r: r.get("performance", {}).get("confirmation_rate", 0), reverse=True)


def save_rule(
    name: str,
    category: str,
    parameters: dict[str, Any],
    rationale: str,
    engagement: str,
    hits: int,
    confirmed: int,
    company_notes: str = "",
    tags: list[str] | None = None,
) -> str:
    """保存一条有效规则，返回 rule_id。"""
    with file_lock(_library_lock_path(), exclusive=True):
        rules = _load()

        # 查找同名同分类的现有规则
        existing = next(
            (r for r in rules if r["name"] == name and r["category"] == category), None
        )

        confirmation_rate = round(confirmed / hits, 4) if hits > 0 else 0

        if existing:
            # 更新命中率（加权累计）
            prev_perf = existing.get("performance", {})
            prev_hits = prev_perf.get("total_hits", 0) + hits
            prev_confirmed = prev_perf.get("total_confirmed", 0) + confirmed
            existing["performance"] = {
                "engagements_used": prev_perf.get("engagements_used", 0) + 1,
                "total_hits": prev_hits,
                "total_confirmed": prev_confirmed,
                "confirmation_rate": round(prev_confirmed / prev_hits, 4) if prev_hits > 0 else 0,
            }
            existing["last_used"] = str(date.today())
            existing["last_engagement"] = engagement
            _save(rules)
            return existing["rule_id"]

        rule_id = f"rul_{date.today().strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}"
        new_rule = {
            "rule_id": rule_id,
            "name": name,
            "category": category,
            "parameters": parameters,
            "rationale": rationale,
            "applicable_context": {"notes": company_notes},
            "performance": {
                "engagements_used": 1,
                "total_hits": hits,
                "total_confirmed": confirmed,
                "confirmation_rate": confirmation_rate,
            },
            "source_engagement": engagement,
            "last_used": str(date.today()),
            "tags": tags or [],
        }
        rules.append(new_rule)
        _save(rules)
        return rule_id


def delete_rule(rule_id: str) -> bool:
    with file_lock(_library_lock_path(), exclusive=True):
        rules = _load()
        before = len(rules)
        rules = [r for r in rules if r["rule_id"] != rule_id]
        if len(rules) < before:
            _save(rules)
            return True
        return False


def get_recommendations(profiles_summary: str, top_n: int = 8) -> list[dict]:
    """
    为新项目推荐历史有效规则。
    当前实现：按确认率降序取 top_n。
    未来可接入语义检索。
    """
    rules = list_rules()
    return rules[:top_n]


def export_library() -> str:
    """导出经验库为 JSON 字符串，用于分享或备份。"""
    return json.dumps(_load(), ensure_ascii=False, indent=2)


def import_library(json_str: str, merge: bool = True) -> int:
    """
    导入经验库，merge=True 时与现有合并（按 rule_id 去重），
    merge=False 时覆盖。返回导入条数。
    """
    incoming: list[dict] = json.loads(json_str)
    with file_lock(_library_lock_path(), exclusive=True):
        if not merge:
            _save(incoming)
            return len(incoming)

        existing = _load()
        existing_ids = {r["rule_id"] for r in existing}
        added = 0
        for r in incoming:
            if r["rule_id"] not in existing_ids:
                existing.append(r)
                added += 1
        _save(existing)
        return added


def library_stats() -> dict:
    rules = _load()
    if not rules:
        return {"total_rules": 0}

    avg_rate = sum(r.get("performance", {}).get("confirmation_rate", 0) for r in rules) / len(rules)
    categories = {}
    for r in rules:
        cat = r.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

    return {
        "total_rules": len(rules),
        "avg_confirmation_rate": round(avg_rate, 4),
        "categories": categories,
        "engagements": list({r.get("source_engagement", "") for r in rules}),
    }


# ── 项目记忆：保存已读取和已执行的项目状态 ──

def _project_id(project_name: str) -> str:
    base = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", project_name.strip())
    base = base.strip("_")[:40] or "unnamed"
    digest = hashlib.sha1(project_name.strip().encode("utf-8")).hexdigest()[:8]
    return f"{base}_{digest}"


def project_id_for_name(project_name: str) -> str:
    """返回项目名称对应的稳定项目 ID，供 UI 做重名和覆盖检查。"""
    return _project_id(project_name)


def _project_dir(project_id: str) -> Path:
    if "/" in project_id or "\\" in project_id or ".." in project_id:
        raise ValueError("非法项目 ID")
    return _projects_dir() / project_id


def _project_metadata(project_id: str, project_name: str, state: dict[str, Any]) -> dict[str, Any]:
    df = state.get("df_unified")
    year_map = state.get("year_map") or {}
    years = sorted(int(y) for y in year_map.keys()) if year_map else []
    row_count = int(len(df)) if df is not None else 0
    voucher_count = int(df["凭证编号"].nunique()) if df is not None and "凭证编号" in df.columns else 0

    return {
        "project_id": project_id,
        "project_name": project_name,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "current_step": int(state.get("current_step", 0) or 0),
        "years": years,
        "row_count": row_count,
        "voucher_count": voucher_count,
        "has_profiles": bool(state.get("profiles")),
        "has_rules_config": bool(state.get("rules_config")),
        "has_rule_results": bool(state.get("rule_results")),
        "has_report": bool(state.get("report_path")),
    }


def list_projects() -> list[dict[str, Any]]:
    """列出已保存的项目记忆，按更新时间倒序。"""
    projects_dir = _projects_dir()
    if not projects_dir.exists():
        return []

    projects: list[dict[str, Any]] = []
    for metadata_path in projects_dir.glob("*/metadata.json"):
        try:
            projects.append(json.loads(metadata_path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return sorted(projects, key=lambda p: p.get("updated_at", ""), reverse=True)


def save_project_state(project_name: str, state: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    """保存项目状态，返回项目元数据。不会保存 API Key。"""
    clean_name = project_name.strip()
    if not clean_name:
        raise ValueError("项目名称不能为空")

    project_id = project_id.strip() if project_id else _project_id(clean_name)
    project_dir = _project_dir(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)
    lock_path = _project_lock_path(project_id)

    with file_lock(lock_path, exclusive=True):
        payload = dict(state)
        payload.pop("_api_key", None)
        payload["engagement_name"] = clean_name

        # 先写临时文件，再原子 rename，防止写入中断导致文件截断
        state_path = project_dir / "state.pkl.gz"
        tmp_path = project_dir / "state.pkl.gz.tmp"
        with gzip.open(tmp_path, "wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
        tmp_path.replace(state_path)

        metadata = _project_metadata(project_id, clean_name, payload)
        (project_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        try:
            state_path.chmod(0o600)
            (project_dir / "metadata.json").chmod(0o600)
        except Exception:
            pass
        return metadata


def load_project_state(project_id: str) -> dict[str, Any]:
    """读取项目状态。只应加载本工具自己保存的本地项目缓存。"""
    project_dir = _project_dir(project_id)
    state_path = project_dir / "state.pkl.gz"
    tmp_path = project_dir / "state.pkl.gz.tmp"
    lock_path = _project_lock_path(project_id)

    with file_lock(lock_path, exclusive=False):
        if not state_path.exists() and not tmp_path.exists():
            raise FileNotFoundError(f"项目缓存不存在：{project_id}")

        state = None
        errors = []

        # 尝试主文件
        if state_path.exists():
            try:
                with gzip.open(state_path, "rb") as f:
                    state = pickle.load(f)
            except Exception as e:
                errors.append(f"主文件: {e}")

        # 回退到临时文件
        if state is None and tmp_path.exists():
            try:
                with gzip.open(tmp_path, "rb") as f:
                    state = pickle.load(f)
                # 用临时文件恢复主文件
                tmp_path.replace(state_path)
            except Exception as e:
                errors.append(f"临时文件: {e}")

        if state is None:
            raise RuntimeError(
                f"项目缓存读取失败：{project_id}。{'；'.join(errors)}。"
                "可尝试重新保存当前项目以覆盖损坏的缓存。"
            )

        metadata_path = project_dir / "metadata.json"
        metadata = {}
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

        return {
            "metadata": metadata,
            "state": state,
        }


def delete_project_state(project_id: str) -> bool:
    """删除本地项目缓存。"""
    project_dir = _project_dir(project_id)
    if not project_dir.exists():
        return False
    with file_lock(_project_lock_path(project_id), exclusive=True):
        shutil.rmtree(project_dir)
    return True
