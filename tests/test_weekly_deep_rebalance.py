import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

from tradingagents.automation.weekly_deep_rebalance import (
    TickerRunResult,
    _load_result_from_disk,
    build_allocation_markdown,
    build_weekly_config,
    count_leap_chain_unavailable,
    compute_target_weights,
    extract_markdown_section,
    resolve_default_analysis_date,
    run_single_ticker_isolated,
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


def test_build_weekly_config_matches_requested_vendor_policy():
    config = build_weekly_config()
    assert config["output_language"] == "Chinese"
    assert config["max_debate_rounds"] == 2
    assert config["max_risk_discuss_rounds"] == 2
    assert config["data_vendors"]["core_stock_apis"] == "longbridge_mcp,yfinance"
    assert config["data_vendors"]["fundamental_data"] == "longbridge_mcp,yfinance"
    assert config["data_vendors"]["news_data"] == "longbridge_mcp,yfinance"
    assert config["data_vendors"]["technical_indicators"] == "yfinance"
    assert config["disable_yfinance"] is False
    assert config["vendor_auto_fallback"] is False


def test_build_weekly_config_restores_missing_nested_vendor_sections(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.automation.weekly_deep_rebalance.DEFAULT_CONFIG",
        {"output_language": "English"},
    )
    config = build_weekly_config()
    assert config["data_vendors"]["core_stock_apis"] == "longbridge_mcp,yfinance"
    assert config["data_vendors"]["technical_indicators"] == "yfinance"
    assert config["longbridge_mcp"]["default_market"] == "US"


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
    report_dir = tmp_path / "NVDA" / "2026-05-29_20260529_160000"
    analysts_dir = report_dir / "1_analysts"
    analysts_dir.mkdir(parents=True)
    (analysts_dir / "leap.md").write_text("Data source: Longbridge MCP", encoding="utf-8")
    (analysts_dir / "data_sources.md").write_text("Longbridge MCP", encoding="utf-8")
    report = report_dir / "complete_report.md"
    report.write_text("ok", encoding="utf-8")
    results = [
        TickerRunResult(
            ticker="NVDA",
            analysis_date="2026-05-29",
            run_dir=report_dir,
            report_file=report,
            rating="Buy",
            executive_summary="分两笔建仓。",
            verified_files={"1_analysts/leap.md": True, "1_analysts/data_sources.md": True},
            longbridge_mentions={"data_sources": True, "market": False, "news": False, "fundamentals": False, "leap": True},
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
    assert "`data_sources.md` 包含 Longbridge MCP 配置: 1/1" in output
    assert "不能把这些章节里未出现 `Longbridge MCP` 文本解读为“没有使用 Longbridge”" in output


def test_resolve_default_analysis_date_uses_most_recent_friday():
    la = ZoneInfo("America/Los_Angeles")
    assert resolve_default_analysis_date(dt.datetime(2026, 6, 1, 12, 0, tzinfo=la)) == "2026-05-29"
    assert resolve_default_analysis_date(dt.datetime(2026, 5, 29, 20, 0, tzinfo=la)) == "2026-05-29"
    assert resolve_default_analysis_date(dt.datetime(2026, 5, 30, 9, 0, tzinfo=la)) == "2026-05-29"


def test_count_leap_chain_unavailable(tmp_path: Path):
    run_dir = tmp_path / "NVDA" / "2026-05-29_20260529_160000" / "1_analysts"
    run_dir.mkdir(parents=True)
    (run_dir / "leap.md").write_text(
        "# LEAPS/options-flow summary for NVDA\n\nNo option expiries found.",
        encoding="utf-8",
    )
    results = [TickerRunResult(ticker="NVDA", analysis_date="2026-05-29", run_dir=run_dir.parent)]
    assert count_leap_chain_unavailable(results) == 1


def test_run_single_ticker_isolated_returns_timeout_error(monkeypatch, tmp_path: Path):
    class FakeQueue:
        def empty(self) -> bool:
            return True

    class FakeProcess:
        def __init__(self, target, args):
            self.target = target
            self.args = args
            self.exitcode = None
            self._alive = False

        def start(self) -> None:
            self._alive = True

        def join(self, timeout=None) -> None:
            return None

        def is_alive(self) -> bool:
            return self._alive

        def terminate(self) -> None:
            self._alive = False
            self.exitcode = -15

    class FakeContext:
        def Queue(self):
            return FakeQueue()

        def Process(self, target, args):
            return FakeProcess(target, args)

    monkeypatch.setattr(
        "tradingagents.automation.weekly_deep_rebalance.mp.get_context",
        lambda mode: FakeContext(),
    )
    result = run_single_ticker_isolated(
        ticker="NVDA",
        analysis_date="2026-05-29",
        config={},
        reports_root=tmp_path,
        timeout_seconds=1,
    )
    assert result.ticker == "NVDA"
    assert result.errors == ["TimeoutError: exceeded 1s per-ticker limit"]


def test_load_result_from_disk_recovers_completed_report(tmp_path: Path):
    run_dir = tmp_path / "AAPL" / "2026-05-29_20260601_232658"
    analysts_dir = run_dir / "1_analysts"
    analysts_dir.mkdir(parents=True)
    (analysts_dir / "leap.md").write_text("Longbridge MCP", encoding="utf-8")
    (analysts_dir / "data_sources.md").write_text("Longbridge MCP", encoding="utf-8")
    (run_dir / "5_portfolio").mkdir(parents=True)
    (run_dir / "5_portfolio" / "decision.md").write_text(
        "**Rating**: Overweight\n\n**Executive Summary**: Build.\n\n**Investment Thesis**: Quality.",
        encoding="utf-8",
    )
    (run_dir / "complete_report.md").write_text("ok", encoding="utf-8")

    result = _load_result_from_disk("AAPL", "2026-05-29", run_dir)
    assert result is not None
    assert result.report_file == run_dir / "complete_report.md"
    assert result.rating == "Overweight"
    assert result.errors == []
