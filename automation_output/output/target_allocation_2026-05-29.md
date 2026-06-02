# Target Allocation - 2026-05-29

## Assumptions
- 组合目标总仓位为 100%。
- `Underweight`、`Hold`、`Sell` 均按 0% 处理。
- `Buy` 与 `Overweight` 视为可分配标的，`Buy` 的分配分值为 2，`Overweight` 的分配分值为 1。
- 若 `GOOGL` 与 `GOOG` 同时为正向评级，仅保留 `GOOGL` 的经济敞口，`GOOG` 记为 0%。

## Longbridge MCP Adoption
- 目标 ticker 数: 25
- 已生成报告: 0/25
- 关键文件校验通过: 0/0
- `data_sources.md` 中出现 Longbridge MCP: 0/25
- 市场报告出现 Longbridge 证据: 0/25
- 新闻报告出现 Longbridge 证据: 0/25
- 基本面报告出现 Longbridge 证据: 0/25
- LEAP 报告出现 Longbridge 证据: 0/25

## Target Weights
| Ticker | Rating | Target Weight | Key Execution Notes | Report Path |
| --- | --- | ---: | --- | --- |
| NVDA | Hold | 0.00% | N/A | ERROR |
| AAPL | Hold | 0.00% | N/A | ERROR |
| MSFT | Hold | 0.00% | N/A | ERROR |
| AMZN | Hold | 0.00% | N/A | ERROR |
| MU | Hold | 0.00% | N/A | ERROR |
| GOOGL | Hold | 0.00% | N/A | ERROR |
| TSLA | Hold | 0.00% | N/A | ERROR |
| GOOG | Hold | 0.00% | N/A | ERROR |
| AMD | Hold | 0.00% | N/A | ERROR |
| AVGO | Hold | 0.00% | N/A | ERROR |
| WMT | Hold | 0.00% | N/A | ERROR |
| BE | Hold | 0.00% | N/A | ERROR |
| CRDO | Hold | 0.00% | N/A | ERROR |
| FN | Hold | 0.00% | N/A | ERROR |
| STRL | Hold | 0.00% | N/A | ERROR |
| SATS | Hold | 0.00% | N/A | ERROR |
| INTC | Hold | 0.00% | N/A | ERROR |
| PLUG | Hold | 0.00% | N/A | ERROR |
| F | Hold | 0.00% | N/A | ERROR |
| ONDS | Hold | 0.00% | N/A | ERROR |
| POET | Hold | 0.00% | N/A | ERROR |
| AAL | Hold | 0.00% | N/A | ERROR |
| SOFI | Hold | 0.00% | N/A | ERROR |
| IREN | Hold | 0.00% | N/A | ERROR |
| NU | Hold | 0.00% | N/A | ERROR |

## Implementation Notes
- 非零权重仅分配给正向评级标的，确保总和精确为 100%。
- 若报告中缺少 Longbridge 证据字段，不代表一定未调用 Longbridge；也可能是运行时回退至 yfinance 或模型未在对应章节显式引用。
- 目标配置文件路径: automation_output/output/target_allocation_2026-05-29.md

## Report Links
- NVDA: ERROR
- AAPL: ERROR
- MSFT: ERROR
- AMZN: ERROR
- MU: ERROR
- GOOGL: ERROR
- TSLA: ERROR
- GOOG: ERROR
- AMD: ERROR
- AVGO: ERROR
- WMT: ERROR
- BE: ERROR
- CRDO: ERROR
- FN: ERROR
- STRL: ERROR
- SATS: ERROR
- INTC: ERROR
- PLUG: ERROR
- F: ERROR
- ONDS: ERROR
- POET: ERROR
- AAL: ERROR
- SOFI: ERROR
- IREN: ERROR
- NU: ERROR

## Final Summary
- Top buys: 无
- Holds/zero weights: NVDA (Hold), AAPL (Hold), MSFT (Hold), AMZN (Hold), MU (Hold), GOOGL (Hold), TSLA (Hold), GOOG (Hold), AMD (Hold), AVGO (Hold), WMT (Hold), BE (Hold), CRDO (Hold), FN (Hold), STRL (Hold), SATS (Hold), INTC (Hold), PLUG (Hold), F (Hold), ONDS (Hold), POET (Hold), AAL (Hold), SOFI (Hold), IREN (Hold), NU (Hold)
- Errors/data-source gaps:
- NVDA: APIConnectionError: Connection error.
- AAPL: APIConnectionError: Connection error.
- MSFT: APIConnectionError: Connection error.
- AMZN: APIConnectionError: Connection error.
- MU: APIConnectionError: Connection error.
- GOOGL: APIConnectionError: Connection error.
- TSLA: APIConnectionError: Connection error.
- GOOG: APIConnectionError: Connection error.
- AMD: APIConnectionError: Connection error.
- AVGO: APIConnectionError: Connection error.
- WMT: APIConnectionError: Connection error.
- BE: APIConnectionError: Connection error.
- CRDO: APIConnectionError: Connection error.
- FN: APIConnectionError: Connection error.
- STRL: APIConnectionError: Connection error.
- SATS: APIConnectionError: Connection error.
- INTC: APIConnectionError: Connection error.
- PLUG: APIConnectionError: Connection error.
- F: APIConnectionError: Connection error.
- ONDS: APIConnectionError: Connection error.
- POET: APIConnectionError: Connection error.
- AAL: APIConnectionError: Connection error.
- SOFI: APIConnectionError: Connection error.
- IREN: APIConnectionError: Connection error.
- NU: APIConnectionError: Connection error.
