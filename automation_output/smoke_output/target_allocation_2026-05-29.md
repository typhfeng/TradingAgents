# Target Allocation - 2026-05-29

## Assumptions
- 组合目标总仓位为 100%。
- `Underweight`、`Hold`、`Sell` 均按 0% 处理。
- `Buy` 与 `Overweight` 视为可分配标的，`Buy` 的分配分值为 2，`Overweight` 的分配分值为 1。
- 若 `GOOGL` 与 `GOOG` 同时为正向评级，仅保留 `GOOGL` 的经济敞口，`GOOG` 记为 0%。

## Longbridge MCP Adoption
- 目标 ticker 数: 1
- 已生成报告: 0/1
- 关键文件校验通过: 0/0
- `data_sources.md` 中出现 Longbridge MCP: 0/1
- 市场报告出现 Longbridge 证据: 0/1
- 新闻报告出现 Longbridge 证据: 0/1
- 基本面报告出现 Longbridge 证据: 0/1
- LEAP 报告出现 Longbridge 证据: 0/1

## Target Weights
| Ticker | Rating | Target Weight | Key Execution Notes | Report Path |
| --- | --- | ---: | --- | --- |
| NVDA | Hold | 0.00% | N/A | ERROR |

## Implementation Notes
- 非零权重仅分配给正向评级标的，确保总和精确为 100%。
- 若报告中缺少 Longbridge 证据字段，不代表一定未调用 Longbridge；也可能是运行时回退至 yfinance 或模型未在对应章节显式引用。
- 目标配置文件路径: automation_output/smoke_output/target_allocation_2026-05-29.md

## Report Links
- NVDA: ERROR

## Final Summary
- Top buys: 无
- Holds/zero weights: NVDA (Hold)
- Errors/data-source gaps:
- NVDA: APIConnectionError: Connection error.
