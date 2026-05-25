# 序时账审计分析平台

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/streamlit-1.35+-red.svg)](https://streamlit.io/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

面向**多年序时账数据**的审计辅助分析工具。支持上传 SAP 等 ERP 系统导出的总账明细，自动识别年份、生成统计画像、执行规则抽样，并借助 LLM 对疑点凭证做辅助核实。

> ⚠️ **定位声明**：本工具是审计师的辅助分析手段，**不替代审计判断，不自动形成审计结论**。最终判断仍需结合凭证原件、合同、对账单等证据链由人工完成。

---

## 功能概览

- **数据摄入** — 支持单/多 Excel 文件上传，自动识别年份，统一 SAP 列名
- **统计画像** — 按年度生成收入成本结构、对手方集中度、用户行为等画像
- **跨年稽核** — 年末突击、1 月红冲、跨年预提未结转等跨期异常检测
- **规则引擎** — 12 条审计核查规则，阈值由 LLM 根据账套画像动态校准
- **LLM 辅助核实** — 对 Top 50 疑点凭证逐条判断，给出风险级别和核查建议
- **可视化报告** — Plotly 交互图表 + Excel 抽样清单输出

---

## 快速开始

### 环境要求

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) 包管理器

### 安装运行

```bash
# 安装依赖
uv sync

# 配置 LLM API Key（任选一种环境变量）
export DEEPSEEK_API_KEY="sk-your-key"  # 或 OPENAI_API_KEY / LLM_API_KEY

# 启动
uv run streamlit run app.py
```

浏览器访问 `http://127.0.0.1:8505`，上传序时账 Excel 文件即可开始。

### macOS 快捷启动

双击 `启动.command` 即可自动同步依赖并启动服务，双击 `关闭.command` 停止。

---

## 审计规则列表

| # | 规则 | 说明 |
|---|------|------|
| 1 | 化整为零 | 短期内对同一对手方多笔小额付款，疑似规避审批额度 |
| 2 | 大额异常 | 整数金额、重复大额、节假日/周末异常过账 |
| 3 | 手工凭证 | 人工录入 + 损益科目 + 月末/年末时点 |
| 4 | 计提异常 | 预提/计提后长期未冲销，或单人独占计提 |
| 5 | 年末突击 | 12 月收入/费用相比前 11 月月均异常跳增 |
| 6 | 融资性贸易 | 无商业实质的空转贸易，虚增营收/套取资金 |
| 7 | 跨年预提 | 年末计提在次年 Q1 冲回覆盖率异常 |
| 8 | 跨年收入波动 | 12 月收入跳增与次年 1 月红字冲回关联 |
| 9 | 资金池划转 | 关联方资金归集、同名划转的大额波动 |
| 10 | 用户集中度 | 单一用户过账占比过高，职责分离失效 |
| 11 | 冲销反记账 | 反记账/红字凭证频率和金额异常 |
| 12 | 敏感费用 | 咨询费、招待费等合规敏感科目的穿透扫描 |

所有规则阈值由 **LLM 规则校准模块** 根据上传账套的实际画像动态生成，每条规则附带 `rationale` 说明阈值依据。

---

## 项目结构

```
app.py                      # Streamlit 主入口（5 步工作流）
pyproject.toml              # 项目依赖（uv 管理）
modules/
  ingestion.py              # 文件加载 + 年份自动识别
  profiler.py               # 单年统计画像
  cross_year.py             # 跨年交叉稽核
  rule_generator.py         # LLM 规则校准
  rule_engine.py            # 规则执行引擎
  llm_verifier.py           # LLM 逐凭证核实
  reporter.py               # Excel 报告输出
  knowledge_base.py         # 经验库读写
  secret_store.py           # API Key 安全存储（钥匙串/文件）
components/
  charts.py                 # Plotly 可视化组件
  sidebar.py                # 侧边栏步骤导航
config/
  constants.py              # LLM 配置常量
  accounts.py               # 科目分类映射
```

---

## 配置

### LLM 配置

- 默认模型：`deepseek-chat`，支持任意 OpenAI 兼容 API
- 可在侧边栏切换模型和 Base URL（如 `https://api.openai.com/v1`）
- API Key 优先级：环境变量 `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` / `LLM_API_KEY` > 会话输入 > 本机钥匙串（macOS）

### 数据格式

支持 SAP 标准序时账列名：

```
凭证编号 | 过账日期 | 凭证类型 | 文本 | 总账科目 | 总账科目：长文本 |
借/贷标识 | 凭证货币价值 | 供应商编号 | 供应商科目：名称 1 |
客户 | 客户科目：姓名 1 | 用户名 | 过账期间 | 录入时间
```

借贷标识：`S` = 借方，`H` = 贷方（SAP 标准）  
Period 13 = 年末关闭调整期，归入当年并单独标记

### 输出样本量

默认最多输出 50 个凭证（可在侧边栏调整），按优先级降序截断。

---

## 常见问题

### `uv sync` 报错 "Operation not permitted" 或 "Permission denied"

uv 缓存目录权限异常所致。按顺序尝试：

```bash
# 方案一：清除 uv 缓存后重试
rm -rf ~/.cache/uv/
uv sync

# 方案二：跳过缓存直接安装
uv sync --no-cache
```

> 双击 `启动.command` 已内置以上降级逻辑，会自动处理此类错误。

### 端口被占用

默认端口 8505。如需更换：

```bash
STREAMLIT_PORT=8506 uv run streamlit run app.py
```

---

## 许可

[MIT](LICENSE)

---

## 免责声明

本工具基于规则引擎和 LLM 辅助分析，输出结果**仅供参考**，不构成审计意见或法律建议。使用者应结合专业判断和完整证据链做出最终结论。
