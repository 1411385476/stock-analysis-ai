# AI量化分析助手使用手册

更新时间：2026-03-06

## 1. 目标
本手册用于让新用户在 30 分钟内跑通主流程：
- 同步A股快照
- 扫描候选池
- 单股分析与回测
- 查看可视化看板
- 通过 OpenClaw Skill 调用分析

## 2. 环境准备

在项目根目录执行：

```bash
cd /home/wgj/openclaw-finance
venv312/bin/python --version
```

常用入口：

```bash
make test
make analyze SYMBOL=600519
make dashboard
```

## 3. 主流程（推荐顺序）

### 3.1 同步A股快照

```bash
venv312/bin/python stock_analyzer.py --sync-a-share --runs 1
```

输出位置：
- `data/ashare_snapshots/ashare_latest.csv`

### 3.2 候选池扫描

```bash
venv312/bin/python stock_analyzer.py --scan --universe hs300 --top 20
```

可选：

```bash
venv312/bin/python stock_analyzer.py --scan --universe zz500 --top 30 --min-turnover 2
```

输出位置：
- `data/candidate_pools/`

### 3.3 单股分析 + 回测

```bash
venv312/bin/python stock_analyzer.py 600519 --backtest
```

输出位置：
- 图表：`charts/`
- 分析报告：控制台输出（可配 `--analysis-save` 落盘）

### 3.4 组合回测 + 风险报告

```bash
venv312/bin/python stock_analyzer.py \
  --portfolio-symbols 600519,000001,300750 \
  --backtest \
  --bt-max-positions 2 \
  --risk-report \
  --bt-save
```

输出位置：
- 回测：`data/backtests/`
- 风险：`data/risk_reports/`

### 3.4.1 Walk-forward 滚动评估（M7 Week2）

```bash
venv312/bin/python stock_analyzer.py \
  --portfolio-symbols 600519,000001,300750 \
  --backtest \
  --bt-grid \
  --bt-grid-fee-rates 0.001,0.0015 \
  --bt-grid-slippage-bps 4,8,12 \
  --bt-grid-min-hold-days 2,3,5 \
  --bt-grid-signal-confirm-days 1,2 \
  --bt-grid-max-positions 1,2 \
  --bt-walk-forward \
  --bt-wf-train-days 126 \
  --bt-wf-test-days 63 \
  --bt-wf-step-days 21 \
  --bt-save
```

输出说明：
- 控制台追加 `Walk-forward评估` 摘要（窗口胜率、平均年化、最差回撤等）
- 导出文件追加：
  - `wf_portfolio_*.json`
  - `wf_portfolio_*.md`

### 3.5 可视化看板

```bash
python -m dashboard.app --serve --port 8765
```

打开浏览器访问：
- `http://127.0.0.1:8765`

### 3.6 日更流水线（M7 Week1）

先做演练（不真正执行）：

```bash
bash scripts/run_daily_pipeline.sh --dry-run
```

正式执行：

```bash
make pipeline-daily
```

常用参数：

```bash
bash scripts/run_daily_pipeline.sh \
  --single-symbol 600519 \
  --portfolio-symbols 600519,000001,300750 \
  --universe hs300 \
  --top 20 \
  --max-retries 2 \
  --retry-delay-sec 15
```

输出位置（按日期分区）：
- `data/pipeline_runs/YYYYMMDD/YYYYMMDD_HHMMSS/`
- 健康状态：`data/pipeline_runs/latest_health.json`

说明：
- 当 `--universe hs300/zz500` 因网络原因无法加载成分股时，流水线会自动回退执行一次 `--universe all`，避免候选池面板为空。

### 3.7 标准化 JSON 接口（M7 Week4）

```bash
venv312/bin/python stock_analyzer.py \
  --standard-json-export \
  --standard-json-data-dir data \
  --standard-json-output data/api/standard_snapshot_latest.json
```

输出位置：
- `data/api/standard_snapshot_latest.json`

说明：
- 该快照会聚合最新的 analysis/candidate/backtest/grid/walk-forward/risk 结果，供看板或外部系统直接消费。

## 4. OpenClaw 使用方式

推荐在 OpenClaw TUI 中执行：

```text
/skill stock-analyst 600519
```

执行日更流水线（推荐）：

```text
/skill pipeline-daily --skip-sync --max-retries 0
```

期望结果：
- 返回单股分析摘要
- 包含图表路径
- 无 `NO_REPLY`、无维护提示文本回显

## 5. 输出验收

将 TUI 输出保存到文本文件后执行：

```bash
make smoke-skill SMOKE_OUTPUT=/tmp/stock_skill_output.txt
```

严格模式：

```bash
make smoke-skill SMOKE_OUTPUT=/tmp/stock_skill_output.txt SMOKE_STRICT=1
```

## 6. 常见问题

1. `model 'default' not found`
- 说明模型配置错误，需使用明确模型名（如 `ollama/qwen2.5:14b-instruct`）。

2. `gateway already running`
- 网关已在运行，不要重复启动，直接复用当前实例。

3. `ProxyError` 或 `RemoteDisconnected`
- 程序会自动尝试代理回退；若持续失败，检查本机网络与代理设置。

4. 输出出现 `NO_REPLY` 或维护提示
- 参见运维手册，确认 memory flush 配置已关闭。

5. 日更流水线失败
- 查看 `data/pipeline_runs/latest_health.json` 的 `failure_reason`
- 打开对应 `logs/*.log` 定位失败步骤

## 7. 风险声明
仅供研究，不构成投资建议。
