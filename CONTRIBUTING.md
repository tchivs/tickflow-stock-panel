# Contributing to AthenaQuant

## Scope

AthenaQuant is a self-hosted research and decision-support application. Contributions must preserve its local-data, server-owned authority, reproducibility, and auditability boundaries. Do not add automatic broker execution, unpinned model downloads, or browser-controlled authorization paths.

## Development Setup

Use Python 3.11+, Node 20+, uv, and pnpm 11.

pnpm 11 permits only the project-approved `esbuild` lifecycle script. Do not approve additional dependency scripts without a documented supply-chain review.

```bash
cd backend
uv sync --extra dev
uv run --extra dev pytest
```

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm build
```

Optional modules must be tested with their dependency groups enabled:

```bash
cd backend
uv run --extra dev --extra shadow pytest tests/shadow
uv run --extra dev --extra forecast pytest tests/forecast
```

## Change Expectations

- Keep changes narrowly scoped and update tests for behavioral changes.
- Do not commit `.env`, `data/`, credentials, local checkpoints, or generated browser reports.
- Preserve SQLite migrations, immutable research artifacts, and append-only audit records.
- Keep Forecast assets pinned to immutable revisions and verified SHA-256 values.
- Treat TickFlow as a market-data provider name, not the product brand.
- Update `CHANGELOG.md` and relevant documentation for user-visible behavior.

## Pull Requests

Describe the user-facing change, validation commands run, data or schema impact, optional dependency requirements, and any deliberate limitation. For security-sensitive paths, use the process in [SECURITY.md](SECURITY.md) instead of a public issue.
