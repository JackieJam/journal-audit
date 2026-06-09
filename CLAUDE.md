# 序时账审计分析工具

## 项目定位
Streamlit 多年序时账审计分析平台。支持单/多文件上传，自动识别年份，输出校准规则 + 疑点样本 + 可视化报告，并将有效规则沉淀到全局经验库。

## 运行方式
```bash
uv run streamlit run app.py
```

## 文件结构
```
app.py                      # Streamlit 主入口（segmented_control 4 页签：上传数据/序时账分析/规则管理/样本抽取）
                            # ~720 行：4 个页签均已抽到 components/tabs/，app.py 保留 session/helper 定义并注入各页签
                            # 各页签 render 函数通过 **helpers 注入 app.py 私有 helper（仍在 app.py 命名空间执行）
pyproject.toml              # 依赖（uv 管理）
modules/
  ingestion.py              # 文件加载 + 年份自动识别 + 分层列名匹配（精确/别名/子串/rapidfuzz 模糊 + 经验库学习项注入，带置信度与冲突消解）
  column_check.py           # 列字段守卫：缺失必要字段则降级跳过并给出可审计提示
  data_columns.py           # 共享分析派生列补充（add_analysis_columns）
  account_classifier.py     # 基于科目名称的自动分类器（损益类 + 资产负债类，含 BALANCE_SHEET_CATEGORIES/SIDE）
  profiler.py               # 单体统计画像（per year，@st.cache_data）
  cross_year.py             # 跨年交叉稽核（七类异常，@st.cache_data，键含分类覆盖签名+阈值签名）
                            # 预提/收入两类检测阈值已 config 化（coverage_threshold/dec_multiplier），由 rules_config 传入并参与缓存键
                            # 这两个阈值不参与 LLM 校准（见 rule_generator.pin_cross_year_thresholds），避免「发现→校准→发现」反馈环
  visual_analysis.py        # Step 2 审计可视化数据准备（聚合视图）
  rule_generator.py         # LLM 规则校准（读 profile + 经验库）
  rule_engine.py            # 规则执行（从 rules_config 读参数，@st.cache_data）
  llm_verifier.py           # LLM 逐凭证核实
  audit_llm_analysis.py     # 审计可视化 LLM 初步解析（仅发送聚合数据，不发 Key/明细，带 fallback）
  llm_quota.py              # LLM 调用配额跟踪（按 namespace）
  reporter.py               # Excel 样本清单输出
  candidate_pool.py         # 疑点库数据层（候选/人工直入分组）
  knowledge_base.py         # 经验库 + 项目状态 + LLM profile 持久化（~/.audit_tool/，含损坏文件告警）
  secret_store.py           # 本机/服务器密钥存储（keychain）
  locking.py                # 跨平台文件锁（并发写保护）
  runtime_context.py        # 运行时上下文 / 按用户隔离的存储根路径
  json_utils.py             # 统一 JSON 解析（处理 LLM 返回的 markdown 代码块 + 正则兜底）
  formatting.py             # 纯格式化 helper（金额/百分比/倍数/年份/HTML 转义）
  rule_text.py              # 规则文本/条件/变更/计数 helper（规则展示用）
components/
  charts.py                 # Plotly 图表组件
  sidebar.py                # 侧边栏
  styles.py                 # 全局 CSS 注入（inject_global_css，从 app.py 抽离的纯样式）
  exports.py                # Excel 导出层（DataFrame→字节流 + 图表标题带下载按钮）
  cross_year_view.py        # 跨年异常/费用结构/经验库规则的展示层（纯渲染，无 session）
  chart_selection.py        # 图表/表格点选事件解析（纯函数）
  candidate_actions.py      # 疑点库详情/动作 UI（候选凭证详情、添加 popover、行样式）
  llm_orchestration.py      # LLM 推荐编排（推荐→明细数据路径 + step-2 有状态 helper）
  tabs/
    upload.py               # Tab 0：上传数据（已抽离）
    rules.py                # Tab 2：规则管理 增删改查（已抽离）
    sampling.py             # Tab 3：样本抽取（规则筛选 + 抽样 + Excel 报告，已抽离）
    analysis/               # Tab 1：序时账分析（已抽离为子包，render_analysis_tab 顶层只做守卫+画像生成+分发）
      tab.py                #   页签入口 render_analysis_tab（守卫/财务画像生成/顶层 3 子页签分发）
      _context.py           #   AnalysisContext：setup 阶段共享上下文 + helpers 字典，传给各内层子渲染
      suspect_filter.py     #   可疑样本库筛选（年份/口径/KPI setup + 7 个内层 sub-tab 分发）
      income_cost.py        #   内层：收入成本    expense.py 内层：费用
      working_capital.py    #   内层：暂估往来 + render_working_capital_main（被 app.py 包装注入）
      balance_sheet.py      #   内层：资产负债（通用「科目类别月度变动」引擎，只做发生额/净变动，非余额表）
      adjustment.py         #   内层：调账冲销 + render_adjustment_main（被 app.py 包装注入）
      cross_year.py         #   内层：跨年交叉稽核    profile.py 内层：统计画像
      overview.py           #   顶层：财务概况    pool.py 顶层：疑点库管理
config/
  accounts.py               # 科目体系与分类常量（科目前缀/凭证类型/费用分类/调整关键词）
  constants.py              # 全局常量（规则顺序、参数中文标签、LLM 默认配置）
  default_rules.json        # 默认规则配置（rules_config 基线）
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

### 经验库路径
`~/.audit_tool/`（按用户隔离，路径由 `runtime_context.storage_root()` 决定）
- `rule_library.json`：跨项目沉淀的有效规则
- `column_aliases.json`：列名学习库——用户每次确认的「源列名→标准列」映射，让列名匹配越用越聪明（频次累计，冲突取高频）
- `llm_profiles.json`：本机保存的 LLM 方案（不含 Key 明文，权限 0600）
- `projects/<id>/`：各审计项目的持久化状态 + 自动保存

模块 `knowledge_base.py` 负责所有读写，其他模块不直接操作这些文件。
JSON 文件解析失败时不静默吞错：记录日志 + 隔离备份为 `*.corrupt-<时间戳>` + 通过 `consume_load_warnings()` 在 UI 暴露。

### LLM 配置
- 默认模型：`deepseek-chat`（兼容 OpenAI SDK，支持任意兼容 API）
- API Key 优先级：环境变量 `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` / `LLM_API_KEY` > Streamlit 侧边栏输入
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
