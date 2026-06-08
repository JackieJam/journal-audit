"""
经验库模块：跨项目持久化有效规则，存储在 ~/.audit_tool/rule_library.json。
所有经验库读写操作通过本模块，其他模块不直接操作文件。
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import pickle
import re
import shutil
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from modules.locking import file_lock
from modules.runtime_context import storage_root

logger = logging.getLogger(__name__)

# 经验库/配置文件加载异常的可见信号：损坏文件不再被静默吞掉。
# app 层可调用 consume_load_warnings() 取出并通过 st.warning 暴露给审计师。
_LOAD_WARNINGS: list[str] = []


def consume_load_warnings() -> list[str]:
    """取出并清空累积的加载告警（UI 用一次性消费）。"""
    global _LOAD_WARNINGS
    warnings, _LOAD_WARNINGS = _LOAD_WARNINGS, []
    return warnings


def _read_json_file(path: Path, default: Any) -> Any:
    """安全读取 JSON 文件。

    - 文件不存在：属正常情况，静默返回 default。
    - 文件存在但解析失败：视为数据损坏，记录日志 + 隔离备份 + 登记可见告警，
      再返回 default。绝不静默丢弃，符合「风险可见」原则。
    """
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        quarantine = path.with_name(
            f"{path.name}.corrupt-{datetime.now():%Y%m%d%H%M%S}"
        )
        try:
            shutil.copy2(path, quarantine)
            backup_note = f"，已备份至 {quarantine.name}"
        except Exception:
            backup_note = "（备份失败）"
        msg = f"配置文件 {path.name} 解析失败：{exc}{backup_note}"
        logger.warning("knowledge_base load error: %s", msg)
        _LOAD_WARNINGS.append(msg)
        return default


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
    data = _read_json_file(_llm_profiles_path(), [])
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
        profile_id = str(profile.get("profile_id", "")).strip()
        safe_profiles.append({
            "profile_id": profile_id,
            "profile_name": str(profile.get("profile_name", "")).strip(),
            "base_url": str(profile.get("base_url", "")).strip(),
            "model": str(profile.get("model", "")).strip(),
            "keychain_account": str(profile.get("keychain_account", "")).strip() or profile_id or "default",
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
            # 钥匙串账户名默认绑定方案自身 id，做到「一套方案一把钥匙」。
            "keychain_account": str(profile.get("keychain_account", "")).strip() or profile_id,
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


# ── 列名学习库：沉淀用户确认的「源列名 → 标准列」，让匹配越用越聪明 ──
# 存 ~/.audit_tool/column_aliases.json。key 为归一化后的源列名（聚合空格/标点变体），
# value 记录候选标准列及确认频次，冲突时高频者胜出。


def _column_aliases_path() -> Path:
    return _root() / "column_aliases.json"


def _column_aliases_lock_path() -> Path:
    return _root() / ".column_aliases.lock"


def _norm_col(text: str) -> str:
    """源列名归一化：去空白/标点 + 小写。

    必须与 ingestion._normalize 保持一致，否则学过的别名查不回来；
    由 test_normalization_matches_ingestion 跨模块锁死。
    """
    return "".join(ch for ch in str(text).lower() if ch.isalnum())


def _load_column_aliases() -> dict[str, Any]:
    data = _read_json_file(_column_aliases_path(), {})
    if not isinstance(data, dict):
        return {}
    return data


def _save_column_aliases(data: dict[str, Any]) -> None:
    path = _column_aliases_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)
    try:
        path.chmod(0o600)
    except Exception:
        pass


def record_column_mappings(std_to_source: dict[str, str]) -> int:
    """沉淀用户确认的列映射（标准列 -> 源列），返回有效记录条数。

    跳过：源列为空、源列归一化后等于标准名（精确命中无沉淀价值）。
    重复确认累加频次；同一源列映射到不同标准列时各自计数，读取时取高频。
    """
    recorded = 0
    today = str(date.today())
    with file_lock(_column_aliases_lock_path(), exclusive=True):
        data = _load_column_aliases()
        for std_name, source in std_to_source.items():
            std_name = str(std_name).strip()
            source = str(source or "").strip()
            if not std_name or not source:
                continue
            norm = _norm_col(source)
            if not norm or norm == _norm_col(std_name):
                continue
            entry = data.get(norm)
            if not isinstance(entry, dict):
                entry = {"example": source, "candidates": {}}
                data[norm] = entry
            entry["example"] = source
            candidates = entry.setdefault("candidates", {})
            cand = candidates.get(std_name)
            if not isinstance(cand, dict):
                cand = {"count": 0, "last_used": today}
                candidates[std_name] = cand
            cand["count"] = int(cand.get("count", 0)) + 1
            cand["last_used"] = today
            recorded += 1
        if recorded:
            _save_column_aliases(data)
    return recorded


def learned_column_aliases() -> dict[str, str]:
    """返回 {归一化源列名: 标准列名}，每个源列取确认频次最高的标准列（并列取最近）。

    供 ingestion 匹配器作为高置信层注入；读取失败时返回空 dict（不阻断上传）。
    """
    data = _load_column_aliases()
    out: dict[str, str] = {}
    for norm, entry in data.items():
        if not isinstance(entry, dict):
            continue
        candidates = entry.get("candidates", {})
        if not isinstance(candidates, dict) or not candidates:
            continue
        best = max(
            candidates.items(),
            key=lambda kv: (
                int(kv[1].get("count", 0)) if isinstance(kv[1], dict) else 0,
                kv[1].get("last_used", "") if isinstance(kv[1], dict) else "",
            ),
        )
        out[str(norm)] = best[0]
    return out


def _load() -> list[dict]:
    data = _read_json_file(_library_path(), [])
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


# 重数据键：体积大、gzip+pickle 序列化成本高，单独存 data.pkl.gz；
# 仅在内容签名变化或显式声明数据已变时才重写，避免每次 autosave 都压缩整个 DataFrame。
DATA_STATE_KEYS: tuple[str, ...] = ("df_unified", "year_map")


def _data_signature(state: dict[str, Any]) -> str:
    """对重数据计算廉价结构签名（行数 / 列 / dtype / 分年规模）。

    刻意只看结构而非逐格内容：autosave 路径根本不触碰 df，结构不变即可安全跳过重写；
    会改写 df 内容的路径（上传、分类覆盖）由调用方显式传 ``data_changed=True`` 兜底，
    保证数据不丢。
    """
    parts: list[str] = []
    df = state.get("df_unified")
    if df is None:
        parts.append("df:none")
    else:
        try:
            cols = ",".join(map(str, df.columns))
            dtypes = ",".join(str(t) for t in df.dtypes)
            parts.append(f"df:{len(df)}:{cols}:{dtypes}")
        except Exception:
            parts.append(f"df:{len(df)}")
    year_map = state.get("year_map") or {}
    try:
        parts.append("ym:" + ",".join(f"{k}={len(v)}" for k, v in sorted(year_map.items())))
    except Exception:
        parts.append(f"ym:{len(year_map)}")
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def _atomic_pickle_gz(path: Path, obj: Any) -> None:
    """gzip+pickle 原子写入：先写临时文件再 rename，避免写入中断导致文件截断。"""
    tmp_path = path.with_name(path.name + ".tmp")
    with gzip.open(tmp_path, "wb") as f:
        pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)
    tmp_path.replace(path)


def _read_pickle_gz(main_path: Path, tmp_path: Path) -> tuple[Any, list[str]]:
    """读取 gzip+pickle，主文件损坏时回退临时文件并修复。返回 (对象 | None, 错误列表)。"""
    obj = None
    errors: list[str] = []
    if main_path.exists():
        try:
            with gzip.open(main_path, "rb") as f:
                obj = pickle.load(f)
        except Exception as e:
            errors.append(f"{main_path.name}: {e}")
    if obj is None and tmp_path.exists():
        try:
            with gzip.open(tmp_path, "rb") as f:
                obj = pickle.load(f)
            tmp_path.replace(main_path)  # 用临时文件恢复主文件
        except Exception as e:
            errors.append(f"{tmp_path.name}: {e}")
    return obj, errors


def save_project_state(
    project_name: str,
    state: dict[str, Any],
    project_id: str | None = None,
    *,
    data_changed: bool = False,
) -> dict[str, Any]:
    """保存项目状态，返回项目元数据。不会保存 API Key。

    重数据（DATA_STATE_KEYS）与轻状态拆成两个文件：轻状态每次都写（快），
    重数据仅在 ``data_changed=True``、签名变化或文件缺失时才重写——让高频 autosave
    不再每次压缩整个 DataFrame。
    """
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

        # 拆分：重数据 vs 轻状态（新格式 state.pkl.gz 只含轻状态）
        data_part = {k: payload.pop(k) for k in DATA_STATE_KEYS if k in payload}
        light_part = payload

        light_path = project_dir / "state.pkl.gz"
        data_path = project_dir / "data.pkl.gz"
        meta_path = project_dir / "metadata.json"

        signature = _data_signature(state)
        prev_signature = ""
        if meta_path.exists():
            try:
                prev_signature = json.loads(meta_path.read_text(encoding="utf-8")).get("data_signature", "")
            except Exception:
                prev_signature = ""
        should_write_data = data_changed or not data_path.exists() or signature != prev_signature

        _atomic_pickle_gz(light_path, light_part)
        if should_write_data:
            _atomic_pickle_gz(data_path, data_part)

        metadata = _project_metadata(project_id, clean_name, state)
        metadata["data_signature"] = signature
        meta_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        for p in (light_path, data_path, meta_path):
            try:
                if p.exists():
                    p.chmod(0o600)
            except Exception:
                pass
        return metadata


def load_project_state(project_id: str) -> dict[str, Any]:
    """读取项目状态。只应加载本工具自己保存的本地项目缓存。

    合并轻状态（state.pkl.gz）与重数据（data.pkl.gz）。兼容历史的单文件全量格式：
    旧 state.pkl.gz 自带 df 而无 data.pkl.gz，合并后仍是完整状态，下次保存自动升级为拆分格式。
    """
    project_dir = _project_dir(project_id)
    light_path = project_dir / "state.pkl.gz"
    light_tmp = project_dir / "state.pkl.gz.tmp"
    data_path = project_dir / "data.pkl.gz"
    data_tmp = project_dir / "data.pkl.gz.tmp"
    lock_path = _project_lock_path(project_id)

    with file_lock(lock_path, exclusive=False):
        if not light_path.exists() and not light_tmp.exists():
            raise FileNotFoundError(f"项目缓存不存在：{project_id}")

        base, errors = _read_pickle_gz(light_path, light_tmp)
        if base is None:
            raise RuntimeError(
                f"项目缓存读取失败：{project_id}。{'；'.join(errors)}。"
                "可尝试重新保存当前项目以覆盖损坏的缓存。"
            )

        data: dict[str, Any] = {}
        if data_path.exists() or data_tmp.exists():
            data_obj, data_errors = _read_pickle_gz(data_path, data_tmp)
            if data_obj is None:
                raise RuntimeError(
                    f"项目重数据读取失败：{project_id}。{'；'.join(data_errors)}。"
                    "可尝试重新保存当前项目以覆盖损坏的缓存。"
                )
            data = data_obj if isinstance(data_obj, dict) else {}

        # 重数据为权威来源，覆盖轻状态中可能存在的历史同名键
        state = {**base, **data}

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
