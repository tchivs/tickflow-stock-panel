# Codebase Structure

**Analysis Date:** 2026-07-10

## Directory Layout

```
AthenaQuant/
├── backend/                     # Python FastAPI backend
│   ├── app/
│   │   ├── __init__.py          # Package root, UTF-8 enforcement, version
│   │   ├── main.py              # FastAPI app factory, lifespan, CORS, auth middleware
│   │   ├── config.py            # Pydantic settings from .env / env vars
│   │   ├── desktop.py           # pywebview desktop client entry point
│   │   ├── market_time.py       # A-share market time utilities (Beijing time)
│   │   ├── parquet.py           # Parquet schema definitions + scan helpers
│   │   ├── secrets_store.py     # Local secrets persistence (secrets.json)
│   │   ├── api/                 # REST API route modules
│   │   ├── backtest/            # Backtesting engine
│   │   ├── data_providers/      # Market data provider abstraction
│   │   ├── indicators/          # Technical indicator computation pipeline
│   │   ├── jobs/                # Scheduled background jobs
│   │   ├── plugins/             # Sidecar plugins (Node.js SDK bridge)
│   │   ├── services/            # Business logic services
│   │   ├── strategy/            # Strategy engine, monitoring, AI generation
│   │   └── tickflow/            # TickFlow SDK adaptation layer
│   ├── scripts/                 # Utility scripts
│   ├── tests/                   # Unit/integration tests
│   ├── pyproject.toml           # Python project metadata + dependencies
│   └── uv.lock                  # uv locked dependency versions
├── frontend/                    # React SPA frontend
│   ├── src/
│   │   ├── main.tsx             # React entry point
│   │   ├── index.css            # Tailwind + design system CSS variables
│   │   ├── router.tsx           # React Router configuration
│   │   ├── components/          # Reusable UI components
│   │   ├── pages/               # Page-level components
│   │   └── lib/                 # Shared utilities, stores, API client
│   ├── public/                  # Static assets
│   ├── index.html               # HTML entry point
│   ├── package.json             # npm dependencies
│   ├── vite.config.ts           # Vite build config
│   ├── tailwind.config.ts       # Tailwind CSS theme
│   └── tsconfig.json            # TypeScript configuration
├── data/                        # Runtime data directory (parquet, config, ssecrets)
├── docs/                        # Project documentation
├── packaging/                   # PyInstaller and Inno Setup packaging
├── screenshots/                 # Screenshots for README
├── .github/                     # GitHub workflows / CI
├── .planning/                   # GSD planning artifacts
├── docker-compose.yml           # Docker Compose production stack
├── Dockerfile                   # Multi-stage production Dockerfile
├── tiers.yaml                   # Capability tier definitions (free/starter/pro/expert)
├── VERSION                      # Version file
├── dev.sh                       # Linux dev startup script
├── dev.ps1                      # Windows dev startup script
└── README.md                    # Project readme
```

## Directory Purposes

### `backend/app/` — Backend Application Root

- **Purpose:** Core Python package containing all backend logic
- **Contains:** FastAPI app, config, API routes, services, data layer, strategy engine
- **Key files:**
  - `main.py`: FastAPI app factory, lifespan (service initialization), CORS, auth middleware, 20+ route includes, exception handlers
  - `config.py`: Pydantic `Settings` class — env-based configuration with path resolution for frozen/non-frozen modes
  - `desktop.py`: pywebview desktop wrapper — single-instance lock, port discovery, uvicorn thread manager
  - `secrets_store.py`: Local JSON file I/O for secrets (API keys, endpoints) in `data/user_data/secrets.json`

### `backend/app/api/` — REST API Routes

- **Purpose:** HTTP request handlers — validation, orchestration, response serialization
- **Contains:** 20+ route modules, each registered in `main.py`
- **Key files:**
  - `routes.py`: Core routes — `/health`, `/api/capabilities`, `/api/capabilities/redetect`
  - `auth.py`: Auth API — setup password, login, logout, session validation
  - `kline.py`: Kline data endpoints
  - `screener.py`: Screener preset + custom + SQL queries
  - `backtest.py`: Backtest runs and optimizer
  - `stock_analysis.py`: Key levels, AI analysis streaming
  - `signals.py`: Custom signal CRUD
  - `monitor_rules.py`: Monitor rule CRUD
  - `data.py`: Data status, sync operations
  - `strategy.py`: Strategy listing, execution, code generation
  - `pipeline.py`: Pipeline (after-hours sync) triggers
  - `watchlist.py`: User watchlist management
  - `financials.py`: Financial data endpoints
  - + additional modules: `indices.py`, `intraday.py`, `overview.py`, `analysis.py`, `ext_data.py`, `rps.py`, `market_recap.py`, `alerts.py`, `settings.py`

### `backend/app/services/` — Business Logic Services

- **Purpose:** Orchestration layer — business logic, data coordination, cross-cutting logic
- **Contains:** 34 service modules
- **Key files:**
  - `quote_service.py`: Real-time quote polling, enriched cache, SSE broadcasting (~1303 lines)
  - `screener.py`: Preset strategies, custom screening, DuckDB SQL screening with Polars expressions (~676 lines)
  - `stock_analyzer.py`: AI-driven stock analysis — K-line + financials + LLM streaming (~310 lines)
  - `market_overview_builder.py`: Market overview dashboard data
  - `ai_provider.py`: LLM provider abstraction (OpenAI-compatible)
  - `ai_reports.py`: AI-generated report management
  - `backtest.py`: Backtest execution service (frontend to engine bridge)
  - `auth.py`: Password auth (PBKDF2), session management (~214 lines)
  - `watchlist.py`: Watchlist data orchestration
  - `rps_rotation.py`: RPS rotation metric computation
  - `financial_analyzer.py`: Financial statement analysis
  - `financial_sync.py`: Financial data synchronization
  - `market_recap.py`: Daily market recap generation
  - `market_recap_reports.py`: Recap report persistence
  - `webhook_adapter.py`: Webhook notification dispatch (Feishu/Webhook)
  - `wecom_bot_service.py`: WeCom (WeChat Work) bot integration
  - `notify_adapter.py`: Cross-channel notification routing
  - `instrument_sync.py`: Instruments (securities master) sync
  - `kline_sync.py`: K-line data synchronization
  - `index_sync.py`: Index data sync
  - `alert_store.py`: Alert persistence
  - `ext_data.py`: Extended data (concept/industry tables)
  - `ext_pull.py`: Extended data pull scheduler
  - `ext_presets.py`: Built-in extended data presets
  - `extend_history.py`: Historical data backfill
  - `depth_service.py`: Level-2 market depth (sealed limit-up/down detection)
  - `strategy_cache.py`: Strategy execution result cache
  - `preferences.py`: User preferences persistence
  - `pipeline_jobs.py`: Pipeline job store and progress tracking

### `backend/app/tickflow/` — TickFlow Adaptation Layer

- **Purpose:** SDK encapsulation, capability detection, repository, scheduling
- **Contains:** 8 modules
- **Key files:**
  - `client.py`: Singleton sync/async SDK client factories — free vs paid endpoint routing (~137 lines)
  - `capabilities.py`: `Cap` enum, `CapabilityLimits`, `CapabilitySet`, `CapabilityDenied` (~76 lines)
  - `policy.py`: Probe-based capability detection — attempts minimal-cost API calls, caches to `capabilities.json` (~606 lines)
  - `repository.py`: `DataStore` + `KlineRepository` — three-tier cache (DuckDB/Polars-scan/Polars-memory), ~1841 lines
  - `scheduler.py`: Rate-limited API scheduling
  - `rate_limits.py`: API rate limit configuration
  - `pools.py`: Stock pool definitions (demo symbols, universes)
  - `pools.py`: Stock pool utilities

### `backend/app/strategy/` — Strategy System

- **Purpose:** Strategy loading, execution, AI generation, monitoring
- **Contains:** Engine, monitor, AI generator, config, custom signals, prompts, built-in strategies
- **Key files:**
  - `engine.py`: `StrategyEngine` — loads Python modules from directories, executes two-phase filtering + scoring (~525 lines)
  - `monitor.py`: `StrategyMonitorService` + `MonitorRuleEngine` — real-time signal checking, alerting (~948 lines)
  - `ai_generator.py`: AI strategy code generation — prompt construction + LLM call + code validation
  - `prompt_builder.py`: Prompt template assembly for strategy generation
  - `config.py`: Strategy configuration utilities
  - `custom_signals.py`: User-defined custom signal expression builder
  - `monitor_rules.py`: Monitor rule persistence (load/save rules to JSON)
  - `prompts/`: Markdown prompt templates for AI strategy generation
    - `strategy-builder-step1.md`
    - `strategy-builder-step2.md`
    - `strategy-guide.md`
    - `strategy-guide-compact.md`
    - `strategy-example.md`
  - `builtin/`: 18 built-in strategy modules
    - `trend_breakout.py`, `ma_golden_cross.py`, `macd_golden.py`
    - `boll_breakout.py`, `limit_up_momentum.py`, `oversold_bounce.py`
    - `volume_price_surge.py`, `strong_open.py`, `pullback_ma20_bounce.py`
    - `pullback_to_support.py`, `n_day_low_reversal.py`
    - `high_turnover_surge.py`, `consecutive_limit_ups.py`
    - `near_limit_up.py`, `oversold_reversal.py`
    - `low_volatility_leader.py`, `bullish_alignment.py`
    - `broken_board_recovery.py`

### `backend/app/backtest/` — Backtesting Engine

- **Purpose:** Historical simulation of trading strategies
- **Contains:** 5 modules
- **Key files:**
  - `engine.py`: Matching engine, trade recording, portfolio simulation, performance metrics (~1647 lines)
  - `strategy.py`: Strategy integration for backtest (bridge between strategy engine and backtest engine)
  - `factor.py`: Factor computation for multi-factor backtests
  - `optimizer.py`: Parameter grid search optimization

### `backend/app/data_providers/` — Data Provider System

- **Purpose:** Market data source abstraction
- **Contains:** Base protocol, TickFlow implementation, normalizer, registry, custom provider
- **Key files:**
  - `base.py`: `MarketDataProvider` protocol + `ProviderCapabilities` dataclass (~68 lines)
  - `tickflow_provider.py`: `TickFlowProvider` — wraps TickFlow SDK calls, normalizes output (~120 lines)
  - `normalizer.py`: DataFrame normalization functions (instruments, daily, adj factors)
  - `registry.py`: Provider registry (`get_provider()` factory)
  - `schemas.py`: Provider-specific schemas
  - `custom/`: Custom data source provider (user-configurable external sources)

### `backend/app/indicators/` — Technical Indicators

- **Purpose:** Enriched data computation pipeline
- **Contains:** 3 modules
- **Key files:**
  - `pipeline.py`: Full enriched pipeline — 50+ technical indicators computed via Polars expressions (~1658 lines)
  - `levels.py`: Key price level computation (support/resistance, pivot points, Bollinger bands)

### `backend/app/jobs/` — Background Jobs

- **Purpose:** Scheduled background data processing
- **Contains:** 2 modules
- **Key files:**
  - `daily_pipeline.py`: APScheduler-based after-hours sync — instruments, klines, adj factors, enriched computation (~969 lines)

### `backend/app/plugins/` — Plugin System

- **Purpose:** Sidecar plugins for alternate data access
- **Contains:** `stocksdk/` (Node.js SDK bridge)
- **Key files:**
  - `stocksdk/__init__.py`: Plugin registration
  - `stocksdk/bridge.py`: Python bridge to Node.js process
  - `stocksdk/bridge.mjs`: Node.js SDK client script
  - `stocksdk/provider.py`: Provider wrapping the Node.js bridge
  - `stocksdk/plugin.yaml`: Plugin metadata

### `backend/tests/` — Test Suite

- **Purpose:** Unit and integration tests
- **Contains:** 19 test files + `backtest/` subdirectory (8 test files)
- **Key files:**
  - `test_ai_generator_prompt.py`, `test_ai_provider.py`, `test_ai_strategy_meta_normalize.py`
  - `test_backtest_etf.py`, `test_stocksdk_provider.py`
  - `test_strategy_*.py` (6 files covering build_stream, code_save, param_normalize, etc.)
  - `test_screener_etf.py`, `test_monitor_etf.py`
  - `test_pipeline_and_monitor_fixes.py`
  - `backtest/`: `test_cost_model.py`, `test_engine_portfolio.py`, `test_optimizer_*.py` (3 files), `test_strategy_backtest_correctness.py`, `test_robustness_metrics.py`, `test_full_simulation_tail.py`

### `frontend/src/` — React Frontend

- **Purpose:** Single-page application UI
- **Contains:** Entry point, router, components, pages, utility libraries
- **Key files:**
  - `main.tsx`: React root — QueryClient + RouterProvider (51 lines)
  - `router.tsx`: React Router config — lazy-loaded pages, onboarding guard (97 lines)
  - `index.css`: Tailwind directives, CSS variables for dark/light theme (79 lines)
  - `components/Layout.tsx`: App shell — sidebar nav, SSE stream status, theme toggle, onboarding, capability-based menu (698 lines)

### `frontend/src/pages/` — Page Components

- **Purpose:** Top-level page components corresponding to routes
- **Contains:** 23 page files
- **Key files:**
  - `Dashboard.tsx`, `Watchlist.tsx`, `Screener.tsx`, `Backtest.tsx`
  - `StockAnalysis.tsx`, `Financials.tsx`, `Analysis.tsx`, `AnalysisDetail.tsx`
  - `Monitor.tsx`, `Trading.tsx`, `Data.tsx`, `Settings.tsx`
  - `Indices.tsx`, `ConceptAnalysis.tsx`, `IndustryAnalysis.tsx`
  - `Review.tsx`, `LimitUpLadder.tsx`, `Branding.tsx`
  - `Auth.tsx`, `Onboarding.tsx`, `Dev.tsx`
  - `backtest/`: Backtest sub-page components
  - `settings/`: Settings tab components

### `frontend/src/components/` — Reusable UI Components

- **Purpose:** Reusable components, many with domain-specific subdirectories
- **Contains:** 33 component files
- **Key groupings:**
  - `data/`: Data-related components
  - `ext-data/`: Extended data components
  - `financials/`: Financial statement display components
  - `monitor/`: Monitor rule editing components
  - `screener/`: Screener results components
  - `signals/`: Signal indicator components
  - `stock-analysis/`: Stock analysis UI (profile, host, bubble)
  - `stock-table/`: Stock list table components
- **Key files:**
  - `Layout.tsx`, `CandlestickChart.tsx`, `EChartsCandlestick.tsx`
  - `EChartsIntraday.tsx`, `StockDailyKChart.tsx`, `StockIntradayChart.tsx`
  - `Modal.tsx`, `Toast.tsx`, `AlertToast.tsx`
  - `ColumnCustomizer.tsx`, `ListColumnCustomizer.tsx`
  - `RpsRotationDialog.tsx`, `StockInfoBar.tsx`, `StockPanel.tsx`

### `frontend/src/lib/` — Shared Utilities

- **Purpose:** State stores, API client, helpers, hooks
- **Contains:** 32 module files
- **Key files:**
  - `api.ts`: Unified fetch wrapper — `request<T>()`, typed API functions (~2221 lines)
  - `queryKeys.ts`: TanStack Query key constants
  - `useSharedQueries.ts`: Shared TanStack Query hooks (settings, capabilities, etc.)
  - `useSharedMutations.ts`: Shared TanStack Query mutations
  - `useQuoteStream.ts`: SSE stream hook for real-time data
  - `stockAnalysisStore.ts`: Stock analysis state
  - `aiReportStore.ts`: AI report state
  - `reviewStore.ts`: Review state
  - `board.ts`: Board/dashboard state
  - `theme.ts`: Dark/light theme toggle
  - `storage.ts`: Local storage utilities
  - `format.ts`: Number/date formatting utilities
  - `cn.ts`: Tailwind class merge utility (clsx + tailwind-merge)
  - `colors.ts`: Color utilities for charts
  - `signals.ts`: Signal display configuration
  - `monitorBadge.ts`: Monitor badge count state

### `frontend/src/components/` sub-directories

- **Purpose:** Domain-specific component groups extracted from parent
- **`data/`:** Data management UI components
- **`ext-data/`:** Extended data table UI
- **`financials/`:** Financial statements, AI analysis host/bubble
- **`monitor/`:** Monitor rule editor components
- **`screener/`:** Screener results table components
- **`signals/`:** Signal indicator components
- **`stock-analysis/`:** Stock analysis profile, host, bubble components
- **`stock-table/`:** Stock list table with columns

## Key File Locations

**Entry Points:**
- `backend/app/main.py`: FastAPI application (uvicorn target)
- `backend/app/desktop.py`: Desktop application (pywebview)
- `frontend/src/main.tsx`: React SPA entry point
- `frontend/index.html`: HTML shell

**Configuration:**
- `backend/app/config.py`: Pydantic-settings (env/`.env` → Python)
- `backend/pyproject.toml`: Python dependencies, tools (ruff, pytest)
- `frontend/package.json`: Node.js dependencies
- `frontend/vite.config.ts`: Vite bundler config (proxy, aliases, chunks)
- `frontend/tailwind.config.ts`: Tailwind CSS theme (colors, fonts, radii)
- `frontend/tsconfig.json`: TypeScript config
- `tiers.yaml`: Capability tier definitions
- `Dockerfile`: Production multi-stage build
- `docker-compose.yml`: Single-service Docker Compose
- `.env.example`: Environment template (never commit real `.env`)

**Core Logic:**
- `backend/app/tickflow/repository.py`: Data store + repository (~1841 lines)
- `backend/app/services/quote_service.py`: Real-time quote engine (~1303 lines)
- `backend/app/backtest/engine.py`: Backtest engine (~1647 lines)
- `backend/app/indicators/pipeline.py`: Technical indicator computation (~1658 lines)
- `backend/app/jobs/daily_pipeline.py`: Scheduled data pipeline (~969 lines)
- `backend/app/strategy/engine.py`: Strategy execution engine (~525 lines)
- `backend/app/strategy/monitor.py`: Strategy monitoring + alerting (~948 lines)
- `backend/app/services/screener.py`: Stock screener service (~676 lines)

**Testing:**
- `backend/tests/`: 19 test files + `backtest/` subdirectory with 8 test files
- Tests cover: strategies, backtest engine, AI generator, parquet schema, monitoring, screener, provider integration

## Naming Conventions

**Files:**
- Python: `snake_case.py` (e.g., `stock_analysis.py`, `quote_service.py`, `daily_pipeline.py`)
- TypeScript/React: `PascalCase.tsx` for components (e.g., `CandlestickChart.tsx`, `Layout.tsx`), `camelCase.ts` for utilities (e.g., `api.ts`, `queryKeys.ts`, `cn.ts`)
- CSS: `index.css` only (Tailwind-based, no CSS modules)
- Markdown: `snake_case.md` (docs), `UPPERCASE.md` (planning artifacts)
- Docker: `Dockerfile` (no extension)

**Directories:**
- Python packages: `snake_case/` (e.g., `tickflow/`, `data_providers/`, `backtest/`)
- Frontend components: `kebab-case/` for domain groups (e.g., `stock-analysis/`, `ext-data/`)
- Frontend pages: `PascalCase.tsx` files in `pages/`
- Frontend stores/libraries: `camelCase.ts` files in `lib/`

**Functions:**
- Python: `snake_case()` (e.g., `compute_levels()`, `detect_capabilities()`, `_load_enriched_for_date()`)
- TypeScript: `camelCase()` (e.g., `useQuoteStream()`, `tierRank()`, `_redirectToLogin()`)

**Variables:**
- Python: `snake_case` (e.g., `data_dir`, `enriched_cache`, `_sync_client`)
- TypeScript: `camelCase` (e.g., `queryClient`, `redirecting`, `isNotInit`)

**Classes:**
- Python: `PascalCase` (e.g., `KlineRepository`, `QuoteService`, `CapabilitySet`, `StrategyEngine`)
- TypeScript: `PascalCase` for components/types (e.g., `CapabilitiesResponse`, `FinancialStatus`), interfaces have no prefix

## Where to Add New Code

**New Feature (Backend):**
- API route: `backend/app/api/<feature_name>.py` — new `router = APIRouter(prefix="/api/<feature>")`
- Register router in `backend/app/main.py` (add `app.include_router()` call)
- Service logic: `backend/app/services/<feature_service>.py`
- Strategy (if applicable): `backend/app/strategy/builtin/<strategy_name>.py`
- Tests: `backend/tests/test_<feature>.py`

**New Feature (Frontend):**
- Page: `frontend/src/pages/<FeatureName>.tsx` — add lazy import + route in `frontend/src/router.tsx`
- Component: `frontend/src/components/<FeatureComponent>.tsx`
- Grouped components: `frontend/src/components/<feature-group>/<Component>.tsx`
- Shared state/hooks: `frontend/src/lib/<featureName>.ts` or `use<FeatureName>.ts`
- API types: Add interfaces to `frontend/src/lib/api.ts`

**New Data Provider:**
- Implementation: `backend/app/data_providers/<provider_name>_provider.py` (implement `MarketDataProvider` protocol)
- Register in `backend/app/data_providers/registry.py`

**New Built-in Strategy:**
- Strategy module: `backend/app/strategy/builtin/<strategy_name>.py`
- Contract: Export `META` dict + `SCORE_FN` function

**Utilities:**
- Python shared helpers: `backend/app/services/` or new sub-package if domain-specific
- TypeScript shared helpers: `frontend/src/lib/<utility>.ts`

**Configuration:**
- New env var: Add field to `Settings` class in `backend/app/config.py`, add default in `.env.example`
- New tier capability: Add entry in `tiers.yaml`, add `Cap` enum in `backend/app/tickflow/capabilities.py`

## Special Directories

**`data/`:**
- Purpose: Runtime data — parquet files, user config, caches, logs
- Generated: Yes (runtime, not committed)
- Committed: No (in `.gitignore`)
- Subdirectories: `kline_daily/`, `kline_daily_enriched/`, `kline_minute/`, `kline_index_daily/`, `kline_etf_daily/`, `adj_factor/`, `financials/`, `instruments/`, `pools/`, `backtest_results/`, `screener_results/`, `ai_cache/`, `user_data/`, `depth5/`

**`packaging/`:**
- Purpose: PyInstaller spec + Inno Setup installer configuration for desktop distribution
- Generated: No (source)
- Committed: Yes
- Key files: `athenaquant.spec` (PyInstaller spec), `athenaquant.iss` (Inno Setup script), icon files

**`frontend/dist/`:**
- Purpose: Built static assets for production
- Generated: Yes (`pnpm build`)
- Committed: No (in `.gitignore`)
- Hosted by FastAPI `StaticFiles` mount at `/assets/`

**`backend/app/strategy/builtin/`:**
- Purpose: Built-in trading strategies shipped with the application
- Generated: No (source)
- Committed: Yes
- 18 strategy modules, auto-loaded by `StrategyEngine`

**`backend/app/strategy/prompts/`:**
- Purpose: Markdown templates for AI strategy code generation
- Generated: No (source)
- Committed: Yes
- 5 markdown files forming a two-step AI prompt chain

**`backend/app/plugins/`:**
- Purpose: Optional plugin modules (e.g., Node.js SDK bridge)
- Generated: No (source)
- Committed: Yes (source), `node_modules/` is gitignored

---

*Structure analysis: 2026-07-10*
