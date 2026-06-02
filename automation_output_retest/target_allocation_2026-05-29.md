# Target Allocation - 2026-05-29

## Assumptions
- 组合目标总仓位为 100%。
- `Underweight`、`Hold`、`Sell` 均按 0% 处理。
- `Buy` 与 `Overweight` 视为可分配标的，`Buy` 的分配分值为 2，`Overweight` 的分配分值为 1。
- 若 `GOOGL` 与 `GOOG` 同时为正向评级，仅保留 `GOOGL` 的经济敞口，`GOOG` 记为 0%。

## Longbridge MCP Adoption
- 目标 ticker 数: 1
- 已生成报告: 1/1
- 关键文件校验通过: 1/1
- `data_sources.md` 中出现 Longbridge MCP: 1/1
- 市场报告出现 Longbridge 证据: 0/1
- 新闻报告出现 Longbridge 证据: 0/1
- 基本面报告出现 Longbridge 证据: 0/1
- LEAP 报告出现 Longbridge 证据: 1/1

## Target Weights
| Ticker | Rating | Target Weight | Key Execution Notes | Report Path |
| --- | --- | ---: | --- | --- |
| NVDA | Overweight | 100.00% | 对 NVDA 的最终决策为“Overweight”，执行上采取分批买入、逐步增配，而不是当前价位一次性追高。建议以中等超配为上限，先建立中等仓位，回踩但守住 50 日均线附近可继续加仓；若有效跌破 50 日均线且无法快速收复，则暂停加仓并在 200 日均线附近重新评估。持有周期以 3-6 个月为主，结合波动率较高这一特征，单次加仓幅度宜小、避免满仓表达。 | /Volumes/ssd2/tradingagents/logs/reports/NVDA/2026-05-29_20260601_213626/complete_report.md |

## Implementation Notes
- 非零权重仅分配给正向评级标的，确保总和精确为 100%。
- 若报告中缺少 Longbridge 证据字段，不代表一定未调用 Longbridge；也可能是运行时回退至 yfinance 或模型未在对应章节显式引用。
- 目标配置文件路径: /Users/sunkewei/git/gh_all_repos/typhfeng__TradingAgents/automation_output_retest/target_allocation_2026-05-29.md

## Report Links
- NVDA: /Volumes/ssd2/tradingagents/logs/reports/NVDA/2026-05-29_20260601_213626/complete_report.md

## Final Summary
- Top buys: NVDA (100.00%)
- Holds/zero weights: 无
- Errors/data-source gaps:
- 无
