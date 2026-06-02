from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_leap_options_summary,
    get_language_instruction,
)
from tradingagents.dataflows.longbridge_mcp import (
    LongbridgeMCPError,
    get_leap_options_summary as fetch_leap_options_summary,
)


LEAP_ANALYSIS_FRAMEWORK = """
You are the LEAP analyst. Your job is to judge whether long-dated options flow
is consistent with informed accumulation, hedging, mechanical rebalancing, or
noise. Do not treat a large call print as automatically bullish.

Use this decision sequence:

1. Data quality gate
- State the data timestamp, option expiry, strikes, stock price, and whether
  open interest has already updated after the trade date.
- If data is stale, missing bid/ask, or cannot separate opening from closing
  trades, downgrade confidence.

2. Price and volume context
- Price return = (current price - previous close) / previous close.
- Intraday rebound = (latest price - intraday low) / intraday low.
- Volume multiple = observed volume / average comparable volume.
- A bullish divergence needs price weakness or pullback plus evidence that
  demand improved into or after the weakness.

3. LEAPS options structure
- OI change = current open interest - prior open interest.
- Contract notional = contracts * 100 * underlying price.
- Premium deployed = contracts * option premium * 100.
- Moneyness = underlying price / strike for calls, or strike / underlying price
  for puts.
- Separate near-the-money calls from far out-of-the-money calls. Far OTM calls
  can be lottery exposure and should receive lower conviction unless premium is
  material and repeated across days.

4. Flow segmentation
- Net premium flow = buy premium - sell premium.
- Large-order net flow = large buy premium - large sell premium.
- Institution-like accumulation is stronger when large-order net flow is
  positive while small-order flow is negative, and when OI rises the next day.
- If call OI rises while put OI also rises, classify as volatility demand or
  hedged structure unless call-side premium dominance is clear.

5. Cross-asset and sector check
- Relative return = stock return - benchmark return.
- Sector dispersion = stock return - peer basket median return.
- If peers fall together, prefer sector rotation, ETF rebalance, or factor
  pressure over single-name fundamental deterioration.
- If the stock falls alone while peers are stable, require company-specific
  news and fundamentals checks before calling it technical pressure.

6. Alternative-structure check
- Explicitly test whether the flow could be covered calls, collars, spreads,
  conversions, dividend capture, volatility arbitrage, or dealer hedging.
- If multi-leg context is unavailable, label the trade as directional-possible,
  not directional-confirmed.

7. Falsification and risk
- Define a price level, event, or data update that breaks the thesis.
- Include earnings date, valuation risk, liquidity, bid/ask width, IV crush,
  and LEAPS duration risk.

8. Synthesis
- Classify the setup as one of:
  Accumulation likely, Hedged accumulation, Technical/sector pressure,
  Speculative call chase, Bearish distribution, or Insufficient evidence.
- Give confidence: High, Medium, Low.
- End with a table of evidence, formula, reading, and caveat.
"""


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate_leap_signal(metrics: Mapping[str, Any]) -> Dict[str, Any]:
    """Score a LEAPS setup from normalized market and option-flow metrics.

    Expected keys are intentionally simple so callers can adapt vendor data:
    price_return, rebound_from_low, volume_multiple, large_buy_premium,
    large_sell_premium, small_buy_premium, small_sell_premium,
    call_oi_change, put_oi_change, call_premium_added, put_premium_added,
    stock_return, benchmark_return, peer_median_return, data_quality_score.

    Returns a compact interpretation that an LLM analyst can cite in a report.
    """
    price_return = _as_float(metrics.get("price_return"))
    rebound = _as_float(metrics.get("rebound_from_low"))
    volume_multiple = _as_float(metrics.get("volume_multiple"))
    call_oi_change = _as_float(metrics.get("call_oi_change")) or 0.0
    put_oi_change = _as_float(metrics.get("put_oi_change")) or 0.0
    call_premium = _as_float(metrics.get("call_premium_added")) or 0.0
    put_premium = _as_float(metrics.get("put_premium_added")) or 0.0
    data_quality = _as_float(metrics.get("data_quality_score"))

    large_buy = _as_float(metrics.get("large_buy_premium")) or 0.0
    large_sell = _as_float(metrics.get("large_sell_premium")) or 0.0
    small_buy = _as_float(metrics.get("small_buy_premium")) or 0.0
    small_sell = _as_float(metrics.get("small_sell_premium")) or 0.0
    large_net_flow = large_buy - large_sell
    small_net_flow = small_buy - small_sell

    stock_return = _as_float(metrics.get("stock_return"))
    benchmark_return = _as_float(metrics.get("benchmark_return"))
    peer_median_return = _as_float(metrics.get("peer_median_return"))
    benchmark_relative = (
        stock_return - benchmark_return
        if stock_return is not None and benchmark_return is not None
        else None
    )
    peer_relative = (
        stock_return - peer_median_return
        if stock_return is not None and peer_median_return is not None
        else None
    )

    score = 0
    evidence = []
    cautions = []

    if data_quality is not None and data_quality < 0.6:
        score -= 2
        cautions.append("Data quality is weak; opening vs closing flow may be unclear.")

    if price_return is not None and price_return < -0.03:
        score += 1
        evidence.append("Price weakness creates a useful stress test for flow behavior.")
    if rebound is not None and rebound > 0.01:
        score += 1
        evidence.append("Rebound from intraday low suggests buyers appeared after weakness.")
    if volume_multiple is not None and volume_multiple > 2:
        score += 1
        evidence.append("Volume is meaningfully above normal.")

    if call_oi_change > 0:
        score += 2
        evidence.append("Call open interest increased.")
    if call_premium > put_premium and call_premium > 0:
        score += 1
        evidence.append("Added call premium exceeds added put premium.")
    if put_oi_change > 0 and put_premium > 0.5 * max(call_premium, 1):
        score -= 1
        cautions.append("Put demand rose as well; flow may reflect volatility or hedging.")

    if large_net_flow > 0:
        score += 2
        evidence.append("Large-order net premium flow is positive.")
    if small_net_flow < 0 and large_net_flow > 0:
        score += 1
        evidence.append("Large flow diverges positively from small flow.")
    if large_net_flow <= 0:
        score -= 2
        cautions.append("Large-order flow does not confirm accumulation.")

    if peer_relative is not None and abs(peer_relative) < 0.02:
        score += 1
        evidence.append("Move is broadly in line with peer basket pressure.")
    elif peer_relative is not None and peer_relative < -0.03:
        score -= 1
        cautions.append("Stock underperformed peers; single-name risk needs explanation.")

    if benchmark_relative is not None and benchmark_relative < -0.03:
        evidence.append("Stock materially underperformed the broad benchmark.")

    if score >= 6:
        classification = "Accumulation likely"
        confidence = "Medium"
    elif score >= 4:
        classification = "Hedged accumulation"
        confidence = "Medium"
    elif score >= 2:
        classification = "Technical/sector pressure"
        confidence = "Low"
    elif score <= -2:
        classification = "Bearish distribution"
        confidence = "Medium"
    else:
        classification = "Insufficient evidence"
        confidence = "Low"

    return {
        "classification": classification,
        "confidence": confidence,
        "score": score,
        "large_net_flow": large_net_flow,
        "small_net_flow": small_net_flow,
        "benchmark_relative": benchmark_relative,
        "peer_relative": peer_relative,
        "evidence": evidence,
        "cautions": cautions,
    }


def _fallback_options_summary(symbol: str, exc: Exception) -> str:
    return (
        f"# LEAPS/options-flow summary for {symbol}\n\n"
        "Data source: Longbridge MCP unavailable\n\n"
        f"Unavailable reason: {exc}\n\n"
        "Missing fields: option expiry, strike ladder, open interest, volume, "
        "implied volatility, delta, premium, and next-day OI confirmation.\n\n"
        "Interpretation guidance: treat the LEAPS signal as insufficient evidence "
        "until option-chain access is restored."
    )


def _load_options_summary(symbol: str) -> str:
    try:
        return fetch_leap_options_summary(symbol)
    except LongbridgeMCPError as exc:
        # Degrade gracefully when Longbridge MCP support is unavailable so the
        # full research graph can still complete and the LEAP analyst can
        # document the data gap explicitly in its report.
        return _fallback_options_summary(symbol, exc)


def create_leap_agent(llm):
    """Create a standalone LEAPS/options-flow analyst node."""

    def leap_agent_node(state):
        current_date = state["trade_date"]
        company = state["company_of_interest"]
        instrument_context = build_instrument_context(company)
        options_summary = _load_options_summary(company)

        system_message = (
            LEAP_ANALYSIS_FRAMEWORK
            + "\nWrite a detailed but disciplined LEAPS/options-flow report. "
            + "Use the supplied Longbridge MCP options summary and cite its data source. "
            + "If exact option-chain data is unavailable, identify the missing fields "
            + "and explain how each missing field would change the conclusion. "
            + "Do not issue a final BUY/HOLD/SELL by yourself; provide evidence for "
            + "the research and trading agents to use."
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant collaborating with other trading "
                    "assistants. Your specialty is LEAPS and options-flow reasoning.\n"
                    "{system_message}\n"
                    "For your reference, the current date is {current_date}. "
                    "{instrument_context}\n\n"
                    "Longbridge MCP options summary:\n{options_summary}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)
        prompt = prompt.partial(options_summary=options_summary)

        chain = prompt | llm
        result = chain.invoke(state["messages"])

        return {
            "messages": [result],
            "leap_report": result.content,
        }

    return leap_agent_node
