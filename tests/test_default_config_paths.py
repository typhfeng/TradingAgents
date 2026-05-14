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


def test_default_paths_still_allow_environment_overrides(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CACHE_DIR", "/tmp/ta-cache")
    monkeypatch.setenv("TRADINGAGENTS_RESULTS_DIR", "/tmp/ta-logs")
    monkeypatch.setenv("TRADINGAGENTS_MEMORY_LOG_PATH", "/tmp/ta-memory.md")

    import tradingagents.default_config as default_config

    default_config = importlib.reload(default_config)
    assert default_config.DEFAULT_CONFIG["data_cache_dir"] == "/tmp/ta-cache"
    assert default_config.DEFAULT_CONFIG["results_dir"] == "/tmp/ta-logs"
    assert default_config.DEFAULT_CONFIG["memory_log_path"] == "/tmp/ta-memory.md"
