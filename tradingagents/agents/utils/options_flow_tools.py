from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.longbridge_mcp import get_leap_options_summary as get_longbridge_leap_options_summary


@tool
def get_leap_options_summary(
    symbol: Annotated[str, "ticker symbol of the company, e.g. ORCL, CRCL, AAPL.US"],
    min_expiry: Annotated[str, "minimum LEAPS expiry date in yyyy-mm-dd format"] = "2027-01-01",
) -> str:
    """Retrieve a Longbridge MCP LEAPS/options-flow summary for a stock."""
    return get_longbridge_leap_options_summary(symbol, min_expiry=min_expiry)
