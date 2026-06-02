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


def test_fetch_returns_passes_yfinance_timeout(monkeypatch):
    calls = []

    class FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, **kwargs):
            calls.append((self.symbol, kwargs))
            import pandas as pd

            return pd.DataFrame({"Close": [100.0, 101.0]})

    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph.config = {"yfinance_timeout": 17}

    monkeypatch.setattr("tradingagents.graph.trading_graph.yf.Ticker", FakeTicker)

    raw, alpha, days = TradingAgentsGraph._fetch_returns(graph, "NVDA", "2026-05-29")

    assert raw == 0.01
    assert alpha == 0.0
    assert days == 1
    assert calls[0][0] == "NVDA"
    assert calls[1][0] == "SPY"
    assert calls[0][1]["timeout"] == 17
    assert calls[1][1]["timeout"] == 17


def test_weekly_config_disables_memory_outcome_resolution():
    config = build_weekly_config()
    assert config["resolve_memory_outcomes"] is False


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
