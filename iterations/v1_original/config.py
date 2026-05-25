"""
序时账审计抽样工具 — 配置文件
阈值常量、白名单、关键人员、科目映射
"""

import os

# ============================================================
# 关键人员（SAP 用户名）— 实现时填入真实 ID
# ============================================================
KEY_PERSONNEL: list[str] = [
    "01450077",  # 林翠池（占位，待确认）
]

# ============================================================
# 白名单（所有规则执行前过滤）
# ============================================================
WHITELIST_TEXT_KEYWORDS: list[str] = [
    "同名划转",
    "资金池",
    "工资",
    "个人所得税",
    "折旧",
    "摊销",
    "社保",
    "公积金",
    "利息收入",
    "利息支出",
    "银行手续费",
]

WHITELIST_VOUCHER_TYPES: list[str] = [
    "AA",  # 折旧自动凭证
    "AB",  # 摊销自动凭证
]

WHITELIST_ACCOUNT_PREFIXES: list[str] = [
    "2221",  # 代扣个税科目
]

# ============================================================
# SAP 科目分类（科目号前缀）
# ============================================================
ACCOUNT_CATEGORIES: dict[str, list[str]] = {
    "收入": ["6001", "6051"],
    "成本": ["6401"],
    "预提": ["2171", "2261"],
    "应付账款": ["2202"],
    "应收账款": ["1122"],
    "银行存款": ["1002"],
    "损益科目": ["6", "5"],  # 前缀匹配，6=收入费用，5=成本费用
}

# ============================================================
# 融资性贸易关键词
# ============================================================
FINANCING_TRADE_KEYWORDS: list[str] = [
    "代垫",
    "代采购",
    "委托贸易",
    "贸易融资",
    "保理",
    "买卖差价",
    "过路费",
]

# ============================================================
# 规则阈值
# ============================================================

# Rule 1: 融资性贸易
FINANCING_MARGIN_THRESHOLD = 0.5       # 毛利率异常阈值
FINANCING_TRADE_WINDOW_DAYS = 30       # 供应商往来观察窗口（天）

# Rule 2: 预提冲销
ACCRUAL_MATCH_WINDOW_DAYS = 90         # 冲销配对窗口（天）
ACCRUAL_AMOUNT_TOLERANCE = 0.05        # 金额偏差容忍度（5%）
ACCRUAL_FREQUENT_COUNT = 4             # 年内频繁预提冲销次数

# Rule 3: 化整为零
SPLITTING_MIN_LINES = 3                # 同组最少笔数
SPLITTING_MAX_SINGLE_AMOUNT = 50_000   # 单笔上限
SPLITTING_MIN_TOTAL = 200_000          # 合计下限
SPLITTING_WINDOW_DAYS = 7              # 7 天窗口
SPLITTING_WINDOW_MIN_LINES = 5         # 窗口内最少笔数
SPLITTING_AMOUNT_VARIANCE = 0.10       # 金额差异容忍度（10%）

# Rule 4: 大额异常
LARGE_AMOUNT_THRESHOLD = 5_000_000      # 大额整数阈值
LARGE_REPEAT_THRESHOLD = 50_000_000     # 大额重复阈值
LARGE_REPEAT_MIN_COUNT = 2              # 30天内最少次数
LARGE_REPEAT_WINDOW_DAYS = 30           # 观察窗口

# Rule 5: 手工凭证
MANUAL_PNL_AMOUNT_THRESHOLD = 100_000   # 损益科目金额阈值
MANUAL_MONTH_END_DAYS = 5              # 月末最后 N 天
MANUAL_EXCLUDE_VOUCHER_TYPES = ["AA", "AB", "ZP"]  # 排除系统自动凭证

# Rule 6: 年末突击
YEAREND_SURGE_MULTIPLIER = 2.0         # 12月 vs 前11月月均倍数

# ============================================================
# LLM 配置（DeepSeek，兼容 OpenAI 格式）
# ============================================================
LLM_BASE_URL = "https://api.deepseek.com"
LLM_MODEL = "deepseek-chat"
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")  # 可被环境变量 DEEPSEEK_API_KEY 覆盖
LLM_BATCH_SIZE = 15                    # 每次 API 调用的凭证组数
LLM_MAX_RETRIES = 2                    # API 调用重试次数
