from pathlib import Path

from tradingagents.automation.weekly_deep_rebalance import (
    TickerRunResult,
    build_allocation_markdown,
    compute_target_weights,
    extract_markdown_section,
    summarize_longbridge_mentions,
    verify_required_files,
)


def test_extract_markdown_section_reads_until_next_header():
    text = (
        "**Rating**: Overweight\n\n"
        "**Executive Summary**: Build in two tranches.\nSecond sentence.\n\n"
        "**Investment Thesis**: Demand is improving."
    )
    assert extract_markdown_section(text, "Executive Summary") == "Build in two tranches.\nSecond sentence."


def test_compute_target_weights_prefers_googl_over_goog():
    results = [
        TickerRunResult(ticker="GOOGL", analysis_date="2026-05-29", rating="Overweight"),
        TickerRunResult(ticker="GOOG", analysis_date="2026-05-29", rating="Buy"),
        TickerRunResult(ticker="NVDA", analysis_date="2026-05-29", rating="Buy"),
        TickerRunResult(ticker="AAPL", analysis_date="2026-05-29", rating="Hold"),
    ]
    weights = compute_target_weights(results)
    assert weights["GOOG"] == 0.0
    assert weights["GOOGL"] > 0.0
    assert weights["NVDA"] > weights["GOOGL"]
    assert round(sum(weights.values()), 2) == 100.0


def test_verify_required_files_and_longbridge_mentions(tmp_path: Path):
    run_dir = tmp_path / "NVDA" / "2026-05-29_20260529_160000"
    analysts_dir = run_dir / "1_analysts"
    analysts_dir.mkdir(parents=True)
    (analysts_dir / "leap.md").write_text("Data source: Longbridge MCP", encoding="utf-8")
    (analysts_dir / "data_sources.md").write_text("Longbridge MCP", encoding="utf-8")
    (analysts_dir / "market.md").write_text("fallback yfinance", encoding="utf-8")
    checks = verify_required_files(run_dir)
    mentions = summarize_longbridge_mentions(run_dir)
    assert checks == {
        "1_analysts/leap.md": True,
        "1_analysts/data_sources.md": True,
    }
    assert mentions["leap"] is True
    assert mentions["data_sources"] is True
    assert mentions["market"] is False


def test_build_allocation_markdown_includes_zero_weight_summary(tmp_path: Path):
    report = tmp_path / "NVDA" / "complete_report.md"
    report.parent.mkdir(parents=True)
    report.write_text("ok", encoding="utf-8")
    results = [
        TickerRunResult(
            ticker="NVDA",
            analysis_date="2026-05-29",
            report_file=report,
            rating="Buy",
            executive_summary="分两笔建仓。",
            verified_files={"1_analysts/leap.md": True, "1_analysts/data_sources.md": True},
            longbridge_mentions={"data_sources": True, "market": True, "news": False, "fundamentals": True, "leap": True},
        ),
        TickerRunResult(
            ticker="AAPL",
            analysis_date="2026-05-29",
            rating="Underweight",
            verified_files={"1_analysts/leap.md": True, "1_analysts/data_sources.md": True},
            longbridge_mentions={"data_sources": True, "market": False, "news": False, "fundamentals": False, "leap": False},
        ),
    ]
    output = build_allocation_markdown("2026-05-29", results, tmp_path / "alloc.md")
    assert "NVDA (100.00%)" in output
    assert "AAPL (Underweight)" in output
    assert str(report) in output
