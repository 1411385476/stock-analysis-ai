# AI量化分析助手实施方案

## 1. 目标
- 输入股票代码或名称，自动输出：
  - 最新行情与技术指标
  - 策略信号与回测结果
  - 图表与AI解读
- 运行环境：Ubuntu 22 + 64G RAM + RTX 4060 + OpenClaw + Qwen2.5 + Python工具链

## 2. 系统架构
- 数据层：`akshare/yfinance` 获取行情，统一为标准 OHLCV 结构
- 因子层：`pandas_ta` 计算 MA/EMA/RSI/MACD/BOLL
- 策略层：规则信号 + 回测（收益/回撤/夏普/胜率）
- AI层：`qwen2.5:32b` 负责解释、总结、风险提示
- 交互层：OpenClaw TUI + `stock-analyst` 技能

## 3. 最小可用流程（MVP）
1. 代码标准化（如 `002739 -> 002739.SZ`）
2. 拉取历史行情并清洗
3. 计算技术指标
4. 生成策略信号
5. 执行回测并汇总指标
6. 输出图表
7. 调用Qwen生成中文解读

## 4. 工程拆分
- `stock_analyzer.py`
  - `fetch_*`: 获取与清洗
  - `add_indicators`: 指标
  - `strategy_signals`: 信号模板
  - `run_backtest`: 回测
  - `generate_chart`: 图表
  - `call_local_qwen`: 本地模型解读
- 输出格式统一为结构化文本 + 图表路径

## 5. 风控建议
- 单票最大仓位限制（如 10%-20%）
- 固定止损（如 -5%）和移动止盈规则
- 组合级回撤阈值报警（如 -10%）
- AI解读仅做辅助，不直接触发交易

## 6. OpenClaw 集成建议
- 技能规则强制“先执行本地命令再回答”
- 查询失败时返回真实错误（禁网/超时/模型不可用）
- 为常用命令提供固定模板：
  - `python stock_analyzer.py 002739`
  - `python stock_analyzer.py 600519 --backtest`

## 7. 下一步迭代
1. 增加自选池批量扫描（Top N 打分）
2. 导出 `json/csv` 报告
3. 增加 `--fast-llm` 与 `--deep-llm` 两种模式
4. 接入 Plotly 交互式看板

