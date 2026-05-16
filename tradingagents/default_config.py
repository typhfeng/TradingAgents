import os

_TRADINGAGENTS_HOME = "/Volumes/ssd2/tradingagents"
_TRADINGAGENTS_CACHE_DIR = os.path.join(_TRADINGAGENTS_HOME, "cache")
_TRADINGAGENTS_LOGS_DIR = os.path.join(_TRADINGAGENTS_HOME, "logs")

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", _TRADINGAGENTS_LOGS_DIR),
    "data_cache_dir": os.getenv("TRADINGAGENTS_CACHE_DIR", _TRADINGAGENTS_CACHE_DIR),
    "memory_log_path": os.getenv("TRADINGAGENTS_MEMORY_LOG_PATH", os.path.join(_TRADINGAGENTS_LOGS_DIR, "memory", "trading_memory.md")),
    # Optional cap on the number of resolved memory log entries. When set,
    # the oldest resolved entries are pruned once this limit is exceeded.
    # Pending entries are never pruned. None disables rotation entirely.
    "memory_log_max_entries": None,
    # LLM settings
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5.4",
    "quick_think_llm": "gpt-5.4-mini",
    # When None, each provider's client falls back to its own default endpoint
    # (api.openai.com for OpenAI, generativelanguage.googleapis.com for Gemini, ...).
    # The CLI overrides this per provider when the user picks one. Keeping a
    # provider-specific URL here would leak (e.g. OpenAI's /v1 was previously
    # being forwarded to Gemini, producing malformed request URLs).
    "backend_url": None,
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    "anthropic_effort": None,           # "high", "medium", "low"
    # Checkpoint/resume: when True, LangGraph saves state after each node
    # so a crashed run can resume from the last successful step.
    "checkpoint_enabled": False,
    # Output language for analyst reports and final decision
    # Internal agent debate stays in English for reasoning quality
    "output_language": "English",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: alpha_vantage, yfinance, longbridge_mcp
        "technical_indicators": "yfinance",  # Options: alpha_vantage, yfinance
        "fundamental_data": "yfinance",      # Options: alpha_vantage, yfinance, longbridge_mcp
        "news_data": "yfinance",             # Options: alpha_vantage, yfinance, longbridge_mcp
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
    # Optional Longbridge MCP configuration.
    # Official docs: https://open.longbridge.com/docs/mcp
    "longbridge_mcp": {
        "endpoint": os.getenv("TRADINGAGENTS_LONGBRIDGE_MCP_URL", "https://openapi.longbridge.com/mcp"),
        # Longbridge MCP uses OAuth 2.1. If your runtime manages OAuth outside
        # this process, provide a bearer token through the environment.
        "access_token": os.getenv("TRADINGAGENTS_LONGBRIDGE_MCP_ACCESS_TOKEN"),
        # Longbridge symbols include region suffixes such as AAPL.US or 700.HK.
        # Set TRADINGAGENTS_LONGBRIDGE_DEFAULT_MARKET=US to map AAPL -> AAPL.US.
        "default_market": os.getenv("TRADINGAGENTS_LONGBRIDGE_DEFAULT_MARKET"),
        "timeout_seconds": float(os.getenv("TRADINGAGENTS_LONGBRIDGE_MCP_TIMEOUT", "30")),
        "oauth_token_file": os.getenv(
            "TRADINGAGENTS_LONGBRIDGE_MCP_TOKEN_FILE",
            os.path.join(_TRADINGAGENTS_CACHE_DIR, "longbridge_mcp_oauth.json"),
        ),
        "oauth_callback_port": int(os.getenv("TRADINGAGENTS_LONGBRIDGE_MCP_CALLBACK_PORT", "8765")),
        "tool_names": {},
        "tool_arguments": {},
    },
}
