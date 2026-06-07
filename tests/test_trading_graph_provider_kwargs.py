from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.automation.weekly_deep_rebalance import build_weekly_config


def test_get_provider_kwargs_includes_transport_settings():
    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph.config = {
        "llm_provider": "openai",
        "llm_timeout": 90,
        "llm_max_retries": 4,
        "openai_reasoning_effort": "medium",
    }

    kwargs = TradingAgentsGraph._get_provider_kwargs(graph)

    assert kwargs["timeout"] == 90
    assert kwargs["max_retries"] == 4
    assert kwargs["reasoning_effort"] == "medium"


def test_get_provider_kwargs_omits_none_transport_settings():
    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph.config = {
        "llm_provider": "google",
        "llm_timeout": None,
        "llm_max_retries": None,
        "google_thinking_level": "high",
    }

    kwargs = TradingAgentsGraph._get_provider_kwargs(graph)

    assert "timeout" not in kwargs
    assert "max_retries" not in kwargs
    assert kwargs["thinking_level"] == "high"


def test_fetch_returns_uses_stock_data_router(monkeypatch):
    calls = []

    def fake_route(method, symbol, start_date, end_date):
        calls.append((method, symbol, start_date, end_date))
        return "Date,Open,High,Low,Close,Volume\n2026-05-29,100,101,99,100,10\n2026-05-30,101,102,100,101,11\n"

    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph.config = {}

    monkeypatch.setattr("tradingagents.graph.trading_graph.route_to_vendor", fake_route)

    raw, alpha, days = TradingAgentsGraph._fetch_returns(graph, "NVDA", "2026-05-29")

    assert raw == 0.01
    assert alpha == 0.0
    assert days == 1
    assert calls == [
        ("get_stock_data", "NVDA", "2026-05-29", "2026-06-10"),
        ("get_stock_data", "SPY", "2026-05-29", "2026-06-10"),
    ]


def test_weekly_config_disables_memory_outcome_resolution():
    config = build_weekly_config()
    assert config["resolve_memory_outcomes"] is False
    assert config["disable_yfinance"] is True
    assert config["vendor_auto_fallback"] is False
    assert config["data_vendors"]["technical_indicators"] == "longbridge_mcp"


def test_propagate_skips_memory_resolution_when_disabled(monkeypatch):
    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph.config = {"resolve_memory_outcomes": False, "checkpoint_enabled": False}
    graph.workflow = type("Workflow", (), {"compile": lambda self, **kwargs: None})()
    graph.graph = None
    graph._checkpointer_ctx = None

    called = {"resolve": False, "run": False}

    def fake_resolve(ticker):
        called["resolve"] = True

    def fake_run(company_name, trade_date):
        called["run"] = True
        return {"ok": True}, "signal"

    graph._resolve_pending_entries = fake_resolve
    graph._run_graph = fake_run

    result = TradingAgentsGraph.propagate(graph, "NVDA", "2026-05-29")

    assert called["resolve"] is False
    assert called["run"] is True
    assert result == ({"ok": True}, "signal")
