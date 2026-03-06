# OpenClaw 指令模板（M6-2）

本文档固定 OpenClaw 的主流程命令模板，目标是“单次触发、稳定返回、可追踪失败原因”。

## 1. 全局执行规则
1. 一次用户请求只执行一条主命令。
2. 主命令失败时最多一次回退命令。
3. 不重复创建子代理，不重复 `sessions_spawn`。
4. 命令执行前不做全目录搜索路径。
5. 输出必须包含：时间戳、关键指标、风险声明。

## 1.1 稳定配置（必配）
为避免 `/skill stock-analyst` 被系统内置 memory flush 提示打断（出现 `NO_REPLY` 或空回复），建议固定以下配置：

```bash
openclaw config set hooks.internal.entries.session-memory.enabled false
openclaw config set agents.defaults.compaction.memoryFlush.enabled false
openclaw config set commands.nativeSkills true
openclaw config set commands.native true
systemctl --user restart openclaw-gateway.service
```

快速核验：
```bash
openclaw config get hooks.internal.entries.session-memory.enabled
openclaw config get agents.defaults.compaction.memoryFlush.enabled
```
期望结果均为 `false`。

## 2. 单股分析模板

### 2.1 快速分析（推荐）
```bash
/home/wgj/openclaw-finance/run_stock.sh <SYMBOL>
```

### 2.2 结构化分析（带 LLM JSON 与落盘）
```bash
cd /home/wgj/openclaw-finance && \
venv312/bin/python stock_analyzer.py <SYMBOL> --llm-json --analysis-save
```

## 3. 市场扫描模板

### 3.1 同步 A 股快照
```bash
cd /home/wgj/openclaw-finance && \
venv312/bin/python stock_analyzer.py --sync-a-share --runs 1
```

### 3.2 候选池扫描（示例：沪深300 Top20）
```bash
cd /home/wgj/openclaw-finance && \
venv312/bin/python stock_analyzer.py --scan --universe hs300 --top 20
```

### 3.3 价值投资候选池（示例：Top20）
```bash
cd /home/wgj/openclaw-finance && \
venv312/bin/python stock_analyzer.py --value-scan --universe all --value-top 20
```

## 4. 回测模板

### 4.1 单股回测
```bash
cd /home/wgj/openclaw-finance && \
venv312/bin/python stock_analyzer.py 600519 --backtest
```

### 4.2 组合回测（含成本与持仓约束）
```bash
cd /home/wgj/openclaw-finance && \
venv312/bin/python stock_analyzer.py \
  --portfolio-symbols 600519,000001,300750 \
  --backtest \
  --bt-fee-rate 0.001 \
  --bt-slippage-bps 8 \
  --bt-min-hold-days 3 \
  --bt-signal-confirm-days 2 \
  --bt-max-positions 2 \
  --bt-save \
  --bt-compare-last
```

## 5. 风控模板

### 5.1 风险日报（含行业与单票约束）
```bash
cd /home/wgj/openclaw-finance && \
venv312/bin/python stock_analyzer.py \
  --portfolio-symbols 600519,000001,300750 \
  --backtest \
  --bt-max-positions 2 \
  --bt-stop-loss-pct 0.08 \
  --bt-take-profit-pct 0.15 \
  --bt-drawdown-circuit-pct 0.10 \
  --bt-circuit-cooldown-days 5 \
  --bt-max-industry-weight 0.6 \
  --bt-max-single-weight 0.35 \
  --industry-map-file data/industry_map.csv \
  --industry-level l1 \
  --risk-report \
  --bt-save
```

## 6. Dashboard 模板
```bash
cd /home/wgj/openclaw-finance && make dashboard
```

本地预览：
```bash
cd /home/wgj/openclaw-finance && \
venv312/bin/python -m dashboard.app --serve --port 8765
```

## 7. 日更流水线模板（M7 Week1）
先 dry-run：

```bash
cd /home/wgj/openclaw-finance && \
bash scripts/run_daily_pipeline.sh --dry-run
```

正式执行：

```bash
cd /home/wgj/openclaw-finance && \
make pipeline-daily
```

自定义参数：

```bash
cd /home/wgj/openclaw-finance && \
bash scripts/run_daily_pipeline.sh \
  --single-symbol 600519 \
  --portfolio-symbols 600519,000001,300750 \
  --universe hs300 \
  --top 20 \
  --max-retries 2 \
  --retry-delay-sec 15
```

健康状态文件：
- `data/pipeline_runs/latest_health.json`

## 8. 失败回退矩阵
- `ProxyError/ConnectionError`：保持命令不变重试 1 次；仍失败则返回真实错误并结束。
- `model 'default' not found`：切换到明确模型名，不再使用默认占位模型。
- `gateway already running`：不要重启网关，直接复用现有连接。
- `行业映射文件不存在`：提示补齐 `data/industry_map.csv` 后再执行风控模板。

## 9. 推荐的 OpenClaw TUI 触发语句
- 分析：`/skill stock-analyst 600519`
- 日更流水线：`/skill pipeline-daily --skip-sync --max-retries 0`
- 扫描：`执行候选池扫描：--scan --universe hs300 --top 20`
- 价值投资 Top20：`最具价值投资的前20支股票`
- 单股价值预判：`分析 600519 是否适合价值投资`
- 回测：`执行组合回测模板（max_positions=2）`
- 风控：`执行风险日报模板（industry + single weight）`

## 10. 冒烟验收（Skill输出）
将 TUI 输出保存到文本文件后执行：

```bash
cd /home/wgj/openclaw-finance && \
make smoke-skill SMOKE_OUTPUT=/tmp/stock_skill_output.txt
```

严格模式（有告警也视为失败）：
```bash
cd /home/wgj/openclaw-finance && \
make smoke-skill SMOKE_OUTPUT=/tmp/stock_skill_output.txt SMOKE_STRICT=1
```

当前冒烟检查项：
- 不得包含 `NO_REPLY`
- 不得包含 `Pre-compaction memory flush` 维护提示
- 必须包含图表文件路径（`/home/wgj/openclaw-finance/charts/*.png`）
