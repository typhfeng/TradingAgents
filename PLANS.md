# Longbridge MCP Data Source Plan

## Problem

Add Longbridge MCP support as an optional TradingAgents data vendor without changing the default yfinance behavior.

## Context

- Existing data source selection is centralized in `tradingagents/dataflows/interface.py`.
- Agent tool functions call `route_to_vendor(...)`, so adding a vendor at this layer keeps analyst prompts and tool contracts stable.
- Longbridge documents a hosted Streamable HTTP MCP endpoint at `https://openapi.longbridge.com/mcp` and a China endpoint at `https://openapi.longbridge.cn/mcp`.

## Proposed Approach

1. Add a `longbridge_mcp` dataflow module with a small MCP client wrapper.
2. Expose read-only vendor functions for OHLCV, fundamentals, statements, news, and insider/executive data where Longbridge MCP has matching tools.
3. Register `longbridge_mcp` in the existing vendor router.
4. Keep unsupported tools, such as stockstats technical indicators, falling back to existing vendors.
5. Add focused unit tests that mock the MCP call boundary.

## Files Or Modules Affected

- `tradingagents/default_config.py`
- `tradingagents/dataflows/interface.py`
- `tradingagents/dataflows/longbridge_mcp.py`
- `pyproject.toml`
- `tests/test_longbridge_mcp.py`

## Validation

- Unit tests for symbol normalization, MCP argument mapping, formatted output, and vendor routing.
- Import/compile checks for the changed modules.

## Risks Or Open Questions

- Longbridge MCP requires OAuth 2.1 at runtime. The code can call a configured MCP endpoint, but users still need to authorize the MCP client/session according to Longbridge account permissions.
- MCP tool schemas can evolve; tool names and base arguments are configurable through `longbridge_mcp` config.
