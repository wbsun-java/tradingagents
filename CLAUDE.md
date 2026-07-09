# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

TradingAgents is a research-oriented, multi-agent financial analysis framework. It uses
LangGraph to coordinate specialized LLM agents that gather market data, write analyst
reports, debate bullish and bearish cases, propose a trade, evaluate risk, and produce a
final portfolio-management decision. It is not financial advice and does not place live
orders.

## Commands

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"        # installs package + ruff/pytest/pytest-subtests
cp .env.example .env           # add at least one LLM provider key
```

Run the app (it's a single-command Typer CLI, not a multi-subcommand one):

```bash
tradingagents                   # installed console script
python -m cli.main               # equivalent, from source
tradingagents --checkpoint       # opt into LangGraph checkpoint/resume
tradingagents --clear-checkpoints
```

Default verification for an isolated additive change:

```bash
pytest -q tests/test_<changed_feature>.py
ruff check <changed files>
```

Run a single test: `pytest tests/test_symbol_utils.py::test_name -q`. Tests marked
`integration` (see `pyproject.toml` markers) may hit external services/APIs — don't add new
tests that make real network or paid LLM calls unless marked `integration`.

Do not run the full suite after every isolated new feature. Add directly affected contract
or wiring tests when needed. Run `pytest -q` plus `ruff check .` only for cross-cutting
changes to shared graph state, common vendor/config interfaces, provider factories,
dependency metadata, multiple existing subsystems, or before a release/PR; also run them
when the user explicitly requests full verification. Keep successful output concise.

## Architecture

`TradingAgentsGraph` (`tradingagents/graph/trading_graph.py`) builds and runs a LangGraph
pipeline with this flow:

1. Selected analysts run in sequence: market, sentiment, news, fundamentals. Each may loop
   through LangChain tools before advancing.
2. Bull and bear researchers debate the analyst reports (rounds from config).
3. The research manager creates an investment plan.
4. The trader turns that plan into a proposed trade.
5. Aggressive, conservative, and neutral risk agents debate the proposal.
6. The portfolio manager emits the final structured decision.

Key modules:

- `cli/main.py` — Typer/Rich interactive CLI and live progress UI; `cli/config.py`,
  `cli/models.py`, `cli/utils.py`, `cli/stats_handler.py` support it.
- `main.py` — minimal programmatic example using `TradingAgentsGraph.propagate()`.
- `tradingagents/graph/setup.py` — LangGraph node/edge wiring; `conditional_logic.py`,
  `analyst_execution.py`, `propagation.py`, `reflection.py`, `checkpointer.py`,
  `signal_processing.py` are the supporting graph pieces.
- `tradingagents/agents/` — per-role prompts and implementations, split into
  `analysts/`, `researchers/`, `managers/`, `trader/`, `risk_mgmt/`; `agents/utils/` holds
  shared tools, the typed `AgentState`, structured-output schemas, and the decision-log
  memory helpers.
- `tradingagents/dataflows/` — vendor routing (`interface.py`, `config.py`) plus adapters:
  `y_finance.py`, `yfinance_news.py`, `alpha_vantage*.py`, `fred.py`, `polymarket.py`,
  `reddit.py`, `stocktwits.py`, `stockstats_utils.py`. All market-data access must go
  through here — never fetch a vendor directly from an agent prompt or graph node.
- `tradingagents/llm_clients/` — provider `factory.py`, `model_catalog.py`, `capabilities.py`
  (validation), `api_key_env.py`, and per-provider clients (openai, anthropic, google,
  azure, bedrock). Add new providers through this registry/factory rather than branching
  in the graph.
- `tradingagents/default_config.py` — `DEFAULT_CONFIG` plus the `TRADINGAGENTS_*` env-var
  override table (`_ENV_OVERRIDES`); adding a new overridable key is a one-line addition
  there, no entry-point changes needed.
- `tradingagents/reporting.py` — per-stage and consolidated Markdown report writer, shared
  by the CLI and programmatic use.

For programmatic use, always copy `DEFAULT_CONFIG` before mutating it, then
`TradingAgentsGraph(config=...).propagate(ticker, "YYYY-MM-DD", asset_type=...)`.

### Data vendor routing

`data_vendors` in config is category-level (`core_stock_apis`, `technical_indicators`,
`fundamental_data`, `news_data`, `macro_data`, `prediction_markets`); `tool_vendors` can
override per-tool. The configured chain is used exactly as given — requests are never
silently rerouted to a vendor the user didn't select.

### Runtime state (outside the repo)

Everything lives under `~/.tradingagents/` by default (overridable via
`TRADINGAGENTS_RESULTS_DIR`, `TRADINGAGENTS_CACHE_DIR`, `TRADINGAGENTS_MEMORY_LOG_PATH`):

- `logs/` — JSON run state and default programmatic reports.
- `cache/checkpoints/<TICKER>.db` — per-ticker LangGraph checkpoint SQLite DBs (only when
  `--checkpoint`/`checkpoint_enabled` is on).
- `memory/trading_memory.md` — the always-on decision log: each run appends its decision,
  and the next run for the same ticker fetches realized return/alpha and injects a
  reflection plus cross-ticker lessons into the Portfolio Manager prompt.

The interactive CLI can also save Markdown reports under a user-chosen path (default
`./reports/`). Never commit `.env`, generated reports, caches, or credentials.

## Coding Conventions

- Do not modify files that came from the original upstream repository. Put all customization
  in newly added files. If integration appears to require an import, registration, binding,
  or prompt change in an upstream file, stop and obtain the user's explicit approval for
  that exact file first.
- Every newly created file must be at most 150 lines, including source, test, script, and
  documentation files. If a feature needs more, split it by responsibility into multiple
  small, single-purpose files (e.g. one file for state definitions, one per behavior/signal
  type, one thin orchestrator that dispatches to them). Existing oversized files are
  grandfathered; avoid growing them with unrelated logic.

## Change Guidelines

- Preserve the typed `AgentState` keys shared across graph nodes and report generation.
- When adding an analyst: update its factory, tool node, execution plan, conditional route,
  CLI display mapping, and tests together.
- When adding a directly-callable Market Analyst tool (vs. a prefetch-only read like
  Wyckoff/O'Neil): register it in `agent_utils.py` (`__all__`), `market_analyst.py`
  (`tools=[...]` + a prompt paragraph), and `trading_graph.py`'s `"market"`
  `ToolNode([...])` — all three, or the LLM's tool call fails at execution even though
  wiring compiles.
- New per-module `prepare_ohlcv`-style preparers (see `wyckoff_range.py`, `oneil_cup.py`,
  `pocket_pivot_signals.py`) should raise `ValueError` below a computed minimum row count,
  not just for missing columns — too little history otherwise degrades indicators to
  silent all-NaN output instead of an error.
- Keep ticker path handling behind `safe_ticker_component` and the symbol-normalization
  helpers (path-traversal hardening depends on this).
- Run the full test + Ruff suite only after cross-cutting graph/provider/dataflow contract
  changes, not after an isolated additive module with focused coverage.
- Ruff config (`pyproject.toml`) selects `E, W, F, I, B, UP, C4, SIM` and ignores `E501`
  (line length); whole-repo `ruff format` adoption is deliberately deferred.
