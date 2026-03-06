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

## 4. 日志排障

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

## 5. 故障处置手册

### 5.1 `/skill` 无输出或空回复
1. 新开会话：`/new`
2. 复测：`/skill stock-analyst 600519`
3. 核验 `memoryFlush` 配置是否已关闭
4. 重启网关后再测

### 5.2 出现 `NO_REPLY` / `Pre-compaction memory flush`
1. 检查 `agents.defaults.compaction.memoryFlush.enabled` 是否为 `false`
2. 确认不是旧会话缓存，使用 `/new` 复测

### 5.3 `model 'default' not found`
1. 检查 `agents.defaults.model.primary`
2. 确保模型名为已安装值，如 `ollama/qwen2.5:14b-instruct`

### 5.4 `gateway already running`
1. 不要重复启动 `openclaw gateway`
2. 直接复用现有端口 `18789`

## 6. 变更与发布检查单

发布前执行：

```bash
make test
make smoke-skill SMOKE_OUTPUT=tests/fixtures/skill_output_ok.txt SMOKE_STRICT=1
```

CI 绿灯后再合并/发布。

## 7. 回滚策略

- 配置回滚：恢复 `~/.openclaw/openclaw.json.bak`
- 代码回滚：`git revert <commit>`
- 服务恢复：`systemctl --user restart openclaw-gateway.service`

## 8. 风险声明
仅供研究，不构成投资建议。
