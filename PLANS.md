# Weekly TradingAgents Deep Rebalance Automation Plan

## Goal

Run a weekly deep TradingAgents rebalance across the fixed ticker universe, save full per-ticker reports, verify required analyst artifacts, and generate a dated target-allocation markdown summary for operational use.

## Phases

1. Add a minimal non-interactive batch runner that reuses `TradingAgentsGraph` and `save_report_to_disk`.
2. Smoke-test one ticker end-to-end with the required analyst set and data-vendor preferences.
3. Run the full universe while isolating failures per ticker.
4. Verify saved report artifacts, summarize ratings/data-source adoption, and write the dated allocation document.

## Validation Per Phase

- Batch runner builds and imports cleanly.
- Single-ticker smoke run produces `1_analysts/leap.md` and `1_analysts/data_sources.md`.
- Full batch completes with per-ticker status captured even when individual names fail.
- Allocation markdown includes 100% total target weight, zero-weight names, implementation notes, and absolute report paths.

## Risks

- Longbridge MCP may require fresh OAuth or may partially fall back to yfinance.
- Full-universe LLM runtime can be long; failures must not abort the whole batch.
- Final report prose is model-generated, so rating and execution-note extraction must tolerate markdown variation.

## Decision Points

- Reuse existing report-save behavior rather than extending the interactive CLI.
- Prefer a standalone script so the Friday automation can be invoked directly and non-interactively.

# Longbridge MCP Data Source Plan

## Problem

Add Longbridge MCP support as an optional TradingAgents data vendor without changing the default yfinance behavior.

## Context

- Existing data source selection is centralized in `tradingagents/dataflows/interface.py`.
- Agent tool functions call `route_to_vendor(...)`, so adding a vendor at this layer keeps analyst prompts and tool contracts stable.
- Longbridge documents a hosted Streamable HTTP MCP endpoint at `https://openapi.longbridge.com/mcp` and a China endpoint at `https://openapi.longbridge.cn/mcp`.

## Proposed Approach

1. Add a `longbridge_mcp` dataflow module with a small MCP client wrapper.
2. Expose read-only vendor functions for OHLCV, fundamentals, statements, news, and insider/executive data where Longbridge MCP has matching tools.
3. Register `longbridge_mcp` in the existing vendor router.
4. Keep unsupported tools, such as stockstats technical indicators, falling back to existing vendors.
5. Add focused unit tests that mock the MCP call boundary.

## Files Or Modules Affected

- `tradingagents/default_config.py`
- `tradingagents/dataflows/interface.py`
- `tradingagents/dataflows/longbridge_mcp.py`
- `pyproject.toml`
- `tests/test_longbridge_mcp.py`

## Validation

- Unit tests for symbol normalization, MCP argument mapping, formatted output, and vendor routing.
- Import/compile checks for the changed modules.

## Risks Or Open Questions

- Longbridge MCP requires OAuth 2.1 at runtime. The code can call a configured MCP endpoint, but users still need to authorize the MCP client/session according to Longbridge account permissions.
- MCP tool schemas can evolve; tool names and base arguments are configurable through `longbridge_mcp` config.

# x_strategy_zoo Standalone Project Plan

## Problem

Build a new standalone project, temporarily named `x_strategy_zoo`, that is independent of this TradingAgents repository and independent of the TradingAgents agent framework.

The project should reuse the useful ideas from TradingAgents, especially vendor abstraction and Longbridge MCP access, but its primary job is different:

- Pull and normalize Longbridge market data.
- Build a local historical database.
- Maintain an extensible strategy zoo.
- Run backtests using local data.
- Run selected strategies on a daily runtime schedule, with optional intraday upgrade if Longbridge data supports hour or 30-minute bars.
- Persist every strategy run, signal, position, metric, and review artifact for monthly, quarterly, and yearly analysis.
- Keep the project easy to sync through GitHub and easy to run through Codex automations.

Two additional reference projects should guide the first implementation:

- `quant_factor_platform`: use its local-first data lake model, especially raw/bronze/silver/features/factors/labels, Parquet durability, Polars Lazy transforms, DuckDB analytical access, and explicit storage config.
- `qc_live_deploy`: use its Python-orchestrated/Rust-native compute split, especially the Rust CLI backtest adapter pattern, reproducible run artifacts, SQLite-style provider/backtest run tracking, and non-interactive operational scripts.

## Context

- `x_strategy_zoo` should be created as a new repository, not as a package inside TradingAgents.
- TradingAgents can be used as a reference for:
  - Longbridge MCP OAuth/session handling.
  - Vendor-facing data adapter structure.
  - Tool/config separation.
  - Runtime result logging discipline.
- `quant_factor_platform` should be used as the reference for database/storage structure:
  - immutable raw layer,
  - typed bronze layer,
  - cleaned silver layer,
  - durable feature/factor/label stores,
  - storage paths resolved from config instead of hardcoded business logic,
  - Parquet as the durable analytical format,
  - DuckDB as the local query/catalog surface.
- `qc_live_deploy` should be used as the reference for native compute:
  - Python CLI/service layer builds requests,
  - Rust CLI runs deterministic ingest/backtest kernels,
  - run outputs include `summary.json`, `report.md`, `equity_curve.csv`, and `trades.csv`,
  - provider/backtest runs are recorded in local tables.
- The new project should avoid importing TradingAgents modules. Copy only the minimal patterns after rethinking the boundaries.
- The new project should also avoid importing `quant_factor_platform` or `qc_live_deploy` at runtime. They are design references, not dependencies.
- The system must scale along two axes:
  - More symbols, markets, peer groups, and universes.
  - More strategies, timeframes, parameters, and review horizons.

## Proposed Approach

### Phase 0: Create The Standalone Repository

Create a fresh GitHub-synced project:

- Repository name: `x_strategy_zoo`
- Suggested local path: `/Users/sunkewei/git/gh_all_repos/x_strategy_zoo` or another GitHub-managed workspace path.
- Runtime language: Python.
- Package manager: choose one and standardize early, preferably `uv` if the local workflow supports it.
- Initial command surface:
  - `python -m x_strategy_zoo.cli sync-data`
  - `python -m x_strategy_zoo.cli backtest`
  - `python -m x_strategy_zoo.cli run-daily`
  - `python -m x_strategy_zoo.cli review`

Suggested top-level layout:

```text
x_strategy_zoo/
  pyproject.toml
  Cargo.toml
  README.md
  PLANS.md
  .env.example
  crates/
    xsz_engine/
      Cargo.toml
      pyproject.toml
      src/
        main.rs
        lib.rs
        ingest.rs
        backtest.rs
        metrics.rs
        storage.rs
        strategies/
          mod.rs
          moving_average.rs
          leap_accumulation.rs
  src/x_strategy_zoo/
    __init__.py
    cli.py
    config.py
    data/
      longbridge_client.py
      schemas.py
      normalize.py
      quality.py
      sync.py
    storage/
      database.py
      migrations/
      repositories.py
    strategies/
      base.py
      registry.py
      leap/
        signal.py
        strategy.py
      examples/
        moving_average.py
    backtest/
      engine.py          # Python adapter around Rust engine
      portfolio.py
      metrics.py
      slippage.py
    runtime/
      daily_runner.py
      scheduler.py
      run_context.py
    review/
      reports.py
      snapshots.py
    automation/
      README.md
      daily_run_prompt.md
      weekly_review_prompt.md
  tests/
  scripts/
  data/              # gitignored local data lake / DB / cache
    raw/
    bronze/
    silver/
    features/
    factors/
    labels/
    db/
  runs/              # gitignored generated run artifacts unless curated
```

Deliverable:

- Empty but runnable repo with Python CLI skeleton, Rust crate skeleton, config loading, test skeleton, `.env.example`, and GitHub remote.

### Phase 1: Define Data Contracts And Local Storage

Use `quant_factor_platform` as the model: data should flow through explicit layers before it touches strategies.

Storage layers:

- `raw`: immutable source-aligned Longbridge payloads and request manifests.
- `bronze`: typed and canonicalized records with source fields mapped to standard names.
- `silver`: cleaned, research-ready records with deterministic quality flags and adjustment policy.
- `features`: durable observable feature outputs.
- `factors`: durable strategy/factor scores and parameter variants.
- `labels`: future-return/outcome labels for evaluation and later ML.
- `research` or `runs`: backtest/runtime outputs and review artifacts.

Preferred storage technology:

- Parquet for raw-derived durable datasets.
- Polars Lazy for transformations.
- DuckDB for analytical querying, joins, pivots, run review, and report extraction.
- A small SQLite or DuckDB metadata catalog for provider runs, strategy runs, and data snapshot manifests.

Core entities:

- `Instrument`: symbol, market, currency, exchange, asset type, sector, peer group, active flag.
- `Bar`: symbol, timeframe, timestamp, open, high, low, close, volume, turnover, adjustment flag.
- `OptionContract`: underlying, expiry, strike, right, contract symbol, multiplier, currency.
- `OptionQuote`: contract symbol, timestamp, bid, ask, last, volume, open interest, IV, greeks.
- `CorporateAction`: split, dividend, symbol change, delisting if available.
- `UniverseMembership`: universe name, symbol, valid_from, valid_to.
- `StrategyRun`: run id, strategy id, version, universe, timeframe, config hash, data snapshot id, started_at, finished_at.
- `Signal`: run id, symbol, timestamp, signal type, score, confidence, payload JSON.
- `Position`: run id, symbol, timestamp, quantity, price, value, exposure.
- `OrderSimulation`: run id, symbol, side, size, signal timestamp, fill timestamp, fill price, slippage model.
- `PerformanceMetric`: run id, metric name, value, window, benchmark.

Standard market schemas should mirror `quant_factor_platform`:

- Trades: `ts_event`, `symbol`, `price`, `size`, `source`, optional `ts_recv`, `side`, `exchange`, `condition`.
- Quotes: `ts_event`, `symbol`, `bid_px`, `ask_px`, `bid_sz`, `ask_sz`, `source`, optional `ts_recv`, `exchange`.
- Bars: `datetime`, `symbol`, `open`, `high`, `low`, `close`, `volume`, `source`, optional `vwap`, `trade_count`.
- Instruments: `symbol`, `start_date`, `end_date`, `asset_type`, optional `exchange`, `currency`.

Metadata/run tables should borrow from `qc_live_deploy` but generalize beyond one strategy:

- `provider_runs`: provider, started_at, params_json, status, message, row counts, payload hashes.
- `data_snapshots`: snapshot id, layer, dataset, symbols, timeframe, date range, source batches, quality status.
- `strategy_runs`: run id, strategy id, strategy version, generated_at, start/end, config_json, data_snapshot_id, metrics_json, report_path.
- `runtime_runs`: run id, runtime mode, market session date, strategy set, status, summary_json.
- `artifacts`: run id, artifact type, path, content hash.

Data directories:

- `data/raw/longbridge/`: raw JSON snapshots, partitioned by provider/tool/date/symbol.
- `data/bronze/longbridge/`: typed canonical records, partitioned by dataset/timeframe/symbol/date.
- `data/silver/`: cleaned research-ready records.
- `data/features/`: feature store.
- `data/factors/`: factor/strategy score store.
- `data/labels/`: future outcome store.
- `data/db/strategy_zoo.duckdb`: local catalog/query database.
- `data/parquet/`: optional columnar export for larger studies.
- `runs/YYYY/MM/DD/<strategy>/<run_id>/`: run reports, configs, metrics, and selected artifacts.

Deliverable:

- Versioned storage schema with migrations and tests for idempotent inserts, duplicate handling, timestamp normalization, and raw-to-bronze-to-silver regeneration.

### Phase 2: Build Longbridge Data Collection

Reference TradingAgents' Longbridge approach, but implement it inside `x_strategy_zoo` with standalone names and tests.

Longbridge modules:

- `data/longbridge_client.py`: OAuth/session/client wrapper.
- `data/sync.py`: high-level sync jobs.
- `data/normalize.py`: convert vendor payloads to project schemas.
- `data/quality.py`: validate missing bars, duplicate timestamps, stale quotes, and outlier prices.

Minimum collection targets:

- Daily OHLCV bars.
- Intraday OHLCV bars if Longbridge supports hour or 30-minute granularity for the target market.
- Option chain expiries.
- Option contract snapshots: strike, expiry, call/put, quote, volume, OI, IV, greeks where available.
- Basic instrument metadata.
- Benchmark and peer symbols.

Data precision check:

- Explicitly inspect Longbridge tool support for bar intervals.
- Record supported timeframes in `data_source_capabilities`.
- Start with daily bars as the stable baseline.
- Add `1h` or `30m` only after confirming:
  - historical depth,
  - timezone semantics,
  - market session coverage,
  - adjustment behavior,
  - API rate limits.

Sync requirements:

- Idempotent sync by symbol/timeframe/date range.
- Persist raw payload before normalization.
- Normalize timestamps to UTC while preserving exchange-local session date.
- Track sync status, source tool name, request args hash, response hash, and row counts.
- Fail partial syncs visibly and retry safely.
- Write raw payloads first, then bronze, then silver. Never let strategy code consume raw payloads directly.

Deliverable:

- `sync-data` can fill a local database for configured symbols and timeframes.

### Phase 3: Build The Strategy Zoo Framework

Strategies should be pluggable and testable without knowing where the data came from.

Strategy interface:

- `strategy_id`
- `version`
- `required_timeframes`
- `required_data`
- `default_parameters`
- `generate_signals(data, context) -> list[Signal]`
- Optional `size_positions(signals, portfolio, context) -> list[TargetPosition]`

Rust/Python split:

- Python owns strategy discovery, configuration validation, experiment orchestration, review generation, and Codex-facing CLI.
- Rust owns deterministic high-throughput signal/backtest kernels.
- Strategy metadata exists in Python config and is mirrored into Rust enums/registry for strategies that need native execution.
- Pure Python reference implementations are acceptable for correctness tests, but production backtests should run through Rust once stabilized.

Registry:

- Strategy registration by Python entrypoint.
- Parameter schema and config validation.
- Stable strategy versioning so old runs remain interpretable.
- Universe compatibility checks.

Initial strategy candidates:

- `leap_accumulation`: LEAPS/options-flow signal based on OI, premium, price weakness, peer context, and data quality.
- `moving_average_cross`: simple baseline for pipeline validation.
- `relative_strength`: benchmark/peer-relative momentum.
- `event_risk_filter`: optional risk overlay around earnings or macro events if data exists.

LEAPS strategy rules should remain deterministic:

- No direct BUY/HOLD/SELL from an LLM.
- Classify evidence: accumulation likely, hedged accumulation, sector pressure, speculative call chase, bearish distribution, insufficient evidence.
- Emit signal score, confidence, missing data flags, and falsification levels.

Deliverable:

- A strategy registry with at least one baseline strategy and one LEAPS strategy skeleton.

### Phase 4: Build Rust Native Compute And Backtesting Engine

Use `qc_live_deploy` as the execution reference: Python builds a request, Rust executes the compute path, and the run emits stable artifacts.

Rust crate:

- `crates/xsz_engine`
- CLI subcommands:
  - `init-db` or `init-catalog`
  - `ingest-longbridge-normalized` for loading normalized parquet/catalog records into fast local views if needed
  - `backtest`
  - `run-strategy`
  - `compute-metrics`
- Optional PyO3 module later if direct Python calls are useful; start with CLI for simpler automation and reproducibility.

Python adapter:

- `src/x_strategy_zoo/backtest/engine.py`
- `RustBacktestRequest`
- `RustBacktestAdapter`
- `build_command()`
- `preview()`
- `run()` with stdout/stderr capture and artifact path validation.

Backtest engine requirements:

- Load data from local database only.
- Enforce timestamp ordering and no look-ahead.
- Respect data availability lag, especially OI and option chain data.
- Support daily baseline first.
- Allow later `1h` or `30m` mode if data capabilities confirm support.
- Parameterized transaction costs, slippage, fill timing, and rebalance timing.
- Benchmark comparison.
- Universe-level and symbol-level output.
- Write reproducible outputs like `qc_live_deploy`:
  - `summary.json`
  - `report.md`
  - `equity_curve.csv`
  - `trades.csv`
  - `signals.parquet` or `signals.csv`
  - `positions.parquet` or `positions.csv`
  - `config.json`
  - `data_snapshot.json`

Metrics:

- CAGR or annualized return.
- Sharpe and volatility.
- Max drawdown.
- Turnover.
- Exposure.
- Win rate and average win/loss.
- Beta or benchmark-relative return.
- Signal hit rate by confidence bucket.
- Capacity/liquidity caveats where volume data exists.

Deliverable:

- Rust `backtest` can run one strategy against one or more symbols and persist full results; Python can preview and invoke the Rust command non-interactively.

### Phase 5: Build Daily Runtime

Daily runtime should run the same strategy code as backtest, with a different data window and output mode.

Runtime flow:

1. Resolve configured universe.
2. Sync latest data from Longbridge.
3. Validate data freshness and missing fields.
4. Run selected strategies through the Rust compute path where available.
5. Persist signals, metrics, and run metadata.
6. Emit Markdown summary for Codex or human review.
7. Save a machine-readable JSON artifact for downstream automation.

Runtime levels:

- `daily`: default, stable.
- `hourly`: only after Longbridge historical and latest bars are validated.
- `30m`: only after the same checks pass and rate limits are acceptable.

Deliverable:

- `run-daily` command that can be called from Codex automation or local cron.

### Phase 6: Preserve Strategy History For Reviews

Every strategy run must leave enough evidence to explain decisions later.

Persist:

- Strategy config.
- Code version or git commit.
- Data snapshot id.
- Data quality report.
- Signals.
- Simulated positions/orders.
- Performance metrics.
- Strategy-specific diagnostic payload.
- Human-readable Markdown report.
- Native engine version, Rust binary build info, and command-line arguments.

Review commands:

- `review --period monthly`
- `review --period quarterly`
- `review --period yearly`
- `review --strategy leap_accumulation`
- `review --symbol NOK`

Review output:

- Period return and benchmark-relative behavior.
- Best/worst signals.
- Signal confidence calibration.
- Drawdown and exposure history.
- Strategy drift or degradation.
- Data quality gaps.
- Actionable follow-up experiments.

Deliverable:

- Periodic review artifacts generated from stored data, not reconstructed manually.

### Phase 7: GitHub Sync And Project Hygiene

GitHub requirements:

- Keep source, tests, docs, configs, and automation prompts in git.
- Keep raw data, local DBs, OAuth tokens, and generated run dumps out of git by default.
- Add `.gitignore` for:
  - `.env`
  - OAuth token files
  - `data/raw/`
  - `data/db/`
  - `data/parquet/`
  - `runs/`
  - `.venv/`
- Add `.env.example` with required Longbridge and storage variables.
- Add README setup instructions.
- Add GitHub Actions for lint, tests, and import checks.
- Add Rust CI:
  - `cargo test --manifest-path crates/xsz_engine/Cargo.toml`
  - `cargo fmt --check`
  - `cargo clippy -- -D warnings` once the crate stabilizes.

Deliverable:

- Repo can be cloned, configured, tested, and run reproducibly without copying local secrets.

### Phase 8: Codex Automation Readiness

Codex automation should be a first-class deployment target.

Automation-facing design:

- CLI commands must be non-interactive.
- Every command should exit nonzero on real failure.
- Runtime output should include a concise Markdown summary and a JSON artifact path.
- Config should be file/env driven, not prompt driven.
- Longbridge OAuth/token refresh behavior should fail clearly if user action is required.

Suggested automation jobs:

- Daily data sync and strategy run after market close.
- Weekly data quality audit.
- Monthly strategy review.
- Quarterly strategy review.
- Yearly strategy review.

Automation files:

- `automation/daily_run_prompt.md`
- `automation/weekly_quality_prompt.md`
- `automation/monthly_review_prompt.md`
- `automation/setup_notes.md`

Deliverable:

- Codex can run the daily and review workflows without needing interactive clarification.

## Files Or Modules Affected

This plan should create a new repository rather than modifying TradingAgents:

- New repo: `x_strategy_zoo`
- Reference-only source: current TradingAgents Longbridge MCP work
- No runtime imports from `tradingagents`

## Validation

Initial validation:

- `python -m pytest`
- `cargo test --manifest-path crates/xsz_engine/Cargo.toml`
- `python -m x_strategy_zoo.cli --help`
- `python -m x_strategy_zoo.cli sync-data --dry-run`
- `python -m x_strategy_zoo.cli backtest --strategy moving_average_cross --symbols SPY --start YYYY-MM-DD --end YYYY-MM-DD`
- `python -m x_strategy_zoo.cli run-daily --dry-run`

Data validation:

- Re-running the same sync does not duplicate rows.
- Timestamp conversion preserves exchange-local trading date.
- Missing bars and stale option quotes are reported.
- Raw payload count matches normalized row count expectations.

Backtest validation:

- No look-ahead: signals only use data available at or before the decision timestamp.
- Rebalance timing is explicit.
- Transaction costs and slippage are configurable.
- Metrics are reproducible from persisted run artifacts.
- Rust and Python reference implementations match on small deterministic fixtures before Rust becomes the default.

## Risks Or Open Questions

- Longbridge MCP may require OAuth refresh or browser authorization that is awkward for unattended automations.
- Longbridge may not expose enough historical intraday data or option trade-flow detail for 30-minute/hour strategies.
- Options OI updates lag trading activity; daily OI must be treated with data-availability lag.
- Large options positions can be hedges or spreads; LEAPS strategy should classify evidence quality before producing trade signals.
- Local DB size may grow quickly if intraday/options history is retained without partitioning.
- Parquet/DuckDB metadata and Rust local views can drift if snapshot ids are not enforced.
- Rust/Python strategy registries can drift; strategy id/version/config hash must be part of every run artifact.
- Peer/universe definitions need versioning to prevent survivorship bias.
- GitHub should not receive raw market data, tokens, or generated run artifacts unless explicitly curated.
