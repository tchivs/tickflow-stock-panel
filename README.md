# AthenaQuant

AthenaQuant is a self-hosted quantitative research platform for individual A-share investors. It combines governed market data, portfolio monitoring, reproducible factor and strategy research, auditable decision plans, and evidence-first AI research in one deployable application.

It is designed for research and decision support. It does not place live broker orders.

## What It Provides

### Research and governance stack

- Governed market-data synchronization backed by Parquet, DuckDB, and Polars.
- Portfolio accounts, holdings, P&L, monitoring rules, delivery history, and shared SSE updates.
- Deterministic trade playbooks with bounded, audited AI adjustments and AI-free historical replay.
- Factor DSL, factor evaluation, strategy backtests, reproducible experiment artifacts, and retained comparisons.
- Evidence-grounded AI analysis with source quality, numerical cross-checks, report provenance, and signal lifecycle review.
- Advanced research workflows for attributed viewpoints, controlled experiments, strategy evolution, authorized jobs, and constrained custom-strategy execution.
- Optional Shadow Account, versioned investment theses, and local-only Kronos forecasting modules.

### A-share market workbench (merged from upstream v0.2)

- Screening engine: 27 built-in Polars strategies plus custom signals, AI-generated strategies, and code migration; full A-share scans in milliseconds, ETF mode included.
- Monitoring center: strategy / stock-signal / price / anomaly rules with AND/OR conditions, intraday SSE popups, voice broadcast of stock name and signal, Feishu webhook push, and persisted trigger history.
- Market sentiment tooling: limit-up ladder with seal-order monitoring, concept and industry rotation matrices, market phase (emotion-cycle stages plus mainline identification from the limit-up ladder), and post-market AI recap.
- Factor and strategy mining: nested out-of-sample validation, walkforward, and robustness checks with T-1 market-environment gating and correlation dedupe; jobs run in spawn workers with persistent run IDs, cancellation, and explicit publish.
- Backtest engine: factor (IC/IR, layered returns, long-short) and strategy (equity curve, drawdown, Sharpe, win rate) modes under T+1, fees, slippage, and non-tradable limit constraints, with SSE progress that survives page switches.
- Intraday and auction analytics: minute-level triggers, intraday signals, multi-day intraday overlays with equal-weight price lines, T-day auction collection with reconciliation, premarket preview, and auction recap.
- Data extensibility: pluggable providers with capability routing, custom data sources (HTTP pull, CSV/Excel upload, JSON write), a dynamic extension-page system for third-party fields, and watchlist OCR import from screenshots.
- Watchlist groups with per-group equal-weight average change badges (realtime-first, close-fallback), shared across the watchlist page and the sidebar submenu.
- A-share microstructure correctness: exchange price limits, historical share capital for turnover, and ST exclusion on the hot path.
- Pluggable AI providers over OpenAI-compatible endpoints (relaxed max_tokens, Codex endpoint support), with an optional containerized Codex CLI mode that reuses the host login read-only.

## Architecture Boundaries

- Time-series data stays in Parquet and is queried through DuckDB and Polars.
- SQLite stores operational state, append-only facts, monitoring history, and workflow audit records.
- The default deployment is one Docker Compose service with no external database or message queue.
- Optional modules are independently enabled. The core application does not import Shadow or Forecast heavy dependencies by default.
- Forecast assets are provisioned explicitly, use immutable revisions and SHA-256 validation, and run locally without runtime model downloads.
- Browser clients submit bounded intent only. Authorization, identities, evidence, lifecycle transitions, and execution authority remain server-owned.
- Generic features reach data only through provider capabilities and standardized datasets; no feature may hard-bind to a single vendor SDK.
- The optional stock-sdk scraping plugin is not bundled into Docker images by default for compliance reasons; enabling it is an explicit, at-your-own-risk build flag.

## Quick Start

### Docker Compose

Prerequisites: Docker and Docker Compose.

```bash
cp .env.example .env
docker compose up --build
```

Open `http://localhost:3018` by default. Runtime data is persisted in the ignored local `data/` directory.

To build optional dependency groups into the image, set `BACKEND_EXTRAS` before building:

```bash
BACKEND_EXTRAS="shadow forecast" docker compose up --build
```

Installing a Forecast extra does not download or activate a model checkpoint. Provisioning is a separate operator action.

The image ships a pinned Codex CLI, and Compose mounts the host `${HOME}/.codex` read-only into the container, so complete Codex login on the host first. On Windows, set `CODEX_HOME_HOST` in `.env` because `HOME` is usually unset. Override the bundled version with `CODEX_CLI_VERSION=0.144.3 docker compose up --build`. The Codex CLI mode lets the container read local Codex credentials and should only be enabled on trusted machines; the credential mount is read-only and never written into the image.

### Local Development

Prerequisites: Python 3.11+, Node 20+, [uv](https://docs.astral.sh/uv/), and pnpm 11.

One-shot launcher (checks dependencies, frees ports, starts both sides):

```bash
./dev.sh                   # Windows: .\dev.ps1
```

Or start each side manually:

```bash
cd backend
uv sync --extra dev
uv run uvicorn app.main:app --reload --port 3018
```

In another terminal:

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

Useful optional backend groups:

```bash
cd backend
uv sync --extra shadow
uv sync --extra forecast
uv sync --extra backtest
```

For a first-run walkthrough (credential detection, post-market pipeline, watchlist, screening, backtest, monitoring) see [docs/features.md](docs/features.md).

## Main Workflows

| Area | Workflow |
| --- | --- |
| Market and portfolio operations | Synchronize governed data, maintain accounts and holdings, configure monitoring rules, inspect delivery history, and receive SSE updates. |
| Screening and market sentiment | Scan with built-in or custom strategies, browse date-navigated pool snapshots, track the limit-up ladder, concept rotation, market phase, and mainlines. |
| Decision support | Inspect a deterministic playbook, compare any bounded AI adjustment with its baseline, and review a replay that has no model dependency. |
| Factor and strategy research | Define validated factor expressions, evaluate IC and RankIC, run backtests and walkforward or robustness validation, mine candidates with nested out-of-sample gating, and compare retained research artifacts. |
| AI analysis | Read evidence-backed reports with data-quality context, source provenance, cross-check outcomes, and lifecycle proposals. |
| Advanced research | Run attributable viewpoints, governed experiments, controlled evolution gates, and authorized agent jobs. |
| Optional research | Import Shadow executions, maintain thesis evidence, or inspect local Kronos forecast paths and quantiles. |

## Optional Modules

### Shadow Account

Shadow imports are research-only. Execution logs become immutable evidence sets, explainable candidate rules, and chronological in-sample/out-of-sample evaluations. Retention does not activate a strategy, broker connection, or market action.

### Thesis Tracking

Theses are immutable versions with valuation anchors, bounded invalidation conditions, due evidence checks, and explicit human confirmation or rejection. The public history is principal and instrument scoped.

### Kronos Forecasting

Forecasting uses a local catalog of pinned model/tokenizer identities. It validates source, configuration, and weight bytes before execution; stores paths and P10/P50/P90 quantiles as immutable artifacts; and runs bounded worker processes with local-only model loading.

## Testing

Backend tests use uv and optional extras as needed:

```bash
cd backend
uv run --extra dev pytest
uv run --extra dev --extra shadow pytest tests/shadow tests/forecast
```

Frontend browser tests use Playwright:

```bash
cd frontend
pnpm exec playwright test
```

The repository also includes Compose, real-host, and final machine-report verification contracts for the governed workflows.

## Data and Configuration

- Do not commit `.env`, `data/`, local databases, checkpoints, or browser test results.
- Start from `.env.example` and keep credentials local.
- Use only data sources and model checkpoints you are authorized to access.
- Treat model output as research material, not a trading instruction or guaranteed return. Backtest results do not represent future returns.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Upstream synchronization notes](docs/UPSTREAM-SYNC.md)
- [Deployment and operations](docs/deployment.md)
- [Deployment verification checklist](docs/deploy-verification.md)
- [Configuration reference](docs/configuration.md)
- [Feature handbook](docs/features.md)
- [Strategy system](docs/strategy.md)
- [Factor and strategy mining](docs/mining.md)
- [Market phase and mainline identification](docs/market-phase.md)
- [Secondary development guide](docs/secondary-development.md)
- [Custom data sources](docs/custom-data-source.md)
- [Plugin development](docs/plugin-development.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Project scope and constraints](.planning/PROJECT.md)
- [Phase roadmap](.planning/ROADMAP.md)

## Origin and License

AthenaQuant began from the [tickflow-stock-panel](https://github.com/shy3130/tickflow-stock-panel) codebase and retains an upstream synchronization path. It adds independently governed domains and does not represent, affiliate with, or receive endorsement from TickFlow or the upstream project.

The inherited upstream disclaimer still applies: the workbench is for study and quantitative research only, is not investment advice, and data accuracy follows the TickFlow provider. The optional stock-sdk data plugin follows its own ISC license.

See [LICENSE](LICENSE) for licensing information.
