# Repository Guide

## Purpose

TradingAgents is a research-oriented, multi-agent financial analysis framework. It uses
LangGraph to coordinate specialized LLM agents that gather market data, write analyst
reports, debate bullish and bearish cases, propose a trade, evaluate risk, and produce a
final portfolio-management decision. It is not financial advice and does not place live
orders.

## Execution Flow

The workflow is:

1. Selected analysts run in sequence: market, sentiment, news, and fundamentals.
2. Bull and bear researchers debate the analyst reports.
3. The research manager creates an investment plan.
4. The trader turns that plan into a proposed trade.
5. Aggressive, conservative, and neutral risk agents debate the proposal.
6. The portfolio manager emits the final decision.

`TradingAgentsGraph` builds and runs this graph. Analyst nodes may loop through their
LangChain tools before advancing; debate round limits come from configuration.

## Important Paths

- `cli/main.py`: Typer/Rich interactive CLI and live progress UI.
- `main.py`: minimal programmatic example using `TradingAgentsGraph.propagate()`.
- `tradingagents/graph/trading_graph.py`: top-level orchestration, persistence, and output.
- `tradingagents/graph/setup.py`: LangGraph nodes and edges.
- `tradingagents/agents/`: agent prompts and role implementations.
- `tradingagents/agents/utils/`: shared tools, state definitions, structured output, and memory.
- `tradingagents/dataflows/`: vendor routing and market/news/fundamental data adapters.
- `tradingagents/llm_clients/`: provider factory, model catalog, validation, and clients.
- `tradingagents/default_config.py`: defaults and `TRADINGAGENTS_*` environment overrides.
- `tradingagents/reporting.py`: per-stage and consolidated Markdown report writer.
- `tests/`: pytest suite; most external integrations are mocked.

## Local Development

The project requires Python 3.10 or newer; CI covers 3.10 through 3.13 and the README
recommends 3.12. `requirements.txt` contains `.` intentionally, so installing it installs
the package and dependencies from `pyproject.toml`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
tradingagents
```

The Typer app currently behaves as a single-command CLI, so run `tradingagents` (or
`python -m cli.main`) directly. Use `tradingagents --checkpoint` to opt into resume support.
At least one LLM provider key is needed unless using Ollama or a keyless local
OpenAI-compatible endpoint. Never commit `.env` or credentials.

For programmatic use, copy `DEFAULT_CONFIG` before modifying it, construct a
`TradingAgentsGraph`, and call `propagate(ticker, YYYY-MM-DD, asset_type=...)`.

## Verification

Default to focused verification for the feature being changed:

```bash
pytest -q tests/test_<changed_feature>.py
ruff check <changed files>
```

Install development extras before running pytest or Ruff: `pip install -e ".[dev]"`.
Tests marked `integration` may require external services or API credentials.

Do not run the whole repository suite after every isolated additive feature. Expand testing
only to directly affected contracts and wiring. Run `pytest -q` and `ruff check .` when a
change affects shared graph state, common vendor/config interfaces, provider factories,
dependency metadata, several existing subsystems, or when preparing a release/PR; also run
them when the user explicitly requests full verification. Keep successful output concise.

## Runtime State and Outputs

By default, application state is outside the repository under `~/.tradingagents/`:

- `logs/`: JSON run state and default programmatic reports.
- `cache/`: downloaded data and optional SQLite checkpoints.
- `memory/trading_memory.md`: decisions and later performance reflections.

The interactive CLI can additionally save Markdown reports beneath a user-selected path,
defaulting to `./reports/`. Keep generated reports, caches, and credentials out of commits.

## Change Guidelines

- Every newly created file must be at most 150 lines, including source, test, script, and
  documentation files. Split larger features by responsibility before adding them. Existing
  files already above the limit are grandfathered but must not be used as a reason to add
  more unrelated logic.
- Do not modify files that came from the original upstream repository. Put customization in
  newly added files only. If an upstream file appears to require wiring, stop and obtain the
  user's explicit approval for that exact file before editing it.
- Put each new experience rule or signal family in its own focused module so later trading
  heuristics do not turn one file into a monolith.
- Preserve the typed `AgentState` keys shared across graph nodes and report generation.
- When adding an analyst, update its factory, tool node, execution plan, conditional route,
  CLI display mapping, and tests together.
- Route new market-data access through `tradingagents/dataflows/`; do not fetch vendors
  directly from agent prompts or graph nodes.
- Add LLM providers through the provider registry/factory and capability validation rather
  than branching throughout the graph.
- Keep ticker path handling behind `safe_ticker_component` and symbol normalization helpers.
- Avoid tests that make real network or paid LLM calls unless explicitly marked integration.
- Run the full test and Ruff suites after cross-cutting graph, provider, or dataflow changes.
