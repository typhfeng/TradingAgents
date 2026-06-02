from tradingagents.agents.analysts import leap_agent
from tradingagents.dataflows.longbridge_mcp import LongbridgeMCPError


def test_load_options_summary_falls_back_when_longbridge_unavailable(monkeypatch):
    monkeypatch.setattr(
        leap_agent,
        "fetch_leap_options_summary",
        lambda symbol: (_ for _ in ()).throw(LongbridgeMCPError("missing mcp package")),
    )

    summary = leap_agent._load_options_summary("NVDA")

    assert "Data source: Longbridge MCP unavailable" in summary
    assert "missing mcp package" in summary
    assert "NVDA" in summary


def test_options_flow_tool_falls_back_when_longbridge_unavailable(monkeypatch):
    from tradingagents.agents.utils import options_flow_tools

    monkeypatch.setattr(
        options_flow_tools,
        "get_longbridge_leap_options_summary",
        lambda symbol, min_expiry="2027-01-01": (_ for _ in ()).throw(
            LongbridgeMCPError("oauth not configured")
        ),
    )

    summary = options_flow_tools.get_leap_options_summary.invoke({"symbol": "AAPL"})

    assert "Data source: Longbridge MCP unavailable" in summary
    assert "oauth not configured" in summary
