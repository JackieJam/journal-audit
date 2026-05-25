# 序时账审计分析工具

## 项目定位
Streamlit 多年序时账审计分析平台。支持单/多文件上传，自动识别年份，输出校准规则 + 疑点样本 + 可视化报告，并将有效规则沉淀到全局经验库。

## 运行方式
```bash
uv run streamlit run app.py
```

## 文件结构
```
app.py                      # Streamlit 主入口（5步工作流）
pyproject.toml              # 依赖（uv 管理）
modules/
  ingestion.py              # 文件加载 + 年份自动识别
  profiler.py               # 单体统计画像（per year）
  cross_year.py             # 跨年交叉稽核
  rule_generator.py         # LLM 规则校准（读 profile + 经验库）
  rule_engine.py            # 规则执行（从 rules_config 读参数）
  llm_verifier.py           # LLM 逐凭证核实
  reporter.py               # Excel 输出
  knowledge_base.py         # 经验库读写（~/.audit_tool/）
components/
  charts.py                 # Plotly 图表组件
  sidebar.py                # 侧边栏步骤导航
config/
  rule_templates.json       # 规则类型模板（结构定义）
```

## 核心约定

### 数据字段（SAP 序时账标准列名）
关键列：`凭证编号` `过账日期` `凭证类型` `文本` `总账科目` `总账科目：长文本`
`借/贷标识` `凭证货币价值` `供应商编号` `供应商科目：名称 1`
`客户` `客户科目：姓名 1` `用户名` `过账期间` `录入时间`

借/贷标识：`S` = 借方，`H` = 贷方（SAP 标准）
SAP Period 13 = 年末关闭调整期，归入当年，在分析中单独标记。

### Session State 键名（Streamlit）
- `st.session_state.df_unified`：合并后的全部年份 DataFrame（含 `_year` 列）
- `st.session_state.year_map`：`{year: df}` 按年分片
- `st.session_state.profiles`：`{year: profile_dict}`
- `st.session_state.cross_year_findings`：跨年稽核结果列表
- `st.session_state.rules_config`：校准后的规则配置 dict
- `st.session_state.rule_hits`：规则命中结果列表
- `st.session_state.llm_judgments`：LLM 核实结果 dict
- `st.session_state.current_step`：当前步骤 1-5

### 经验库路径
`~/.audit_tool/rule_library.json`
模块 `knowledge_base.py` 负责所有读写，其他模块不直接操作该文件。

### LLM 配置
- 默认模型：`deepseek-chat`（兼容 OpenAI SDK）
- API Key 优先级：环境变量 `DEEPSEEK_API_KEY` > Streamlit 侧边栏输入
- Key 不写入任何文件

### 规则配置格式（rules_config.json / session_state）
每条规则必须包含 `enabled`、`rationale` 字段，其余为规则特定参数。
rationale 是可审计性的核心，必须说明"为什么这个阈值"。

### 输出样本量控制
默认最多输出 50 个凭证（可在侧边栏调整），按优先级降序截断。
避免输出几千行让审计师无从下手。

## 禁止事项
- 不在代码里硬编码任何阈值（全部从 rules_config 读）
- 不在代码里硬编码 API Key
- 不直接操作 `~/.audit_tool/` 目录（走 knowledge_base.py）
- 不跳过 LLM 核实就把规则命中直接输出（宁可 fallback 保留）


<claude-mem-context>
# Memory Context

# [15_journal-audit_序时账分析抽样] recent context, 2026-05-13 1:51pm GMT+8

No previous sessions found.
</claude-mem-context>