"""Longbridge MCP data vendor integration.

Longbridge hosts a Streamable HTTP MCP endpoint at:
https://open.longbridge.com/docs/mcp

The MCP Python SDK client pattern used here follows the official SDK docs:
https://py.sdk.modelcontextprotocol.io/client/
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import subprocess
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .config import get_config


LONG_BRIDGE_MCP_VENDOR = "longbridge_mcp"
DEFAULT_ENDPOINT = "https://openapi.longbridge.com/mcp"
CHINA_ENDPOINT = "https://openapi.longbridge.cn/mcp"
DEFAULT_TOKEN_FILE = "/Volumes/ssd2/tradingagents/cache/longbridge_mcp_oauth.json"


class LongbridgeMCPError(RuntimeError):
    """Raised when the Longbridge MCP vendor cannot complete a request."""


@dataclass(frozen=True)
class LongbridgeMCPSettings:
    endpoint: str
    access_token: str | None
    default_market: str | None
    timeout_seconds: float
    oauth_token_file: str
    oauth_callback_port: int
    tool_names: dict[str, str]
    tool_arguments: dict[str, dict[str, Any]]


DEFAULT_TOOL_NAMES = {
    "stock_data": "candlesticks",
    "fundamentals": "static_info",
    "balance_sheet": "financial_statement",
    "cashflow": "financial_statement",
    "income_statement": "financial_statement",
    "news": "news",
    "global_news": "news_search",
    "insider_transactions": "executive",
}

DEFAULT_TOOL_ARGUMENTS = {
    "stock_data": {
        "period": "day",
        "count": 1000,
        "forward_adjust": True,
        "trade_sessions": "intraday",
    },
    "balance_sheet": {
        "kind": "BS",
        "report": "qf",
    },
    "income_statement": {
        "kind": "IS",
        "report": "qf",
    },
    "cashflow": {
        "kind": "CF",
        "report": "qf",
    },
    "news": {},
    "global_news": {
        "keyword": "stock market economy",
        "limit": 20,
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
    oauth_token_file = (
        os.getenv("TRADINGAGENTS_LONGBRIDGE_MCP_TOKEN_FILE")
        or config.get("oauth_token_file")
        or DEFAULT_TOKEN_FILE
    )
    oauth_callback_port = int(
        os.getenv("TRADINGAGENTS_LONGBRIDGE_MCP_CALLBACK_PORT", config.get("oauth_callback_port", 8765))
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
        oauth_token_file=oauth_token_file,
        oauth_callback_port=oauth_callback_port,
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

    http_client = _create_http_client(settings)
    kwargs = {}
    if http_client is not None and "http_client" in inspect.signature(streamable_http_client).parameters:
        kwargs["http_client"] = http_client
    elif settings.access_token and "headers" in inspect.signature(streamable_http_client).parameters:
        kwargs["headers"] = {"Authorization": f"Bearer {settings.access_token}"}

    async with streamable_http_client(settings.endpoint, **kwargs) as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await asyncio.wait_for(session.initialize(), timeout=settings.timeout_seconds)
            yield session
    if http_client is not None:
        await http_client.aclose()


def _create_http_client(settings: LongbridgeMCPSettings):
    try:
        import httpx
    except ModuleNotFoundError as exc:
        raise LongbridgeMCPError("Longbridge MCP OAuth support requires httpx.") from exc

    if settings.access_token:
        return httpx.AsyncClient(
            headers={"Authorization": f"Bearer {settings.access_token}"},
            follow_redirects=True,
            timeout=settings.timeout_seconds,
        )

    return httpx.AsyncClient(
        auth=_create_oauth_provider(settings),
        follow_redirects=True,
        timeout=settings.timeout_seconds,
    )


def _create_oauth_provider(settings: LongbridgeMCPSettings):
    try:
        from mcp.client.auth import OAuthClientProvider
        from mcp.shared.auth import OAuthClientMetadata
        from pydantic import AnyUrl
    except ModuleNotFoundError as exc:
        raise LongbridgeMCPError("Longbridge MCP OAuth support requires the MCP auth dependencies.") from exc

    callback_url = f"http://127.0.0.1:{settings.oauth_callback_port}/callback"
    return OAuthClientProvider(
        server_url=settings.endpoint.removesuffix("/mcp"),
        client_metadata=OAuthClientMetadata(
            client_name="TradingAgents Local Longbridge MCP",
            redirect_uris=[AnyUrl(callback_url)],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            scope="openid profile",
        ),
        storage=_FileTokenStorage(settings.oauth_token_file),
        redirect_handler=_open_authorization_url,
        callback_handler=lambda: _wait_for_oauth_callback(settings.oauth_callback_port),
    )


class _FileTokenStorage:
    def __init__(self, path: str):
        self.path = path
        self.tokens = None
        self.client_info = None
        if os.path.exists(path):
            try:
                from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("tokens"):
                    self.tokens = OAuthToken.model_validate(data["tokens"])
                if data.get("client_info"):
                    self.client_info = OAuthClientInformationFull.model_validate(data["client_info"])
            except Exception:
                self.tokens = None
                self.client_info = None

    def _save(self):
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        data = {
            "tokens": self.tokens.model_dump(mode="json") if self.tokens else None,
            "client_info": self.client_info.model_dump(mode="json") if self.client_info else None,
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    async def get_tokens(self):
        return self.tokens

    async def set_tokens(self, tokens):
        self.tokens = tokens
        self._save()

    async def get_client_info(self):
        return self.client_info

    async def set_client_info(self, client_info):
        self.client_info = client_info
        self._save()


async def _open_authorization_url(auth_url: str):
    print(f"Longbridge MCP authorization required: {auth_url}", flush=True)
    try:
        subprocess.run(["open", auth_url], check=False)
    except Exception:
        pass


async def _wait_for_oauth_callback(port: int):
    loop = asyncio.get_running_loop()
    callback_future = loop.create_future()

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            code = params.get("code", [None])[0]
            state = params.get("state", [None])[0]
            error = params.get("error", [None])[0]
            self.send_response(200 if code or error else 204)
            self.end_headers()
            if (code or error) and not callback_future.done():
                if error:
                    loop.call_soon_threadsafe(callback_future.set_exception, RuntimeError(error))
                else:
                    loop.call_soon_threadsafe(callback_future.set_result, (code, state))

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", port), CallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        return await asyncio.wait_for(callback_future, timeout=300)
    finally:
        server.shutdown()


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
        elif "T" in date_text:
            date_text = date_text[:10]
        if date_text < start_date or date_text > end_date:
            continue
        csv_rows.append(",".join(str(value) for value in (
            date_text,
            row.get("open", ""),
            row.get("high", ""),
            row.get("low", ""),
            row.get("close", ""),
            row.get("volume", ""),
            row.get("turnover", ""),
        )))

    header = f"# Stock data for {symbol} from {start_date} to {end_date}\n"
    header += f"# Data source: Longbridge MCP\n"
    header += f"# Total records: {max(len(csv_rows) - 1, 0)}\n\n"
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
        },
    )
    return _format_candlesticks(normalized_symbol, start_date, end_date, result)


def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    settings = _get_settings()
    normalized_symbol = _normalize_symbol(ticker, settings.default_market)
    result = _call_configured_tool("fundamentals", {"symbols": [normalized_symbol]})
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
    args = {"symbol": normalized_symbol}
    result = _call_configured_tool(key, args)
    return _format_raw_result(f"{key.replace('_', ' ').title()} for {normalized_symbol}", result)


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    settings = _get_settings()
    normalized_symbol = _normalize_symbol(ticker, settings.default_market)
    result = _call_configured_tool(
        "news",
        {"symbol": normalized_symbol},
    )
    return _format_news(f"{normalized_symbol} News, from {start_date} to {end_date}", result)


def get_global_news(curr_date: str, look_back_days: int = 7, limit: int = 50) -> str:
    result = _call_configured_tool(
        "global_news",
        {
            "limit": limit,
        },
    )
    return _format_news(f"Global Market News for {curr_date}", result, limit=limit)


def get_insider_transactions(symbol: str) -> str:
    settings = _get_settings()
    normalized_symbol = _normalize_symbol(symbol, settings.default_market)
    result = _call_configured_tool("insider_transactions", {"symbol": normalized_symbol})
    return _format_raw_result(f"Insider and Executive Data for {normalized_symbol}", result)


def _payload_text(value: Any) -> Any:
    plain = _to_plain_data(value)
    if isinstance(plain, dict) and plain.get("content"):
        content = plain["content"]
        if isinstance(content, list) and content:
            text = content[0].get("text") if isinstance(content[0], dict) else None
            if text:
                return _parse_json_if_possible(text)
    return plain


def get_leap_options_summary(symbol: str, min_expiry: str = "2027-01-01") -> str:
    """Return a compact Longbridge MCP LEAPS/options-flow summary."""
    settings = _get_settings()
    normalized_symbol = _normalize_symbol(symbol, settings.default_market)
    quote = _payload_text(call_mcp_tool("quote", {"symbols": [normalized_symbol]}))
    quote_row = quote[0] if isinstance(quote, list) and quote else {}
    last_done = quote_row.get("last_done")
    expiries = _payload_text(call_mcp_tool("option_chain_expiry_date_list", {"symbol": normalized_symbol}))
    expiries = expiries if isinstance(expiries, list) else []
    leap_expiries = [expiry for expiry in expiries if expiry >= min_expiry]
    selected_expiry = (leap_expiries[-1:] or expiries[-1:] or [None])[0]

    if not selected_expiry:
        return f"# LEAPS/options-flow summary for {normalized_symbol}\n\nData source: Longbridge MCP\n\nNo option expiries found."

    chain = _payload_text(call_mcp_tool("option_chain_info_by_date", {"symbol": normalized_symbol, "date": selected_expiry}))
    chain = chain if isinstance(chain, list) else []
    try:
        spot = float(last_done)
    except (TypeError, ValueError):
        spot = None

    selected_symbols = []
    if spot is not None:
        ranked = []
        for row in chain:
            try:
                ranked.append((abs(float(row["price"]) - spot), float(row["price"]), row))
            except (KeyError, TypeError, ValueError):
                continue
        ranked.sort()
        for _, _, row in ranked[:2]:
            selected_symbols.extend([row["call_symbol"], row["put_symbol"]])
        for threshold in (1.15, 1.35):
            for _, strike, row in ranked:
                if strike >= spot * threshold:
                    selected_symbols.extend([row["call_symbol"], row["put_symbol"]])
                    break

    selected_symbols = list(dict.fromkeys(selected_symbols))
    option_quotes = _payload_text(call_mcp_tool("option_quote", {"symbols": selected_symbols})) if selected_symbols else []
    option_quotes = option_quotes if isinstance(option_quotes, list) else []
    calc = _payload_text(call_mcp_tool(
        "calc_indexes",
        {
            "symbols": selected_symbols,
            "indexes": [
                "LastDone",
                "ChangeRate",
                "Volume",
                "OpenInterest",
                "ImpliedVolatility",
                "Delta",
                "Premium",
                "StrikePrice",
                "ExpiryDate",
            ],
        },
    )) if selected_symbols else []
    calc = calc if isinstance(calc, list) else []
    calc_by_symbol = {row.get("symbol"): row for row in calc if isinstance(row, dict)}

    lines = [
        f"# LEAPS/options-flow summary for {normalized_symbol}",
        "",
        "Data source: Longbridge MCP",
        f"Spot/last_done: {last_done}",
        f"Selected LEAPS expiry: {selected_expiry}",
        "",
        "| Contract | Type | Strike | Last | Volume | OI | IV | Delta | Premium % | Change % |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in option_quotes:
        symbol_key = row.get("symbol")
        c = calc_by_symbol.get(symbol_key, {})
        lines.append(
            "| {symbol} | {direction} | {strike} | {last} | {volume} | {oi} | {iv} | {delta} | {premium} | {change} |".format(
                symbol=symbol_key,
                direction=row.get("direction", ""),
                strike=row.get("strike_price", c.get("strike_price", "")),
                last=row.get("last_done", c.get("last_done", "")),
                volume=row.get("volume", c.get("volume", "")),
                oi=row.get("open_interest", c.get("open_interest", "")),
                iv=row.get("implied_volatility", c.get("implied_volatility", "")),
                delta=c.get("delta", ""),
                premium=c.get("premium", ""),
                change=c.get("change_rate", ""),
            )
        )
    lines.append("")
    lines.append("Data limitations: Longbridge MCP option quotes provide OI, volume, IV, and greeks for selected contracts, but this summary does not prove opening vs closing trades or next-day OI change.")
    return "\n".join(lines)
