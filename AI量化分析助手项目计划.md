# AI量化分析助手项目计划（OpenClaw + Qwen2.5 + A股工具链）

更新时间：2026-03-06  
运行环境：Ubuntu 22 / 64G RAM / RTX 4060 / Python 3.10+（建议 3.12）

## 0. 当前进度（截至 2026-03-06）

- M1（第1周）：已完成
- M2（第2周）：已完成
- M3（第3周）：已完成
- M4（第4周）：已完成（已落地止损/止盈、风险日报、回撤熔断、行业集中度约束与单票权重上限）
- M5（第5周）：已完成（已落地提示词拆分 + JSON schema + 安全规则 + 分析导出与齐全率统计 + 低温度稳定性评估并通过）
- M6（第6周）：已完成（Plotly Dashboard MVP + OpenClaw 指令模板固化 + 使用/运维手册交付 + CI 冒烟验收）
- M7（v0.7）：已完成（Week1~Week4 全部落地，含 CI 回归快照漂移告警）

## 1. 项目目标

构建一个可本地运行的 AI 量化分析助手，支持：

- 单股分析：行情、技术指标、策略信号、图表、AI解读
- 全市场扫描：A股快照落盘、条件筛选、Top N 候选池
- 模板回测：收益、回撤、夏普、胜率、交易次数
- 组合风控：仓位限制、止损、回撤阈值告警
- OpenClaw 交互：命令式调用和结构化输出

## 2. 当前基础（已具备）

基于 `stock_analyzer.py`，当前已实现：

- A股快照抓取与分批落盘（AkShare）
- 单股历史行情抓取（yfinance）和指标计算（pandas_ta）
- MACD/RSI/BOLL/MA 模板信号
- 简单回测引擎（long-only）
- 图表输出（matplotlib）
- 本地 Qwen2.5 解读（兼容 Ollama 原生和 OpenAI 风格接口）
- CLI 参数体系（同步、筛选、单股、回测、是否启用 LLM）

## 3. 目标架构（建议）

```text
openclaw-finance/
  app/
    cli.py                  # 命令入口
    config.py               # 环境变量与路径配置
  data/
    providers/
      akshare_provider.py   # A股快照与历史数据
      yf_provider.py        # 海外/兜底数据源
    repository/
      market_store.py       # CSV/Parquet 读写
  factors/
    indicators.py           # MA/EMA/RSI/MACD/BOLL
    features.py             # 扩展特征
  strategy/
    rules/
      trend_follow.py
      reversal.py
    signal_engine.py
  backtest/
    engine.py               # 回测执行
    metrics.py              # 绩效指标
    cost_model.py           # 手续费/滑点
  portfolio/
    manager.py              # 仓位、风控
    risk.py                 # 风险阈值与告警
  llm/
    qwen_client.py          # 本地模型调用
    prompts.py              # 提示词模板
    summarizer.py           # 结构化结论生成
  report/
    renderer.py             # 文本/JSON/Markdown
  dashboard/
    app.py                  # Plotly 看板（后续）
  tests/
    unit/
    integration/
```

## 4. 里程碑与排期（7周，含 v0.7 规划）

### M1（第1周）：工程化重构 + 配置标准化

- 将 `stock_analyzer.py` 拆分为模块化目录（不改业务逻辑）
- 增加 `config.py` 和 `.env.example`
- 增加统一日志（INFO/ERROR）和错误码
- 增加基础单元测试（指标、信号、回测指标）

验收标准：

- 现有命令行为与旧版本一致
- 核心函数覆盖率 >= 60%
- 出现接口失败时能返回可读错误信息

当前状态：已完成（覆盖率阈值待补充 coverage 统计后量化确认）

### M2（第2周）：市场扫描与候选池评分

- 在快照筛选上新增评分器（趋势、量价、波动、换手）
- 支持 `--universe` 参数（沪深300/中证500/全市场）
- 输出 Top N 候选股票（CSV + Markdown）

验收标准：

- 一次扫描 5000+ 标的可在可接受时间完成
- 输出结果字段完整、可复现

当前状态：已完成（已落地 universe 过滤、评分字段与 CSV/Markdown 导出）

基准记录（2026-03-05，北京时间）：

- 样本文件：`data/ashare_snapshots/ashare_snapshot_20260305_194702.csv`
- 样本规模：5486 标的
- 命令：`python stock_analyzer.py --scan --snapshot-file data/ashare_snapshots/ashare_snapshot_20260305_194702.csv --universe all --top 20`
- 用时：0.57s / 0.56s / 0.55s（平均 0.56s）
- 结论：5000+ 标的扫描在当前机器上可在 1 秒内完成

评分参数（可复现、可调）：

- `.env` 支持：`SCORE_WEIGHT_TREND`、`SCORE_WEIGHT_VOLUME_PRICE`、`SCORE_WEIGHT_VOLATILITY`、`SCORE_WEIGHT_TURNOVER`
- 默认值：`0.35 / 0.30 / 0.15 / 0.20`
- 运行时自动归一化，避免配置和不为 1 造成结果漂移

### M3（第3周）：回测引擎增强

- 引入交易成本模型（手续费+滑点）
- 支持信号去抖、最小持仓天数、最大持仓数
- 新增基准对比、年度分解、滚动回撤

验收标准：

- 回测结果可重复（同参数同输出）
- 输出包括总收益、年化、回撤、夏普、卡玛、胜率

当前状态：已完成（已支持手续费+滑点、信号去抖、最小持仓天数、`max_positions` 组合限仓、卡玛比率、年度分解、滚动回撤、回测结果 JSON/Markdown 落盘与最近一次参数对比、参数网格回测排行榜）

### M4（第4周）：组合管理与风控

- 增加组合层仓位管理（单票上限、行业集中度）
- 增加止损止盈规则和组合回撤熔断
- 增加风险日报（当日信号、风险暴露、告警）

验收标准：

- 能对组合触发风险规则并给出原因
- 风险报告可导出 Markdown/JSON

当前状态：已完成（已支持 `--bt-stop-loss-pct` / `--bt-take-profit-pct`、`--bt-drawdown-circuit-pct` / `--bt-circuit-cooldown-days`、`--bt-max-industry-weight` / `--industry-map-file` / `--industry-level`、`--bt-max-single-weight`，并提供 `--risk-report` 导出 Markdown/JSON 风险日报；实盘样例验证低风险等级并完成基线对比）

### M5（第5周）：AI 助手能力升级

- 提示词拆分：技术面解释 / 策略复盘 / 风险建议
- 输出 JSON schema（结论、证据、风险、待观察点）
- 增加“禁用确定性收益承诺”与“高风险提示”安全规则

验收标准：

- AI 输出结构稳定（字段齐全率 >= 95%）
- 同一输入在低温度下输出波动可控

当前状态：已完成（已新增 `llm/prompts.py` 与 `llm/summarizer.py`，实现“技术面解释/策略复盘/风险建议”提示词拆分、结构化 JSON 解析与安全规则；CLI 支持 `--llm-json` 输出结构化结果，并支持 `--analysis-save` 导出单股分析 JSON/Markdown、`--llm-stability-runs`/`--llm-stability-temperature` 进行低温度稳定性评估，内置 schema 字段齐全率统计；实测 Schema 齐全率 100%，低温度稳定性综合分 0.922，判定“通过”）

### M6（第6周）：可视化与交互交付

- 增加 Plotly 交互看板（单股 + 候选池 + 组合）
- OpenClaw 指令模板固化（分析、扫描、回测、风控）
- 形成可交付文档（使用手册 + 运维手册）

验收标准：

- 支持桌面端和移动端基础浏览
- 新用户按文档可在 30 分钟内跑通主流程

当前状态：已完成（已新增 `dashboard/app.py`，支持 `python -m dashboard.app` 生成 `dashboard/dist/index.html`，包含单股分析、候选池评分、组合回测、风险日报四个板块；已补 `make dashboard` 快捷入口；已新增 `skills/stock-analyst/SKILL.md` 与 `docs/openclaw_templates.md` 固化 OpenClaw 分析/扫描/回测/风控模板，并明确单次触发、防重复、超时与失败回退策略；已新增 `docs/user_guide.md` 与 `docs/ops_runbook.md` 形成可交付手册，并接入 `.github/workflows/ci.yml` + `tests/fixtures/skill_output_ok.txt` 完成严格冒烟验收）

### M7（v0.7，4周）：自动化运行与稳健性升级

- Week 1：自动化日更流水线
  - 串联 `sync -> scan -> backtest -> risk-report -> dashboard` 为定时任务（cron/systemd）。
  - 增加失败重试、失败摘要日志与健康状态记录。
  - 产物按日期目录落盘，支持追溯。
- Week 2：策略稳健性增强
  - 增加 Walk-forward（滚动训练/验证）评估。
  - 增加参数稳健区间报告（避免单点最优过拟合）。
  - 增加与基准/当前策略版本的分段对比。
- Week 3：组合层升级
  - 增加目标波动率控制与资金利用率约束。
  - 增加周/月再平衡模式与统一调仓记录。
  - 完成行业/单票/回撤约束联动解释（每次风控触发给出可读原因）。
- Week 4：交付与接口
  - 输出标准化 JSON 接口（供看板/外部系统消费）。
  - 看板升级为 V2（参数对比、回测曲线对比、风险时序）。
  - CI 增加策略回归快照（关键指标漂移告警）。

验收标准：

- 自动化流水线连续 7 天成功运行，失败可重试并有可读日志。
- Walk-forward 报告可复现，包含分段收益、回撤、夏普。
- 组合风控触发时可输出“触发条件 + 触发时点 + 处理动作”。
- CI 保持绿色，`unittest + smoke-skill(strict)` 全通过。
- 新用户按文档 20 分钟内跑通主流程。

当前状态：已完成（Week1 日更流水线、Week2 Walk-forward+稳健区间+分段对比、Week3 目标波动率/资金利用率/周月再平衡/调仓记录、Week4 标准化 JSON + Dashboard V2 + CI 策略回归快照漂移告警均已落地）

## 5. 命令接口规划

保留并扩展 CLI：

```bash
# 单股分析
python stock_analyzer.py 600519 --backtest

# 同步A股快照并筛选
python stock_analyzer.py --sync-a-share --batch-size 300 --runs 1
python stock_analyzer.py --keyword 芯片 --min-turnover 3 --top 30

# M2 已支持
python stock_analyzer.py --scan --universe hs300 --top 20
python -m app.cli portfolio --rebalance
python -m app.cli report --daily
```

## 6. OpenClaw 集成方案

- 提供固定技能命令模板，确保“先执行本地命令，再输出总结”
- 要求 AI 回复包含：
  - 数据时间戳
  - 关键信号与证据
  - 风险提示
  - 非投资建议声明
- 调用失败时回传真实错误（禁网、超时、模型不可用、字段缺失）

## 7. 风险与治理

- 数据风险：AkShare/yfinance 字段变化，需做 schema 校验
- 模型风险：Qwen 输出幻觉，必须附证据字段
- 策略风险：禁止直接自动交易，默认仅建议模式
- 合规风险：输出统一加入“仅供研究，不构成投资建议”
- 运维风险：增加定时任务健康检查与失败重试

## 8. 成果物清单

- 代码：模块化量化助手代码库
- 文档：部署手册、参数说明、策略说明、风险说明
- 报表：单股报告、候选池报告、组合风险报告
- 看板：Plotly 交互页（行情/信号/绩效）

## 9. 第一周执行清单（已完成）

- [x] 抽离 `data/factors/strategy/backtest/llm` 五层模块
- [x] 新增 `requirements.txt` 或 `pyproject.toml` 锁版本
- [x] 增加 `.env.example`（QWEN_BASE_URL、QWEN_MODEL、QWEN_TIMEOUT）
- [x] 增加 `tests/test_indicators.py`、`tests/test_backtest.py`
- [x] 增加 `Makefile`：`make test` / `make analyze SYMBOL=600519`
- [x] 保持旧命令兼容，先跑通回归测试

验证记录（2026-03-05）：

- `make test` 通过（4/4）

---

备注：你当前机器配置可支撑“本地研究助手 + 中等规模扫描 + 日级回测”。如需分钟级高频回测或更大模型低延迟推理，建议后续增加更高显存 GPU 或拆分为独立推理服务。
