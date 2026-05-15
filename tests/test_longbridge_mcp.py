import pytest

from tradingagents.dataflows import longbridge_mcp
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.interface import VENDOR_LIST, VENDOR_METHODS, route_to_vendor


@pytest.fixture(autouse=True)
def _reset_longbridge_config(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_LONGBRIDGE_MCP_URL", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_LONGBRIDGE_MCP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_LONGBRIDGE_DEFAULT_MARKET", raising=False)
    set_config(
        {
            "data_vendors": {
                "core_stock_apis": "yfinance",
                "technical_indicators": "yfinance",
                "fundamental_data": "yfinance",
                "news_data": "yfinance",
            },
            "tool_vendors": {},
            "longbridge_mcp": {
                "endpoint": longbridge_mcp.DEFAULT_ENDPOINT,
                "access_token": None,
                "default_market": None,
                "timeout_seconds": 30,
                "tool_names": {},
                "tool_arguments": {},
            },
        }
    )


@pytest.mark.unit
def test_longbridge_vendor_is_registered_for_read_only_data_tools():
    assert "longbridge_mcp" in VENDOR_LIST
    for method in (
        "get_stock_data",
        "get_fundamentals",
        "get_balance_sheet",
        "get_cashflow",
        "get_income_statement",
        "get_news",
        "get_global_news",
        "get_insider_transactions",
    ):
        assert "longbridge_mcp" in VENDOR_METHODS[method]


@pytest.mark.unit
def test_stock_data_maps_dates_and_default_market(monkeypatch):
    calls = []

    def fake_call(tool_name, arguments):
        calls.append((tool_name, arguments))
        return {
            "candlesticks": [
                {
                    "timestamp": 1714521600,
                    "open": "170.00",
                    "high": "175.00",
                    "low": "169.50",
                    "close": "174.00",
                    "volume": 123,
                    "turnover": "21000.00",
                }
            ]
        }

    monkeypatch.setattr(longbridge_mcp, "call_mcp_tool", fake_call)
    set_config({"longbridge_mcp": {"default_market": "US"}})

    result = longbridge_mcp.get_stock("aapl", "2024-05-01", "2024-05-02")

    assert calls == [
        (
            "history_candlesticks_by_date",
            {
                "period": 1000,
                "adjust_type": 0,
                "symbol": "AAPL.US",
                "query_type": 2,
                "date_request": {"start_date": "20240501", "end_date": "20240502"},
            },
        )
    ]
    assert "# Stock data for AAPL.US from 2024-05-01 to 2024-05-02" in result
    assert "Date,Open,High,Low,Close,Volume,Turnover" in result
    assert "2024-05-01,170.00,175.00,169.50,174.00,123,21000.00" in result


@pytest.mark.unit
def test_news_result_is_formatted(monkeypatch):
    def fake_call(tool_name, arguments):
        assert tool_name == "news_search"
        assert arguments["symbol"] == "700.HK"
        return {
            "news": [
                {
                    "title": "Tencent earnings beat",
                    "source": "Longbridge",
                    "published_at": "2026-05-01",
                    "summary": "Revenue growth improved.",
                    "url": "https://example.test/news",
                }
            ]
        }

    monkeypatch.setattr(longbridge_mcp, "call_mcp_tool", fake_call)

    result = longbridge_mcp.get_news("700.HK", "2026-04-24", "2026-05-01")

    assert "## 700.HK News, from 2026-04-24 to 2026-05-01" in result
    assert "### Tencent earnings beat (Longbridge | 2026-05-01)" in result
    assert "Revenue growth improved." in result


@pytest.mark.unit
def test_route_to_vendor_uses_longbridge_when_configured(monkeypatch):
    monkeypatch.setitem(
        VENDOR_METHODS["get_stock_data"],
        "longbridge_mcp",
        lambda symbol, start_date, end_date: f"longbridge:{symbol}:{start_date}:{end_date}",
    )
    set_config({"data_vendors": {"core_stock_apis": "longbridge_mcp"}})

    assert (
        route_to_vendor("get_stock_data", "NVDA.US", "2026-01-01", "2026-01-31")
        == "longbridge:NVDA.US:2026-01-01:2026-01-31"
    )


@pytest.mark.unit
def test_route_to_vendor_falls_back_after_longbridge_mcp_error(monkeypatch):
    def fail_longbridge(symbol, start_date, end_date):
        raise longbridge_mcp.LongbridgeMCPError("not authenticated")

    monkeypatch.setitem(
        VENDOR_METHODS["get_stock_data"],
        "longbridge_mcp",
        fail_longbridge,
    )
    monkeypatch.setitem(
        VENDOR_METHODS["get_stock_data"],
        "yfinance",
        lambda symbol, start_date, end_date: "fallback-yfinance",
    )
    set_config({"data_vendors": {"core_stock_apis": "longbridge_mcp,yfinance"}})

    assert route_to_vendor("get_stock_data", "NVDA", "2026-01-01", "2026-01-31") == "fallback-yfinance"


@pytest.mark.unit
def test_technical_indicators_do_not_route_to_longbridge():
    assert "longbridge_mcp" not in VENDOR_METHODS["get_indicators"]
