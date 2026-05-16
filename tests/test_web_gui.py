from cli.web import infer_request_params, parse_form, render_markdown_report


def test_parse_form_normalizes_core_fields():
    params = parse_form(
        b"ticker=nvda&analysis_date=2026-01-15&analysts=market&analysts=fundamentals"
        b"&research_depth=3&llm_provider=ollama&quick_think_llm=llama3&deep_think_llm=llama3.1"
        b"&output_language=Chinese&checkpoint_enabled=on"
    )

    assert params["ticker"] == "NVDA"
    assert params["analysis_date"] == "2026-01-15"
    assert params["analysts"] == ["market", "fundamentals"]
    assert params["research_depth"] == 3
    assert params["llm_provider"] == "ollama"
    assert params["backend_url"] == "http://localhost:11434/v1"
    assert params["checkpoint_enabled"] is True


def test_parse_form_accepts_codex_style_request():
    params = parse_form(
        "request_text=用中文分析 NVDA 今天的交易建议，深度 3，包含新闻、市场和基本面，使用 ollama"
        .encode("utf-8")
    )

    assert params["ticker"] == "NVDA"
    assert params["output_language"] == "Chinese"
    assert params["research_depth"] == 3
    assert params["llm_provider"] == "ollama"
    assert params["backend_url"] == "http://localhost:11434/v1"
    assert params["analysts"] == ["market", "news", "fundamentals"]


def test_infer_request_params_handles_yesterday_and_all_analysts():
    params = infer_request_params("分析 AAPL 昨天，全部分析师，英文，最深", today="2026-05-05")

    assert params["ticker"] == "AAPL"
    assert params["analysis_date"] == "2026-05-04"
    assert params["analysts"] == ["market", "social", "news", "fundamentals", "leap"]
    assert params["output_language"] == "English"
    assert params["research_depth"] == 5


def test_render_markdown_report_includes_final_decision_and_available_sections():
    report = render_markdown_report(
        "NVDA",
        "2026-01-15",
        {
            "market_report": "Market report",
            "news_report": "News report",
            "final_trade_decision": "Rating: Buy",
        },
        "BUY",
    )

    assert "# 交易分析报告：NVDA" in report
    assert "## 最终决策\n\nBUY" in report
    assert "## 市场分析\n\nMarket report" in report
    assert "## 新闻分析\n\nNews report" in report
    assert "## 投资组合经理决策\n\nRating: Buy" in report
