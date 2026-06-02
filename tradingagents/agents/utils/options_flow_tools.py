from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.longbridge_mcp import (
    LongbridgeMCPError,
    get_leap_options_summary as get_longbridge_leap_options_summary,
)


@tool
def get_leap_options_summary(
    symbol: Annotated[str, "ticker symbol of the company, e.g. ORCL, CRCL, AAPL.US"],
    min_expiry: Annotated[str, "minimum LEAPS expiry date in yyyy-mm-dd format"] = "2027-01-01",
) -> str:
    """Retrieve a Longbridge MCP LEAPS/options-flow summary for a stock."""
    try:
        return get_longbridge_leap_options_summary(symbol, min_expiry=min_expiry)
    except LongbridgeMCPError as exc:
        return (
            f"# LEAPS/options-flow summary for {symbol}\n\n"
            "Data source: Longbridge MCP unavailable\n\n"
            f"Unavailable reason: {exc}\n"
        )
