# AI量化分析助手运维手册

更新时间：2026-03-06

## 1. 组件与职责

- OpenClaw Gateway：会话、技能调度、工具调用
- Ollama：本地模型服务（`qwen2.5:14b-instruct`）
- openclaw-finance：数据拉取、策略计算、回测与报表

## 2. 稳定配置（必配）

为避免 `/skill stock-analyst` 被 memory flush 提示打断，执行：

```bash
openclaw config set hooks.internal.entries.session-memory.enabled false
openclaw config set agents.defaults.compaction.memoryFlush.enabled false
openclaw config set commands.nativeSkills true
openclaw config set commands.native true
systemctl --user restart openclaw-gateway.service
```

核验：

```bash
openclaw config get hooks.internal.entries.session-memory.enabled
openclaw config get agents.defaults.compaction.memoryFlush.enabled
```

期望均为 `false`。

## 3. 服务控制

```bash
systemctl --user status openclaw-gateway.service --no-pager -n 50
systemctl --user restart openclaw-gateway.service
systemctl --user stop openclaw-gateway.service
systemctl --user start openclaw-gateway.service
```

## 4. 自动化调度（M7 Week1）

### 4.1 手动运行

```bash
cd /home/wgj/openclaw-finance
bash scripts/run_daily_pipeline.sh --dry-run
make pipeline-daily
```

### 4.2 systemd timer（推荐）

```bash
mkdir -p ~/.config/systemd/user
cp ops/systemd/openclaw-finance-daily.service ~/.config/systemd/user/
cp ops/systemd/openclaw-finance-daily.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now openclaw-finance-daily.timer
systemctl --user status openclaw-finance-daily.timer --no-pager
```

### 4.3 cron（可选）

```bash
crontab -l > /tmp/mycron || true
cat ops/cron/openclaw-finance-daily.cron >> /tmp/mycron
crontab /tmp/mycron
```

## 5. 日志排障

网关日志：

```bash
journalctl --user -u openclaw-gateway.service -n 200 --no-pager
tail -n 200 /tmp/openclaw/openclaw-$(date +%F).log
```

会话日志：

```bash
ls -1t ~/.openclaw/agents/main/sessions/*.jsonl | head -n 3
tail -n 200 ~/.openclaw/agents/main/sessions/<session-id>.jsonl
```

流水线日志：

```bash
find data/pipeline_runs -name "pipeline.log" | tail -n 5
tail -n 200 data/pipeline_runs/latest_health.json
```

## 6. 故障处置手册

### 6.1 `/skill` 无输出或空回复
1. 新开会话：`/new`
2. 复测：`/skill stock-analyst 600519`
3. 核验 `memoryFlush` 配置是否已关闭
4. 重启网关后再测

补充：
- 日更任务优先使用：`/skill pipeline-daily --skip-sync --max-retries 0`
- 该技能会回传 `latest_health.json` 对应的 `status/run_dir/dashboard_html`，不依赖“后台运行”提示。

### 6.2 出现 `NO_REPLY` / `Pre-compaction memory flush`
1. 检查 `agents.defaults.compaction.memoryFlush.enabled` 是否为 `false`
2. 确认不是旧会话缓存，使用 `/new` 复测

### 6.3 `model 'default' not found`
1. 检查 `agents.defaults.model.primary`
2. 确保模型名为已安装值，如 `ollama/qwen2.5:14b-instruct`

### 6.4 `gateway already running`
1. 不要重复启动 `openclaw gateway`
2. 直接复用现有端口 `18789`

### 6.5 流水线失败（`status=failed`）
1. 先看 `data/pipeline_runs/latest_health.json` 的 `failure_reason`
2. 打开对应步骤日志（`logs/<step>.log`）
3. 修复后手动重跑：`make pipeline-daily`

补充：
- 若 `scan_candidates` 日志出现 `加载 universe=hs300 成分股失败`，流水线会自动触发 `scan_candidates_fallback_all`。

## 7. 变更与发布检查单

发布前执行：

```bash
make preflight
```

CI 绿灯后再合并/发布。

若策略逻辑发生“预期变更”，需要更新回归基线：

```bash
venv312/bin/python scripts/check_strategy_regression.py \
  --baseline tests/fixtures/strategy_regression_baseline.json \
  --update-baseline
```

## 8. 回滚策略

- 配置回滚：恢复 `~/.openclaw/openclaw.json.bak`
- 代码回滚：`git revert <commit>`
- 服务恢复：`systemctl --user restart openclaw-gateway.service`

## 9. 风险声明
仅供研究，不构成投资建议。
