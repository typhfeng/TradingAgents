import importlib

import pytest


@pytest.fixture(autouse=True)
def _restore_default_config(monkeypatch):
    yield
    monkeypatch.delenv("TRADINGAGENTS_CACHE_DIR", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_RESULTS_DIR", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_MEMORY_LOG_PATH", raising=False)
    import tradingagents.default_config as default_config

    importlib.reload(default_config)


def test_default_cache_and_logs_paths(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_CACHE_DIR", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_RESULTS_DIR", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_MEMORY_LOG_PATH", raising=False)

    import tradingagents.default_config as default_config

    default_config = importlib.reload(default_config)
    assert default_config.DEFAULT_CONFIG["data_cache_dir"] == "/Volumes/ssd2/tradingagents/cache"
    assert default_config.DEFAULT_CONFIG["results_dir"] == "/Volumes/ssd2/tradingagents/logs"
    assert (
        default_config.DEFAULT_CONFIG["memory_log_path"]
        == "/Volumes/ssd2/tradingagents/logs/memory/trading_memory.md"
    )
    assert (
        default_config.DEFAULT_CONFIG["longbridge_mcp"]["oauth_token_file"]
        == "/Volumes/ssd2/tradingagents/cache/longbridge_mcp_oauth.json"
    )


def test_default_paths_still_allow_environment_overrides(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CACHE_DIR", "/tmp/ta-cache")
    monkeypatch.setenv("TRADINGAGENTS_RESULTS_DIR", "/tmp/ta-logs")
    monkeypatch.setenv("TRADINGAGENTS_MEMORY_LOG_PATH", "/tmp/ta-memory.md")

    import tradingagents.default_config as default_config

    default_config = importlib.reload(default_config)
    assert default_config.DEFAULT_CONFIG["data_cache_dir"] == "/tmp/ta-cache"
    assert default_config.DEFAULT_CONFIG["results_dir"] == "/tmp/ta-logs"
    assert default_config.DEFAULT_CONFIG["memory_log_path"] == "/tmp/ta-memory.md"


def test_llm_transport_defaults_and_overrides(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_LLM_TIMEOUT", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_LLM_MAX_RETRIES", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_RESOLVE_MEMORY_OUTCOMES", raising=False)

    import tradingagents.default_config as default_config

    default_config = importlib.reload(default_config)
    assert default_config.DEFAULT_CONFIG["llm_timeout"] == 180.0
    assert default_config.DEFAULT_CONFIG["llm_max_retries"] == 2
    assert default_config.DEFAULT_CONFIG["resolve_memory_outcomes"] is True

    monkeypatch.setenv("TRADINGAGENTS_LLM_TIMEOUT", "45")
    monkeypatch.setenv("TRADINGAGENTS_LLM_MAX_RETRIES", "5")
    monkeypatch.setenv("TRADINGAGENTS_YFINANCE_TIMEOUT", "12")
    monkeypatch.setenv("TRADINGAGENTS_RESOLVE_MEMORY_OUTCOMES", "false")
    default_config = importlib.reload(default_config)
    assert default_config.DEFAULT_CONFIG["llm_timeout"] == 45.0
    assert default_config.DEFAULT_CONFIG["llm_max_retries"] == 5
    assert default_config.DEFAULT_CONFIG["yfinance_timeout"] == 12.0
    assert default_config.DEFAULT_CONFIG["resolve_memory_outcomes"] is False
