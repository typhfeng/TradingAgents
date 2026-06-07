from typing import Annotated

# Import from vendor-specific modules
from .y_finance import (
    get_YFin_data_online,
    get_stock_stats_indicators_window,
    get_fundamentals as get_yfinance_fundamentals,
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
)
from .yfinance_news import get_news_yfinance, get_global_news_yfinance
from .alpha_vantage import (
    get_stock as get_alpha_vantage_stock,
    get_indicator as get_alpha_vantage_indicator,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_income_statement as get_alpha_vantage_income_statement,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news,
    get_global_news as get_alpha_vantage_global_news,
)
from .alpha_vantage_common import AlphaVantageRateLimitError
from .longbridge_mcp import (
    LongbridgeMCPError,
    get_indicator as get_longbridge_mcp_indicator,
    get_stock as get_longbridge_mcp_stock,
    get_fundamentals as get_longbridge_mcp_fundamentals,
    get_balance_sheet as get_longbridge_mcp_balance_sheet,
    get_cashflow as get_longbridge_mcp_cashflow,
    get_income_statement as get_longbridge_mcp_income_statement,
    get_news as get_longbridge_mcp_news,
    get_global_news as get_longbridge_mcp_global_news,
    get_insider_transactions as get_longbridge_mcp_insider_transactions,
)
from .stockstats_utils import YahooFinanceError

# Configuration and routing logic
from .config import get_config

# Tools organized by category
TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV stock price data",
        "tools": [
            "get_stock_data"
        ]
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": [
            "get_indicators"
        ]
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement"
        ]
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
        ]
    }
}

VENDOR_LIST = [
    "yfinance",
    "alpha_vantage",
    "longbridge_mcp",
]

# Mapping of methods to their vendor-specific implementations
VENDOR_METHODS = {
    # core_stock_apis
    "get_stock_data": {
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
        "longbridge_mcp": get_longbridge_mcp_stock,
    },
    # technical_indicators
    "get_indicators": {
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
        "longbridge_mcp": get_longbridge_mcp_indicator,
    },
    # fundamental_data
    "get_fundamentals": {
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "yfinance": get_yfinance_fundamentals,
        "longbridge_mcp": get_longbridge_mcp_fundamentals,
    },
    "get_balance_sheet": {
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
        "longbridge_mcp": get_longbridge_mcp_balance_sheet,
    },
    "get_cashflow": {
        "alpha_vantage": get_alpha_vantage_cashflow,
        "yfinance": get_yfinance_cashflow,
        "longbridge_mcp": get_longbridge_mcp_cashflow,
    },
    "get_income_statement": {
        "alpha_vantage": get_alpha_vantage_income_statement,
        "yfinance": get_yfinance_income_statement,
        "longbridge_mcp": get_longbridge_mcp_income_statement,
    },
    # news_data
    "get_news": {
        "alpha_vantage": get_alpha_vantage_news,
        "yfinance": get_news_yfinance,
        "longbridge_mcp": get_longbridge_mcp_news,
    },
    "get_global_news": {
        "yfinance": get_global_news_yfinance,
        "alpha_vantage": get_alpha_vantage_global_news,
        "longbridge_mcp": get_longbridge_mcp_global_news,
    },
    "get_insider_transactions": {
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
        "longbridge_mcp": get_longbridge_mcp_insider_transactions,
    },
}

def describe_data_sources() -> str:
    """Return a human-readable summary of configured data vendors."""
    config = get_config()
    data_vendors = config.get("data_vendors", {})
    tool_vendors = config.get("tool_vendors", {})
    lines = ["# Data Sources"]
    for category in TOOLS_CATEGORIES:
        vendor = data_vendors.get(category, "default")
        lines.append(f"- {category}: {vendor}")
    if tool_vendors:
        lines.append("- tool overrides:")
        for method, vendor in sorted(tool_vendors.items()):
            lines.append(f"  - {method}: {vendor}")
    if any("longbridge_mcp" in str(v) for v in list(data_vendors.values()) + list(tool_vendors.values())):
        lb_config = config.get("longbridge_mcp", {})
        endpoint = lb_config.get("endpoint", "https://openapi.longbridge.com/mcp")
        token_file = lb_config.get("oauth_token_file")
        lines.append(f"- longbridge_mcp endpoint: {endpoint}")
        if token_file:
            lines.append(f"- longbridge_mcp oauth_token_file: {token_file}")
        lines.append("- longbridge_mcp evidence: Longbridge MCP responses include 'Data source: Longbridge MCP' in formatted stock data headers.")
    return "\n".join(lines)

def get_category_for_method(method: str) -> str:
    """Get the category that contains the specified method."""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")

def get_vendor(category: str, method: str = None) -> str:
    """Get the configured vendor for a data category or specific tool method.
    Tool-level configuration takes precedence over category-level.
    """
    config = get_config()

    # Check tool-level configuration first (if method provided)
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    # Fall back to category-level configuration
    return config.get("data_vendors", {}).get(category, "default")


def _build_vendor_chain(method: str, vendor_config: str) -> list[str]:
    config = get_config()
    disable_yfinance = bool(config.get("disable_yfinance", False))
    auto_fallback = bool(config.get("vendor_auto_fallback", True))

    configured = [v.strip() for v in vendor_config.split(",") if v.strip()]
    if auto_fallback:
        for vendor in VENDOR_METHODS[method]:
            if vendor not in configured:
                configured.append(vendor)

    if disable_yfinance:
        configured = [vendor for vendor in configured if vendor != "yfinance"]
    return configured

def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to appropriate vendor implementation with fallback support."""
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    fallback_vendors = _build_vendor_chain(method, vendor_config)
    errors: list[str] = []

    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        try:
            return impl_func(*args, **kwargs)
        except AlphaVantageRateLimitError as exc:
            errors.append(f"{vendor}: {type(exc).__name__}: {exc}")
            continue  # Only rate limits trigger fallback
        except LongbridgeMCPError as exc:
            errors.append(f"{vendor}: {type(exc).__name__}: {exc}")
            continue  # MCP connection/auth/runtime availability issues trigger fallback
        except YahooFinanceError as exc:
            errors.append(f"{vendor}: {type(exc).__name__}: {exc}")
            continue  # Yahoo session/rate/auth failures should not block other vendors

    details = "; ".join(errors) if errors else "no configured vendor succeeded"
    raise RuntimeError(f"No available vendor for '{method}': {details}")
