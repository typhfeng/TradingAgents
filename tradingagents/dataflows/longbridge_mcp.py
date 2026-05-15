"""Longbridge MCP data vendor integration.

Longbridge hosts a Streamable HTTP MCP endpoint at:
https://open.longbridge.com/docs/mcp

The MCP Python SDK client pattern used here follows the official SDK docs:
https://py.sdk.modelcontextprotocol.io/client/
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .config import get_config


LONG_BRIDGE_MCP_VENDOR = "longbridge_mcp"
DEFAULT_ENDPOINT = "https://openapi.longbridge.com/mcp"
CHINA_ENDPOINT = "https://openapi.longbridge.cn/mcp"


class LongbridgeMCPError(RuntimeError):
    """Raised when the Longbridge MCP vendor cannot complete a request."""


@dataclass(frozen=True)
class LongbridgeMCPSettings:
    endpoint: str
    access_token: str | None
    default_market: str | None
    timeout_seconds: float
    tool_names: dict[str, str]
    tool_arguments: dict[str, dict[str, Any]]


DEFAULT_TOOL_NAMES = {
    "stock_data": "history_candlesticks_by_date",
    "fundamentals": "company",
    "balance_sheet": "financial_statement",
    "cashflow": "cash_flow",
    "income_statement": "financial_statement",
    "news": "news_search",
    "global_news": "news_search",
    "insider_transactions": "executive",
}

DEFAULT_TOOL_ARGUMENTS = {
    "stock_data": {
        "period": 1000,  # Period.Day in the Longbridge OpenAPI enum.
        "adjust_type": 0,  # AdjustType.NoAdjust.
    },
    "balance_sheet": {
        "statement_type": "balance_sheet",
    },
    "income_statement": {
        "statement_type": "income_statement",
    },
    "cashflow": {},
    "news": {},
    "global_news": {
        "keyword": "stock market economy",
    },
    "insider_transactions": {},
}


def _get_settings() -> LongbridgeMCPSettings:
    config = get_config().get("longbridge_mcp", {})
    endpoint = (
        os.getenv("TRADINGAGENTS_LONGBRIDGE_MCP_URL")
        or config.get("endpoint")
        or DEFAULT_ENDPOINT
    )
    access_token = (
        os.getenv("TRADINGAGENTS_LONGBRIDGE_MCP_ACCESS_TOKEN")
        or config.get("access_token")
    )
    default_market = (
        os.getenv("TRADINGAGENTS_LONGBRIDGE_DEFAULT_MARKET")
        or config.get("default_market")
    )
    timeout_seconds = float(
        os.getenv("TRADINGAGENTS_LONGBRIDGE_MCP_TIMEOUT", config.get("timeout_seconds", 30))
    )
    tool_names = DEFAULT_TOOL_NAMES | config.get("tool_names", {})
    tool_arguments = {
        key: (DEFAULT_TOOL_ARGUMENTS.get(key, {}) | config.get("tool_arguments", {}).get(key, {}))
        for key in set(DEFAULT_TOOL_ARGUMENTS) | set(config.get("tool_arguments", {}))
    }

    return LongbridgeMCPSettings(
        endpoint=endpoint,
        access_token=access_token,
        default_market=default_market,
        timeout_seconds=timeout_seconds,
        tool_names=tool_names,
        tool_arguments=tool_arguments,
    )


def _normalize_symbol(symbol: str, default_market: str | None = None) -> str:
    normalized = symbol.strip().upper()
    if "." not in normalized and default_market:
        return f"{normalized}.{default_market.strip().upper()}"
    return normalized


def _compact_date(date_value: str) -> str:
    return datetime.strptime(date_value, "%Y-%m-%d").strftime("%Y%m%d")


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}

    def runner():
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - re-raised in caller thread
            result["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


@asynccontextmanager
async def _open_session(settings: LongbridgeMCPSettings):
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
    except ModuleNotFoundError as exc:
        raise LongbridgeMCPError(
            "Longbridge MCP support requires the 'mcp' package. "
            "Install project dependencies from pyproject.toml before using this vendor."
        ) from exc

    headers = {}
    if settings.access_token:
        headers["Authorization"] = f"Bearer {settings.access_token}"

    # The official MCP Python SDK documents streamable_http_client(url) with
    # ClientSession(read, write), and accepts headers for authenticated HTTP MCP
    # endpoints.
    kwargs = {"headers": headers} if headers else {}
    async with streamable_http_client(settings.endpoint, **kwargs) as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await asyncio.wait_for(session.initialize(), timeout=settings.timeout_seconds)
            yield session


async def _call_mcp_tool_async(tool_name: str, arguments: dict[str, Any]) -> Any:
    settings = _get_settings()
    try:
        async with _open_session(settings) as session:
            result = await asyncio.wait_for(
                session.call_tool(tool_name, arguments=arguments),
                timeout=settings.timeout_seconds,
            )
        return _extract_mcp_result(result)
    except LongbridgeMCPError:
        raise
    except Exception as exc:
        raise LongbridgeMCPError(f"Longbridge MCP tool '{tool_name}' failed: {exc}") from exc


def call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    return _run_async(_call_mcp_tool_async(tool_name, arguments))


def _extract_mcp_result(result: Any) -> Any:
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return structured

    content = getattr(result, "content", None)
    if content:
        text_parts = []
        for item in content:
            text = getattr(item, "text", None)
            if text is not None:
                text_parts.append(text)
        if len(text_parts) == 1:
            return _parse_json_if_possible(text_parts[0])
        if text_parts:
            return "\n".join(text_parts)

    return result


def _parse_json_if_possible(value: str) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def _to_plain_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _to_plain_data(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_to_plain_data(item) for item in value]
    if hasattr(value, "model_dump"):
        return _to_plain_data(value.model_dump(mode="json"))
    if hasattr(value, "dict"):
        return _to_plain_data(value.dict())
    return value


def _format_raw_result(title: str, result: Any) -> str:
    plain = _to_plain_data(result)
    if isinstance(plain, str):
        return f"# {title}\n\n{plain}"
    return f"# {title}\n\n{json.dumps(plain, indent=2, sort_keys=True, default=str)}"


def _find_records(result: Any, candidate_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    plain = _to_plain_data(result)
    if isinstance(plain, dict):
        for key in candidate_keys:
            value = plain.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        for value in plain.values():
            nested = _find_records(value, candidate_keys)
            if nested:
                return nested
    if isinstance(plain, list):
        return [item for item in plain if isinstance(item, dict)]
    return []


def _format_candlesticks(symbol: str, start_date: str, end_date: str, result: Any) -> str:
    rows = _find_records(result, ("candlesticks", "data", "items"))
    if not rows:
        return _format_raw_result(f"Longbridge stock data for {symbol}", result)

    csv_rows = ["Date,Open,High,Low,Close,Volume,Turnover"]
    for row in rows:
        timestamp = row.get("timestamp") or row.get("time") or row.get("date")
        date_text = str(timestamp)
        if isinstance(timestamp, (int, float)):
            date_text = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
        csv_rows.append(
            ",".join(
                str(row.get(field, ""))
                for field in ("date", "open", "high", "low", "close", "volume", "turnover")
            ).replace(str(row.get("date", "")), date_text, 1)
        )

    header = f"# Stock data for {symbol} from {start_date} to {end_date}\n"
    header += f"# Data source: Longbridge MCP\n"
    header += f"# Total records: {len(rows)}\n\n"
    return header + "\n".join(csv_rows)


def _format_news(title: str, result: Any, limit: int | None = None) -> str:
    rows = _find_records(result, ("news", "items", "data", "results"))
    if not rows:
        return _format_raw_result(title, result)

    parts = [f"## {title}"]
    for row in rows[:limit]:
        headline = row.get("title") or row.get("headline") or row.get("name") or "Untitled"
        source = row.get("source") or row.get("publisher") or row.get("provider")
        published_at = row.get("published_at") or row.get("time") or row.get("timestamp")
        summary = row.get("summary") or row.get("content") or row.get("description")
        url = row.get("url") or row.get("link")
        meta = " | ".join(str(item) for item in (source, published_at) if item)
        parts.append(f"\n### {headline}" + (f" ({meta})" if meta else ""))
        if summary:
            parts.append(str(summary))
        if url:
            parts.append(f"Link: {url}")
    return "\n".join(parts)


def _configured_tool(key: str) -> tuple[str, dict[str, Any]]:
    settings = _get_settings()
    return settings.tool_names[key], settings.tool_arguments.get(key, {}).copy()


def _call_configured_tool(key: str, arguments: dict[str, Any]) -> Any:
    tool_name, defaults = _configured_tool(key)
    return call_mcp_tool(tool_name, defaults | arguments)


def get_stock(
    symbol: str,
    start_date: str,
    end_date: str,
) -> str:
    settings = _get_settings()
    normalized_symbol = _normalize_symbol(symbol, settings.default_market)
    result = _call_configured_tool(
        "stock_data",
        {
            "symbol": normalized_symbol,
            "query_type": 2,
            "date_request": {
                "start_date": _compact_date(start_date),
                "end_date": _compact_date(end_date),
            },
        },
    )
    return _format_candlesticks(normalized_symbol, start_date, end_date, result)


def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    settings = _get_settings()
    normalized_symbol = _normalize_symbol(ticker, settings.default_market)
    result = _call_configured_tool("fundamentals", {"symbol": normalized_symbol})
    return _format_raw_result(f"Company fundamentals for {normalized_symbol}", result)


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str = None):
    return _get_statement("balance_sheet", ticker, freq, curr_date)


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str = None):
    return _get_statement("cashflow", ticker, freq, curr_date)


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str = None):
    return _get_statement("income_statement", ticker, freq, curr_date)


def _get_statement(key: str, ticker: str, freq: str, curr_date: str | None):
    settings = _get_settings()
    normalized_symbol = _normalize_symbol(ticker, settings.default_market)
    args = {
        "symbol": normalized_symbol,
        "frequency": freq,
    }
    if curr_date:
        args["date"] = _compact_date(curr_date)
    result = _call_configured_tool(key, args)
    return _format_raw_result(f"{key.replace('_', ' ').title()} for {normalized_symbol}", result)


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    settings = _get_settings()
    normalized_symbol = _normalize_symbol(ticker, settings.default_market)
    result = _call_configured_tool(
        "news",
        {
            "symbol": normalized_symbol,
            "keyword": normalized_symbol,
            "start_date": _compact_date(start_date),
            "end_date": _compact_date(end_date),
        },
    )
    return _format_news(f"{normalized_symbol} News, from {start_date} to {end_date}", result)


def get_global_news(curr_date: str, look_back_days: int = 7, limit: int = 50) -> str:
    result = _call_configured_tool(
        "global_news",
        {
            "end_date": _compact_date(curr_date),
            "look_back_days": look_back_days,
            "limit": limit,
        },
    )
    return _format_news(f"Global Market News for {curr_date}", result, limit=limit)


def get_insider_transactions(symbol: str) -> str:
    settings = _get_settings()
    normalized_symbol = _normalize_symbol(symbol, settings.default_market)
    result = _call_configured_tool("insider_transactions", {"symbol": normalized_symbol})
    return _format_raw_result(f"Insider and Executive Data for {normalized_symbol}", result)
