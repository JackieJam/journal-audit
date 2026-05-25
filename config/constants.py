"""
全局常量：规则顺序、元信息、参数中文标签、LLM 默认配置。
"""

from __future__ import annotations

# ── 规则执行顺序 ──

RULE_ORDER = [
    "splitting",
    "large_amount",
    "manual_entry",
    "accrual_anomaly",
    "yearend_surge",
    "financing_trade",
    "cross_year_accrual",
    "cross_year_revenue",
    "cash_pool",
    "user_concentration",
    "reversal_pattern",
    "sensitive_fees",
]

# ── 规则元信息（标题 + 审计目的）──

RULE_META: dict[str, dict[str, str]] = {
    "splitting": {
        "title": "化整为零",
        "purpose": "识别把一笔大额付款拆成多笔相近金额、借此规避审批或掩盖集中付款的模式。",
    },
    "large_amount": {
        "title": "大额异常",
        "purpose": "识别大额整数、大额重复交易、异常周末/节假日过账和凌晨录入等高风险操作。",
    },
    "manual_entry": {
        "title": "手工凭证",
        "purpose": "识别手工干预程度高、且更可能触达损益和月末/年末调账的凭证。",
    },
    "accrual_anomaly": {
        "title": "计提异常",
        "purpose": "识别非常规计提、用户集中计提和长期未冲回的悬空预提。",
    },
    "yearend_surge": {
        "title": "年末突击确认",
        "purpose": "识别收入在年末异常冲高、可能影响截止测试结论的月份。",
    },
    "financing_trade": {
        "title": "融资性贸易",
        "purpose": "把相近期间的收入凭证和成本凭证组成疑点候选，复核是否存在贸易形式包装的资金通道。",
    },
    "cross_year_accrual": {
        "title": "跨年预提",
        "purpose": "识别跨年预提冲回不足、存在跨期悬挂的异常对象。",
    },
    "cross_year_revenue": {
        "title": "跨年收入波动",
        "purpose": "识别跨年层面年末收入偏高、收入确认前置的异常信号。",
    },
    "cash_pool": {
        "title": "资金池划转",
        "purpose": "识别同名划转、资金归集、上划下拨等可能对应资金占用的交易。",
    },
    "user_concentration": {
        "title": "用户集中度异常",
        "purpose": "识别过账权限过度集中、职责分离可能失效的用户。",
    },
    "reversal_pattern": {
        "title": "冲销反记账异常",
        "purpose": "识别高频冲销、大额冲销以及期后修饰类反记账操作。",
    },
    "sensitive_fees": {
        "title": "敏感费用筛查",
        "purpose": "识别咨询、代理、招待、旅游、捐赠、罚款等敏感费用及异常操作者。",
    },
}

# ── 规则参数中文标签 ──

PARAM_HELP = {
    "max_single_amount": "【化整为零】单笔金额上限。低于此金额且多笔合计达标时才触发。用于定义「化整」的单笔门槛。",
    "min_total": "【化整为零】多笔合计金额下限。窗口期内同一供应商多笔合计必须≥此值才触发。",
    "window_days": "观察的时间窗口（天）。在此天数内查找符合条件的多笔交易。",
    "min_txn_count": "最少交易笔数。同一供应商在窗口期内至少需达到此笔数才触发。",
    "burst_multiplier": "频次放大倍数。当日笔数超过该供应商日均笔数×此倍数时触发「集中爆发」子规则。",
    "round_number_threshold": "【大额异常】整数金额门槛。金额≥此值且为整数时触发。用于发现凑整/化整嫌疑。",
    "repeat_threshold": "【大额异常】重复大额门槛。同供应商在窗口内出现多笔≥此值的交易时触发。",
    "repeat_window_days": "【大额异常】重复观察窗口。在此天数内检测同一供应商的大额重复交易。",
    "repeat_min_count": "【大额异常】重复最少笔数。窗口内同供应商大额交易达到此数量才触发。",
    "holiday_min_amount": "【大额异常】节假日金额门槛。周末/节假日过账的凭证金额≥此值才标记（含过滤小额周末操作）。",
    "pnl_amount_threshold": "【手工凭证】损益科目金额门槛。手工凭证中涉及损益科目且金额≥此值时提高优先级。",
    "month_end_days": "月末观察天数。过账日期距离月末≤此天数的凭证标记为「月末/年末调整」。",
    "match_window_days": "冲回观察窗口。在此天数内查找计提对应的冲销/冲回凭证。",
    "amount_tolerance": "金额容差。冲销金额与计提金额的允许偏差率（0.10=±10%）。",
    "min_amount": "最低金额门槛。低于此金额的计提/费用不会被标记，过滤零星小额。",
    "multiplier": "放大倍数。关注月份的数值超过其他月份均值×此倍数时触发。",
    "months": "关注月份列表。指定需要重点检测的月份（如[12]表示年末突击确认）。",
    "margin_threshold": "毛利率阈值。组合毛利率≤此值时视为低毛利疑点组合（融资性贸易规则）。",
    "income_account_prefixes": "收入科目前缀列表。用于识别收入类科目（如6001、6051）。",
    "cost_account_prefixes": "成本科目前缀列表。用于识别成本类科目（如6401、6402）。",
    "min_revenue_amount": "最低收入金额。收入凭证金额≥此值才进入融资性贸易匹配候选。",
    "low_margin_threshold": "低毛利阈值。收入-成本组合毛利率≤此值时触发疑点预警。",
    "max_loss_rate": "最大亏损容忍率。组合亏损超过此比例时视为噪声过滤，避免极端异常干扰。",
    "min_match_score": "最低匹配得分。收入凭证和成本凭证的匹配度≥此分值时纳入疑点组合。",
    "max_candidate_groups": "最多候选组合数。融资性贸易规则输出的最大疑点组合数量上限。",
    "max_related_vouchers": "最多关联凭证数。每个收入凭证最多匹配的成本凭证数量。",
    "keywords": "关键词列表。用于文本匹配筛选（如「代垫」「资金池」「咨询费」等）。",
    "coverage_threshold": "覆盖率阈值。跨年预提冲销覆盖率<此值时视为悬空预提风险。",
    "dec_multiplier": "12月放大倍数。12月收入超过前11月均值×此倍数时触发年末收入确认前置风险。",
    "large_threshold": "大额门槛。凭证金额≥此值时触发大额风险标记。",
    "concentration_threshold": "集中度阈值。单个用户过账行数占比≥此值时触发职责分离失效风险。",
    "frequent_count": "频繁笔数阈值。同一用户冲销笔数≥此值时标记为频繁冲销用户。",
    "categories": "敏感费用分类定义。每个类别含关键词列表、排除词和金额阈值。",
    "baseline_multiplier": "异常用户放大倍数。用户敏感费用率>公司均值×此倍数时，该用户全部敏感费用凭证被标记。",
    "whitelist_keywords": "白名单关键词。命中这些关键词的凭证被自动过滤，不进入规则引擎。",
    "whitelist_voucher_types": "白名单凭证类型。如AA/AB/ZP等系统自动凭证类型，命中后过滤。",
    "max_sample_size": "样本量上限。最终输出的最大凭证数量，超出部分按优先级截断。",
}

PARAM_LABELS = {
    "max_single_amount": "单笔上限",
    "min_total": "合计门槛",
    "window_days": "观察窗口",
    "min_txn_count": "最少笔数",
    "burst_multiplier": "频次放大倍数",
    "round_number_threshold": "整数金额门槛",
    "repeat_threshold": "重复大额门槛",
    "repeat_window_days": "重复观察窗口",
    "repeat_min_count": "重复最少笔数",
    "holiday_min_amount": "节假日金额门槛",
    "pnl_amount_threshold": "损益金额门槛",
    "month_end_days": "月末观察天数",
    "match_window_days": "冲回观察窗口",
    "amount_tolerance": "金额容差",
    "min_amount": "最低金额门槛",
    "multiplier": "放大倍数",
    "months": "关注月份",
    "margin_threshold": "差异率阈值",
    "income_account_prefixes": "收入科目前缀",
    "cost_account_prefixes": "成本科目前缀",
    "min_revenue_amount": "最低收入金额",
    "low_margin_threshold": "低毛利阈值",
    "max_loss_rate": "最大亏损容忍",
    "min_match_score": "最低匹配得分",
    "max_candidate_groups": "最多候选组合",
    "max_related_vouchers": "最多关联凭证",
    "keywords": "关键词",
    "coverage_threshold": "覆盖率阈值",
    "dec_multiplier": "12月放大倍数",
    "large_threshold": "大额门槛",
    "concentration_threshold": "集中度阈值",
    "frequent_count": "频繁笔数阈值",
    "categories": "敏感费用分类",
    "baseline_multiplier": "异常用户放大倍数",
    "whitelist_keywords": "白名单关键词",
    "whitelist_voucher_types": "白名单凭证类型",
    "max_sample_size": "样本上限",
}

# ── LLM 默认配置 ──

DEFAULT_LLM_CONFIG: dict[str, str] = {
    "profile_id": "",
    "profile_name": "默认",
    "model": "deepseek-chat",
    "base_url": "https://api.deepseek.com",
    "key_source": "env_or_keychain",
    "keychain_account": "default",
}

# ── Session State 版本号 ──

PROFILES_VERSION = 1
FINANCIALS_VERSION = 1
AUDIT_CACHE_VERSION = 1

# ── 项目记忆持久化键 ──

PROJECT_MEMORY_KEYS = [
    "df_unified",
    "year_map",
    "year_summary",
    "profiles",
    "profiles_version",
    "cross_year_findings",
    "financials",
    "financials_version",
    "audit_llm_analysis",
    "candidate_pool",
    "llm_config",
    "rules_config",
    "rule_results",
    "llm_judgments",
    "report_path",
    "report_stats",
    "engagement_name",
    "loaded_file_signature",
]
