# AthenaQuant

AthenaQuant is a self-hosted quantitative research platform for individual A-share investors. It combines governed market data, portfolio monitoring, reproducible factor and strategy research, auditable decision plans, and evidence-first AI research in one deployable application.

It is designed for research and decision support. It does not place live broker orders.

## What It Provides

- Governed market-data synchronization backed by Parquet, DuckDB, and Polars.
- Portfolio accounts, holdings, P&L, monitoring rules, delivery history, and shared SSE updates.
- Deterministic trade playbooks with bounded, audited AI adjustments and AI-free historical replay.
- Factor DSL, factor evaluation, strategy backtests, reproducible experiment artifacts, and retained comparisons.
- Evidence-grounded AI analysis with source quality, numerical cross-checks, report provenance, and signal lifecycle review.
- Advanced research workflows for attributed viewpoints, controlled experiments, strategy evolution, authorized jobs, and constrained custom-strategy execution.
- Optional Shadow Account, versioned investment theses, and local-only Kronos forecasting modules.

## Architecture Boundaries

- Time-series data stays in Parquet and is queried through DuckDB and Polars.
- SQLite stores operational state, append-only facts, monitoring history, and workflow audit records.
- The default deployment is one Docker Compose service with no external database or message queue.
- Optional modules are independently enabled. The core application does not import Shadow or Forecast heavy dependencies by default.
- Forecast assets are provisioned explicitly, use immutable revisions and SHA-256 validation, and run locally without runtime model downloads.
- Browser clients submit bounded intent only. Authorization, identities, evidence, lifecycle transitions, and execution authority remain server-owned.

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

### Local Development

Prerequisites: Python 3.11+, Node 20+, [uv](https://docs.astral.sh/uv/), and pnpm 11.

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

## Main Workflows

| Area | Workflow |
| --- | --- |
| Market and portfolio operations | Synchronize governed data, maintain accounts and holdings, configure monitoring rules, inspect delivery history, and receive SSE updates. |
| Decision support | Inspect a deterministic playbook, compare any bounded AI adjustment with its baseline, and review a replay that has no model dependency. |
| Factor and strategy research | Define validated factor expressions, evaluate IC and RankIC, run backtests, and compare retained research artifacts. |
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
- Treat model output as research material, not a trading instruction or guaranteed return.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Upstream synchronization notes](docs/UPSTREAM-SYNC.md)
- [Deployment and operations](docs/deployment.md)
- [Configuration reference](docs/configuration.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Project scope and constraints](.planning/PROJECT.md)
- [Phase roadmap](.planning/ROADMAP.md)

## Origin and License

AthenaQuant began from the [tickflow-stock-panel](https://github.com/shy3130/tickflow-stock-panel) codebase and retains an upstream synchronization path. It adds independently governed domains and does not represent, affiliate with, or receive endorsement from TickFlow or the upstream project.

See [LICENSE](LICENSE) for licensing information.
