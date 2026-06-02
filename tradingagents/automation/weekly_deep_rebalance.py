from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import multiprocessing as mp
import re
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from tradingagents.agents.utils.rating import parse_rating
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

load_dotenv()
load_dotenv(".env.enterprise", override=False)

TICKER_UNIVERSE = [
    "NVDA", "AAPL", "MSFT", "AMZN", "MU", "GOOGL", "TSLA", "GOOG", "AMD",
    "AVGO", "WMT", "BE", "CRDO", "FN", "STRL", "SATS", "INTC", "PLUG", "F",
    "ONDS", "POET", "AAL", "SOFI", "IREN", "NU",
]

SELECTED_ANALYSTS = ["market", "news", "fundamentals", "leap"]
REQUIRED_REPORT_FILES = ("1_analysts/leap.md", "1_analysts/data_sources.md")
POSITIVE_RATINGS = {"Buy", "Overweight"}
ZERO_WEIGHT_RATINGS = {"Hold", "Underweight", "Sell"}
RATING_SCORES = {"Buy": 2, "Overweight": 1}
REPORTS_ROOT = Path("/Volumes/ssd2/tradingagents/logs/reports")
OUTPUT_ROOT = Path("/Volumes/ssd2/tradingagents/output")
LOS_ANGELES = ZoneInfo("America/Los_Angeles")
DEFAULT_PER_TICKER_TIMEOUT_SECONDS = 900


@dataclass
class TickerRunResult:
    ticker: str
    analysis_date: str
    run_dir: Path | None = None
    report_file: Path | None = None
    rating: str = "Hold"
    decision_markdown: str = ""
    executive_summary: str = ""
    implementation_notes: str = ""
    longbridge_mentions: dict[str, bool] = field(default_factory=dict)
    verified_files: dict[str, bool] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.report_file is not None and not self.errors


def build_weekly_config() -> dict:
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["output_language"] = "Chinese"
    config["max_debate_rounds"] = 2
    config["max_risk_discuss_rounds"] = 2
    config["data_vendors"]["core_stock_apis"] = "longbridge_mcp,yfinance"
    config["data_vendors"]["fundamental_data"] = "longbridge_mcp,yfinance"
    config["data_vendors"]["news_data"] = "longbridge_mcp,yfinance"
    config["data_vendors"]["technical_indicators"] = "yfinance"
    config["resolve_memory_outcomes"] = False
    config["longbridge_mcp"]["default_market"] = (
        config["longbridge_mcp"].get("default_market") or "US"
    )
    return config


def extract_markdown_section(text: str, label: str) -> str:
    pattern = re.compile(
        rf"\*\*{re.escape(label)}\*\*:\s*(.*?)(?=\n\*\*[A-Za-z ][A-Za-z ]*\*\*:|\Z)",
        re.DOTALL,
    )
    match = pattern.search(text or "")
    if not match:
        return ""
    return match.group(1).strip()


def save_report_to_disk(final_state: dict, ticker: str, save_path: Path) -> Path:
    """Persist the report tree using the same layout as the interactive CLI."""
    save_path.mkdir(parents=True, exist_ok=True)
    sections = []

    if final_state.get("data_sources_report"):
        sections.append(f"## Data Sources\n\n{final_state['data_sources_report']}")

    analysts_dir = save_path / "1_analysts"
    analyst_parts = []
    if final_state.get("market_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "market.md").write_text(final_state["market_report"], encoding="utf-8")
        analyst_parts.append(("Market Analyst", final_state["market_report"]))
    if final_state.get("sentiment_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "sentiment.md").write_text(final_state["sentiment_report"], encoding="utf-8")
        analyst_parts.append(("Social Analyst", final_state["sentiment_report"]))
    if final_state.get("news_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "news.md").write_text(final_state["news_report"], encoding="utf-8")
        analyst_parts.append(("News Analyst", final_state["news_report"]))
    if final_state.get("fundamentals_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "fundamentals.md").write_text(final_state["fundamentals_report"], encoding="utf-8")
        analyst_parts.append(("Fundamentals Analyst", final_state["fundamentals_report"]))
    if final_state.get("leap_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "leap.md").write_text(final_state["leap_report"], encoding="utf-8")
        analyst_parts.append(("LEAPS Analyst", final_state["leap_report"]))
    if final_state.get("data_sources_report"):
        analysts_dir.mkdir(exist_ok=True)
        (analysts_dir / "data_sources.md").write_text(final_state["data_sources_report"], encoding="utf-8")
    if analyst_parts:
        content = "\n\n".join(f"### {name}\n{text}" for name, text in analyst_parts)
        sections.append(f"## I. Analyst Team Reports\n\n{content}")

    if final_state.get("investment_debate_state"):
        research_dir = save_path / "2_research"
        debate = final_state["investment_debate_state"]
        research_parts = []
        if debate.get("bull_history"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "bull.md").write_text(debate["bull_history"], encoding="utf-8")
            research_parts.append(("Bull Researcher", debate["bull_history"]))
        if debate.get("bear_history"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "bear.md").write_text(debate["bear_history"], encoding="utf-8")
            research_parts.append(("Bear Researcher", debate["bear_history"]))
        if debate.get("judge_decision"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "manager.md").write_text(debate["judge_decision"], encoding="utf-8")
            research_parts.append(("Research Manager", debate["judge_decision"]))
        if research_parts:
            content = "\n\n".join(f"### {name}\n{text}" for name, text in research_parts)
            sections.append(f"## II. Research Team Decision\n\n{content}")

    if final_state.get("trader_investment_plan"):
        trading_dir = save_path / "3_trading"
        trading_dir.mkdir(exist_ok=True)
        (trading_dir / "trader.md").write_text(final_state["trader_investment_plan"], encoding="utf-8")
        sections.append(f"## III. Trading Team Plan\n\n### Trader\n{final_state['trader_investment_plan']}")

    if final_state.get("risk_debate_state"):
        risk_dir = save_path / "4_risk"
        risk = final_state["risk_debate_state"]
        risk_parts = []
        if risk.get("aggressive_history"):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "aggressive.md").write_text(risk["aggressive_history"], encoding="utf-8")
            risk_parts.append(("Aggressive Analyst", risk["aggressive_history"]))
        if risk.get("conservative_history"):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "conservative.md").write_text(risk["conservative_history"], encoding="utf-8")
            risk_parts.append(("Conservative Analyst", risk["conservative_history"]))
        if risk.get("neutral_history"):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "neutral.md").write_text(risk["neutral_history"], encoding="utf-8")
            risk_parts.append(("Neutral Analyst", risk["neutral_history"]))
        if risk_parts:
            content = "\n\n".join(f"### {name}\n{text}" for name, text in risk_parts)
            sections.append(f"## IV. Risk Management Team Decision\n\n{content}")
        if risk.get("judge_decision"):
            portfolio_dir = save_path / "5_portfolio"
            portfolio_dir.mkdir(exist_ok=True)
            (portfolio_dir / "decision.md").write_text(risk["judge_decision"], encoding="utf-8")
            sections.append(f"## V. Portfolio Manager Decision\n\n### Portfolio Manager\n{risk['judge_decision']}")

    header = (
        f"# Trading Analysis Report: {ticker}\n\n"
        f"Generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    report_path = save_path / "complete_report.md"
    report_path.write_text(header + "\n\n".join(sections), encoding="utf-8")
    return report_path


def summarize_longbridge_mentions(run_dir: Path) -> dict[str, bool]:
    files = {
        "market": run_dir / "1_analysts" / "market.md",
        "news": run_dir / "1_analysts" / "news.md",
        "fundamentals": run_dir / "1_analysts" / "fundamentals.md",
        "leap": run_dir / "1_analysts" / "leap.md",
        "data_sources": run_dir / "1_analysts" / "data_sources.md",
    }
    mentions: dict[str, bool] = {}
    for name, path in files.items():
        if not path.exists():
            mentions[name] = False
            continue
        mentions[name] = "Longbridge MCP" in path.read_text(encoding="utf-8")
    return mentions


def verify_required_files(run_dir: Path) -> dict[str, bool]:
    return {
        relative_path: (run_dir / relative_path).exists()
        for relative_path in REQUIRED_REPORT_FILES
    }


def resolve_default_analysis_date(now: dt.datetime | None = None) -> str:
    """Default to the most recent Friday in Los Angeles time.

    The weekly automation is intended to run after the US Friday market close.
    When invoked manually on other days, using "today" produces misleading dates
    such as Saturday/Sunday/Monday. This helper keeps the batch anchored to the
    latest intended weekly analysis date.
    """
    now = now.astimezone(LOS_ANGELES) if now else dt.datetime.now(LOS_ANGELES)
    days_since_friday = (now.weekday() - 4) % 7
    return (now.date() - dt.timedelta(days=days_since_friday)).isoformat()


def count_leap_chain_unavailable(results: Iterable[TickerRunResult]) -> int:
    count = 0
    for result in results:
        run_dir = result.run_dir
        if not run_dir:
            continue
        leap_path = run_dir / "1_analysts" / "leap.md"
        if not leap_path.exists():
            continue
        if "No option expiries found." in leap_path.read_text(encoding="utf-8"):
            count += 1
    return count


def compute_target_weights(results: Iterable[TickerRunResult]) -> dict[str, float]:
    results_by_ticker = {result.ticker: result for result in results}
    eligible: list[TickerRunResult] = [
        result
        for result in results_by_ticker.values()
        if result.rating in POSITIVE_RATINGS and result.errors == []
    ]
    if "GOOGL" in results_by_ticker and "GOOG" in results_by_ticker:
        googl = results_by_ticker["GOOGL"]
        goog = results_by_ticker["GOOG"]
        if googl in eligible and goog in eligible:
            eligible = [result for result in eligible if result.ticker != "GOOG"]

    scores = {result.ticker: RATING_SCORES.get(result.rating, 0) for result in eligible}
    total_score = sum(scores.values())

    weights = {ticker: 0.0 for ticker in results_by_ticker}
    if total_score <= 0:
        return weights

    ranked = sorted(eligible, key=lambda item: (-scores[item.ticker], item.ticker))
    remainder = 10000
    for index, result in enumerate(ranked):
        if index == len(ranked) - 1:
            basis_points = remainder
        else:
            basis_points = int(round(scores[result.ticker] * 10000 / total_score))
            remainder -= basis_points
        weights[result.ticker] = basis_points / 100
    return weights


def build_allocation_markdown(
    analysis_date: str,
    results: list[TickerRunResult],
    allocation_path: Path,
) -> str:
    weights = compute_target_weights(results)
    positive = [
        result for result in results
        if weights.get(result.ticker, 0.0) > 0
    ]
    zero_weight = [result for result in results if weights.get(result.ticker, 0.0) == 0.0]
    top_buys = ", ".join(f"{result.ticker} ({weights[result.ticker]:.2f}%)" for result in positive) or "无"
    zero_weight_summary = ", ".join(
        f"{result.ticker} ({result.rating})" for result in zero_weight
    ) or "无"

    total_reports = len(results)
    generated_reports = sum(result.report_file is not None for result in results)
    verified_reports = sum(
        bool(result.verified_files) and all(result.verified_files.values())
        for result in results
        if result.report_file is not None
    )
    longbridge_configured = sum(
        result.longbridge_mentions.get("data_sources", False) for result in results
    )
    longbridge_leap = sum(result.longbridge_mentions.get("leap", False) for result in results)
    leap_chain_unavailable = count_leap_chain_unavailable(results)

    error_lines = []
    for result in results:
        if result.errors:
            error_lines.append(f"- {result.ticker}: {result.errors[0]}")
        elif not all(result.verified_files.values()):
            missing = [path for path, exists in result.verified_files.items() if not exists]
            error_lines.append(f"- {result.ticker}: 缺少 {', '.join(missing)}")
    if not error_lines:
        error_lines.append("- 无")

    lines = [
        f"# Target Allocation - {analysis_date}",
        "",
        "## Assumptions",
        "- 组合目标总仓位为 100%。",
        "- `Underweight`、`Hold`、`Sell` 均按 0% 处理。",
        "- `Buy` 与 `Overweight` 视为可分配标的，`Buy` 的分配分值为 2，`Overweight` 的分配分值为 1。",
        "- 若 `GOOGL` 与 `GOOG` 同时为正向评级，仅保留 `GOOGL` 的经济敞口，`GOOG` 记为 0%。",
        "",
        "## Longbridge MCP Adoption",
        f"- 报告检查数: {total_reports}",
        f"- 已生成报告: {generated_reports}/{total_reports}",
        f"- `leap.md` 与 `data_sources.md` 校验通过: {verified_reports}/{generated_reports if generated_reports else 0}",
        f"- `data_sources.md` 包含 Longbridge MCP 配置: {longbridge_configured}/{generated_reports if generated_reports else 0}",
        f"- `leap.md` 显式引用 Longbridge MCP: {longbridge_leap}/{generated_reports if generated_reports else 0}",
        f"- LEAPS 链不可用（`No option expiries found.`）: {leap_chain_unavailable}/{generated_reports if generated_reports else 0}",
        "- 重要限制: analyst markdown 不保留逐次 market/news/fundamentals 工具调用的 vendor provenance，",
        "  因此不能把这些章节里未出现 `Longbridge MCP` 文本解读为“没有使用 Longbridge”。",
        "",
        "## Target Weights",
        "| Ticker | Rating | Target Weight | Key Execution Notes | Report Path |",
        "| --- | --- | ---: | --- | --- |",
    ]

    for result in results:
        report_path = str(result.report_file) if result.report_file else "ERROR"
        lines.append(
            f"| {result.ticker} | {result.rating} | {weights.get(result.ticker, 0.0):.2f}% | "
            f"{(result.executive_summary or result.implementation_notes or 'N/A').replace('|', '/')} | "
            f"{report_path} |"
        )

    lines.extend([
        "",
        "## Implementation Notes",
        "- 非零权重仅分配给正向评级标的，确保总和精确为 100%。",
        "- 若报告中缺少 Longbridge 证据字段，不代表一定未调用 Longbridge；也可能是运行时回退至 yfinance 或模型未在对应章节显式引用。",
        f"- 目标配置文件路径: {allocation_path}",
        "",
        "## Report Links",
    ])
    for result in results:
        if result.report_file is None:
            lines.append(f"- {result.ticker}: ERROR")
        else:
            lines.append(f"- {result.ticker}: {result.report_file}")

    lines.extend([
        "",
        "## Final Summary",
        f"- Top buys: {top_buys}",
        f"- Holds/zero weights: {zero_weight_summary}",
        "- Errors/data-source gaps:",
        *error_lines,
    ])

    return "\n".join(lines) + "\n"


def run_single_ticker(
    ticker: str,
    analysis_date: str,
    config: dict,
    reports_root: Path,
) -> TickerRunResult:
    timestamp = dt.datetime.now(LOS_ANGELES).strftime("%Y%m%d_%H%M%S")
    run_dir = reports_root / ticker / f"{analysis_date}_{timestamp}"
    return run_single_ticker_at_dir(
        ticker=ticker,
        analysis_date=analysis_date,
        config=config,
        run_dir=run_dir,
    )


def run_single_ticker_at_dir(
    ticker: str,
    analysis_date: str,
    config: dict,
    run_dir: Path,
) -> TickerRunResult:
    result = TickerRunResult(ticker=ticker, analysis_date=analysis_date, run_dir=run_dir)
    try:
        graph = TradingAgentsGraph(
            selected_analysts=SELECTED_ANALYSTS,
            config=config,
            debug=False,
        )
        final_state, _ = graph.propagate(ticker, analysis_date)
        report_file = save_report_to_disk(final_state, ticker, run_dir)
        decision_markdown = final_state.get("final_trade_decision", "")
        result.report_file = report_file
        result.decision_markdown = decision_markdown
        result.rating = parse_rating(decision_markdown)
        result.executive_summary = extract_markdown_section(decision_markdown, "Executive Summary")
        result.implementation_notes = extract_markdown_section(decision_markdown, "Investment Thesis")
        result.verified_files = verify_required_files(run_dir)
        result.longbridge_mentions = summarize_longbridge_mentions(run_dir)
        missing = [path for path, exists in result.verified_files.items() if not exists]
        if missing:
            result.errors.append(f"missing required files: {', '.join(missing)}")
        return result
    except Exception as exc:
        result.errors.append(f"{type(exc).__name__}: {exc}")
        result.errors.append(traceback.format_exc(limit=5))
        return result


def _run_single_ticker_worker(
    queue: mp.queues.Queue,
    ticker: str,
    analysis_date: str,
    config: dict,
    run_dir: str,
) -> None:
    result = run_single_ticker_at_dir(
        ticker=ticker,
        analysis_date=analysis_date,
        config=config,
        run_dir=Path(run_dir),
    )
    queue.put(
        {
            "ticker": result.ticker,
            "analysis_date": result.analysis_date,
            "run_dir": str(result.run_dir) if result.run_dir else None,
            "report_file": str(result.report_file) if result.report_file else None,
            "rating": result.rating,
            "decision_markdown": result.decision_markdown,
            "executive_summary": result.executive_summary,
            "implementation_notes": result.implementation_notes,
            "longbridge_mentions": result.longbridge_mentions,
            "verified_files": result.verified_files,
            "errors": result.errors,
        }
    )


def _load_result_from_disk(
    ticker: str,
    analysis_date: str,
    run_dir: Path,
) -> TickerRunResult | None:
    report_file = run_dir / "complete_report.md"
    decision_file = run_dir / "5_portfolio" / "decision.md"
    if not report_file.exists():
        return None

    decision_markdown = decision_file.read_text(encoding="utf-8") if decision_file.exists() else ""
    result = TickerRunResult(
        ticker=ticker,
        analysis_date=analysis_date,
        run_dir=run_dir,
        report_file=report_file,
        decision_markdown=decision_markdown,
        rating=parse_rating(decision_markdown),
        executive_summary=extract_markdown_section(decision_markdown, "Executive Summary"),
        implementation_notes=extract_markdown_section(decision_markdown, "Investment Thesis"),
        verified_files=verify_required_files(run_dir),
        longbridge_mentions=summarize_longbridge_mentions(run_dir),
    )
    missing = [path for path, exists in result.verified_files.items() if not exists]
    if missing:
        result.errors.append(f"missing required files: {', '.join(missing)}")
    return result


def run_single_ticker_isolated(
    ticker: str,
    analysis_date: str,
    config: dict,
    reports_root: Path,
    timeout_seconds: int,
) -> TickerRunResult:
    timestamp = dt.datetime.now(LOS_ANGELES).strftime("%Y%m%d_%H%M%S")
    run_dir = reports_root / ticker / f"{analysis_date}_{timestamp}"
    ctx = mp.get_context("spawn")
    queue = ctx.Queue()
    process = ctx.Process(
        target=_run_single_ticker_worker,
        args=(queue, ticker, analysis_date, config, str(run_dir)),
    )
    process.start()
    process.join(timeout_seconds)

    if process.is_alive():
        process.terminate()
        process.join(10)
        recovered = _load_result_from_disk(ticker, analysis_date, run_dir)
        if recovered is not None:
            return recovered
        return TickerRunResult(
            ticker=ticker,
            analysis_date=analysis_date,
            run_dir=run_dir,
            errors=[f"TimeoutError: exceeded {timeout_seconds}s per-ticker limit"],
        )

    if process.exitcode not in (0, None):
        recovered = _load_result_from_disk(ticker, analysis_date, run_dir)
        if recovered is not None:
            return recovered
        return TickerRunResult(
            ticker=ticker,
            analysis_date=analysis_date,
            run_dir=run_dir,
            errors=[f"ChildProcessError: worker exited with code {process.exitcode}"],
        )

    if queue.empty():
        recovered = _load_result_from_disk(ticker, analysis_date, run_dir)
        if recovered is not None:
            return recovered
        return TickerRunResult(
            ticker=ticker,
            analysis_date=analysis_date,
            run_dir=run_dir,
            errors=["ChildProcessError: worker exited without returning a result"],
        )

    payload = queue.get()
    return TickerRunResult(
        ticker=payload["ticker"],
        analysis_date=payload["analysis_date"],
        run_dir=Path(payload["run_dir"]) if payload["run_dir"] else None,
        report_file=Path(payload["report_file"]) if payload["report_file"] else None,
        rating=payload["rating"],
        decision_markdown=payload["decision_markdown"],
        executive_summary=payload["executive_summary"],
        implementation_notes=payload["implementation_notes"],
        longbridge_mentions=payload["longbridge_mentions"],
        verified_files=payload["verified_files"],
        errors=payload["errors"],
    )


def run_batch(
    tickers: Iterable[str],
    analysis_date: str,
    reports_root: Path = REPORTS_ROOT,
    output_root: Path = OUTPUT_ROOT,
    per_ticker_timeout_seconds: int = DEFAULT_PER_TICKER_TIMEOUT_SECONDS,
) -> tuple[list[TickerRunResult], Path]:
    reports_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    config = build_weekly_config()
    results = [
        run_single_ticker_isolated(
            ticker=ticker,
            analysis_date=analysis_date,
            config=copy.deepcopy(config),
            reports_root=reports_root,
            timeout_seconds=per_ticker_timeout_seconds,
        )
        for ticker in tickers
    ]
    allocation_path = output_root / f"target_allocation_{analysis_date}.md"
    allocation_markdown = build_allocation_markdown(analysis_date, results, allocation_path)
    allocation_path.write_text(allocation_markdown, encoding="utf-8")
    summary_path = output_root / f"target_allocation_{analysis_date}.json"
    summary_path.write_text(
        json.dumps(
            [
                {
                    "ticker": result.ticker,
                    "rating": result.rating,
                    "report_file": str(result.report_file) if result.report_file else None,
                    "errors": result.errors,
                    "verified_files": result.verified_files,
                    "longbridge_mentions": result.longbridge_mentions,
                }
                for result in results
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    return results, allocation_path


def parse_args() -> argparse.Namespace:
    default_analysis_date = resolve_default_analysis_date()
    parser = argparse.ArgumentParser(description="Run the weekly TradingAgents deep rebalance batch.")
    parser.add_argument(
        "--analysis-date",
        default=default_analysis_date,
        help=(
            "Analysis date in YYYY-MM-DD. Defaults to the most recent Friday "
            "in America/Los_Angeles."
        ),
    )
    parser.add_argument(
        "--tickers",
        nargs="*",
        default=TICKER_UNIVERSE,
        help="Optional subset of tickers to run.",
    )
    parser.add_argument("--reports-root", default=str(REPORTS_ROOT))
    parser.add_argument("--output-root", default=str(OUTPUT_ROOT))
    parser.add_argument(
        "--per-ticker-timeout-seconds",
        type=int,
        default=DEFAULT_PER_TICKER_TIMEOUT_SECONDS,
        help="Hard parent-process timeout for each ticker worker.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results, allocation_path = run_batch(
        tickers=args.tickers,
        analysis_date=args.analysis_date,
        reports_root=Path(args.reports_root),
        output_root=Path(args.output_root),
        per_ticker_timeout_seconds=args.per_ticker_timeout_seconds,
    )
    failures = [result for result in results if result.errors]
    print(f"Allocation markdown: {allocation_path}")
    print(f"Completed {len(results)} tickers; failures: {len(failures)}")
    for result in failures:
        print(f"- {result.ticker}: {result.errors[0]}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
