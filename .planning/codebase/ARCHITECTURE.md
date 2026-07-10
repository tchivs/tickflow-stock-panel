<!-- refreshed: 2026-07-10 -->
# Architecture

**Analysis Date:** 2026-07-10

## System Overview

```text
┌─────────────────────────────────────────────────────────────────────┐
│                         Frontend (React SPA)                        │
│  `frontend/src/`                                                    │
│  Pages → Components → TanStack Query → api.ts → HTTP/SSE           │
└───────────────────────────┬─────────────────────────────────────────┘
                            │  HTTP (JSON) / SSE (real-time)
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend (Layer 1)                       │
│  `backend/app/main.py`                                              │
│  CORS → Auth Middleware → Router Dispatcher → /api/*                │
├──────────────────┬──────────────────┬───────────────────────────────┤
│   API Routes     │   Services       │  Strategy/Monitor             │
│  `backend/app/   │  `backend/app/   │  `backend/app/strategy/       │
│   api/*.py`      │   services/*.py` │   strategy/*.py`              │
└────────┬─────────┴────────┬─────────┴─────────────────┬─────────────┘
         │                  │                           │
         ▼                  ▼                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Data Layer (Layer 2)                           │
│  TickFlow SDK (`tickflow/` + `data_providers/`)                    │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Repository Layer (`app/tickflow/repository.py`)             │    │
│  │  DuckDB (cold queries) + Polars cache (hot path) + Parquet  │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
         │                           │
         ▼                           ▼
┌────────────────────┐   ┌──────────────────────────────┐
│  Local Parquet     │   │  TickFlow Cloud API          │
│  `data/`           │   │  (free-api / paid endpoints) │
│  (file storage)    │   │  (external market data)      │
└────────────────────┘   └──────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Entry Point | FastAPI app factory, lifespan (init all services), CORS, auth middleware | `backend/app/main.py` |
| Core Router | Health check, capability detection | `backend/app/api/routes.py` |
| API Routes | 20+ route modules covering stock analysis, screener, backtest, data, etc. | `backend/app/api/*.py` |
| Config | Pydantic-settings from `.env` / environment variables | `backend/app/config.py` |
| TickFlow Client | Singleton SDK wrapper for TickFlow (sync/async) | `backend/app/tickflow/client.py` |
| Capabilities | Enum of all capabilities, tier-based detection | `backend/app/tickflow/capabilities.py`, `backend/app/tickflow/policy.py` |
| Repository | Data store with DuckDB + Polars + Parquet storage | `backend/app/tickflow/repository.py` |
| Data Providers | Provider abstraction protocol for market data sources | `backend/app/data_providers/base.py` |
| TickFlow Provider | TickFlow-specific provider implementation | `backend/app/data_providers/tickflow_provider.py` |
| Custom Provider | User-defined external data sources (plugin system) | `backend/app/data_providers/custom/` |
| Indicators Pipeline | Enriched parquet computation (OHLCV + 50+ technical indicators) | `backend/app/indicators/pipeline.py` |
| Key Levels | Support/resistance level computation | `backend/app/indicators/levels.py` |
| Strategy Engine | Load and execute strategies from Python modules | `backend/app/strategy/engine.py` |
| Strategy Monitor | Real-time strategy signal checking + alerting | `backend/app/strategy/monitor.py` |
| AI Generator | LLM-powered strategy code generation | `backend/app/strategy/ai_generator.py` |
| Backtest Engine | Pure Polars/NumPy backtesting with matching + portfolio + metrics | `backend/app/backtest/engine.py` |
| Backtest Optimizer | Parameter grid search | `backend/app/backtest/optimizer.py` |
| Quote Service | Real-time market data polling + enriched cache + SSE | `backend/app/services/quote_service.py` |
| Screener Service | Preset + custom stock screening (Polars expressions) | `backend/app/services/screener.py` |
| Daily Pipeline | Scheduled after-hours data sync (APScheduler) | `backend/app/jobs/daily_pipeline.py` |
| Secrets Store | Local encrypted secrets management | `backend/app/secrets_store.py` |
| Auth Service | Password-based auth (PBKDF2) + session tokens | `backend/app/services/auth.py` |
| Market Time | A-share trading calendar/time utilities (Beijing time) | `backend/app/market_time.py` |
| Desktop Entry | pywebview desktop client (single-instance lock) | `backend/app/desktop.py` |
| Frontend Router | React Router with lazy-loaded pages | `frontend/src/router.tsx` |
| Frontend API Client | Unified fetch wrapper for all backend calls | `frontend/src/lib/api.ts` |
| Frontend Layout | App shell with nav + SSE stream + capability-based menu | `frontend/src/components/Layout.tsx` |

## Pattern Overview

**Overall:** Three-layer architecture with service-oriented decomposition

**Key Characteristics:**
- FastAPI backend serves both REST API (JSON) and static frontend SPA
- TickFlow SDK is the primary data source, abstracted behind `MarketDataProvider` protocol
- Capability-based feature gating — each API tier (free/starter/pro/expert) unlocks different capabilities
- Polars-native data processing across queries (no pandas dependency in hot paths)
- File-based storage with Parquet on local filesystem + DuckDB in-memory for SQL queries
- Strategy system uses Python module loader — strategies are standalone `.py` files dropped into directories
- Real-time data flows via poll-loop → enriched cache → SSE broadcast to connected frontends
- Desktop client wraps the same FastAPI app in pywebview (identical code path)

## Layers

**API Layer:**
- Purpose: HTTP entry points, request validation, response formatting
- Location: `backend/app/api/`
- Contains: 20+ route modules (stock_analysis, screener, backtest, signals, etc.)
- Depends on: Services layer, Strategy layer, TickFlow client, Repository
- Used by: Frontend (HTTP/SSE), external HTTP clients

**Services Layer:**
- Purpose: Business logic, data orchestration, cross-cutting concerns
- Location: `backend/app/services/`
- Contains: 34 service modules (quote_service, screener, auth, etc.)
- Depends on: Repository, TickFlow SDK, Backtest engine
- Used by: API layer

**Strategy Layer:**
- Purpose: Strategy loading, execution, monitoring, AI generation
- Location: `backend/app/strategy/`
- Contains: Engine, Monitor, AI Generator, Built-in strategies, Custom signals, Prompts
- Depends on: Repository (enriched data), Services (screener)
- Used by: API layer, Monitor service

**Data Layer:**
- Purpose: Data access, storage, provider abstraction
- Location: `backend/app/tickflow/`, `backend/app/data_providers/`
- Contains: Repository, Client, Capabilities, Policy, Providers (TickFlow, Custom)
- Depends on: TickFlow SDK, Parquet files, DuckDB, Polars
- Used by: Services layer, API layer, Strategy layer

**Plugins Layer:**
- Purpose: Sidecar plugins (e.g., Node.js SDK bridge)
- Location: `backend/app/plugins/stocksdk/`
- Contains: Python bridge + Node.js SDK for TickFlow alternative access
- Depends on: Node.js runtime (optional)
- Used by: Custom data provider path

## Data Flow

### Primary Request Path (HTTP API)

1. HTTP request hits FastAPI → `auth_middleware` checks session cookie (`backend/app/main.py:242-272`)
2. Request routed to API handler (e.g., `POST /api/screener/preset` in `backend/app/api/screener.py`)
3. Handler calls service layer (e.g., `ScreenerService.run_preset()` in `backend/app/services/screener.py`)
4. Service calls repository (`KlineRepository.get_enriched_latest()` in `backend/app/tickflow/repository.py`)
5. Repository serves from Polars memory cache (hot) or scans parquet files (cold)
6. Results flow back through service → handler → JSON response

### Real-time Market Data Flow

1. `QuoteService` background thread polls TickFlow `/get_by_universes` every ~15s (`backend/app/services/quote_service.py`)
2. Raw records written to kline_daily parquet (unadjusted prices)
3. Enriched cache updated in memory (OHLCV + technical indicators, ~50ms)
4. Enriched parquet written to disk
5. SSE notification sent to all connected subscribers
6. Frontend receives `quote_updated` event, triggers `@tanstack/react-query` invalidations
7. Strategy `MonitorRuleEngine` checks conditions against new data, pushes alerts

### After-hours Pipeline Flow

1. `APScheduler` triggers daily job at 09:10 and 15:30 (`backend/app/jobs/daily_pipeline.py`)
2. 09:10 — instruments sync (full overwrite)
3. 15:30 — Kline sync → adjust factors → enriched computation → DuckDB views refresh
4. Pipeline stages report progress via callback protocol
5. Cache invalidation triggers on stage completion

### Strategy Execution Flow

1. `StrategyEngine` loads strategies from 3 directories: `builtin/`, `custom/`, `ai/` (`backend/app/strategy/engine.py`)
2. Each strategy is a Python module with `META` dict and `SCORE_FN` function
3. Two-phase filtering: basic filter (price, market cap, volume, ST exclusion) → strategy filter (strategy-specific conditions)
4. Scoring sorts candidates by strategy's scoring function
5. Results cached in `strategy_cache.py` for hot-path reuse

## Key Abstractions

**MarketDataProvider Protocol:**
- Purpose: Abstract interface for external market data sources (TickFlow, Tushare, AkShare, etc.)
- Location: `backend/app/data_providers/base.py`
- Methods: `get_instruments()`, `get_daily()`, `get_adj_factors()`, `get_minute()`, `get_realtime()`
- Pattern: Structural typing via `Protocol` — any object matching the interface qualifies
- Implementations: `TickFlowProvider` (`backend/app/data_providers/tickflow_provider.py`), Custom providers (`backend/app/data_providers/custom/provider.py`)

**CapabilitySet:**
- Purpose: Runtime-feature gating based on user's tier (none/free/starter/pro/expert)
- Location: `backend/app/tickflow/capabilities.py`
- Usage: `capset.require(Cap.QUOTE_BATCH)` raises `CapabilityDenied` if tier lacks that capability
- Pattern: Probe-based detection in `backend/app/tickflow/policy.py` — tries minimal API calls, caches results to `capabilities.json`

**KlineRepository:**
- Purpose: Single unified data access point for all K-line/enriched data
- Location: `backend/app/tickflow/repository.py` (~1841 lines)
- Pattern: Three-tier cache (DuckDB for cold SQL → Polars scan_parquet for warm → Polars in-memory for hot enriched). Methods: `get_enriched_latest()`, `get_daily()`, `get_instruments()`, `get_historical()`

**Strategy Module:**
- Purpose: Standalone Python files defining a trading strategy
- Location: `backend/app/strategy/builtin/` (18 built-in strategies)
- Contract: Each module exports `META` (dict with id/name/params/description) and `SCORE_FN` (callable)
- Pattern: File-watch loading from three directories; executed via `importlib.util.spec_from_file_location()`

**Enriched Data Schema:**
- Purpose: Storage schema for computed OHLCV + technical indicators + signals
- Location: `backend/app/parquet.py` (schema definition) + `backend/app/indicators/pipeline.py` (computation)
- Storage: 14 columns in parquet (base OHLCV + turnover_rate, consecutive_limit_ups/downs)
- Runtime: 50+ computed indicators via Polars expressions (MAs, MACD, BOLL, KDJ, RSI, ATR, etc.)

## Entry Points

**FastAPI Server (primary):**
- Location: `backend/app/main.py`
- Triggers: `uvicorn app.main:app` (Docker) or `python -m app.desktop` (desktop)
- Responsibilities: App factory, service initialization, CORS, auth middleware, routing

**Desktop Client:**
- Location: `backend/app/desktop.py`
- Triggers: `python -m app.desktop` or packaged executable
- Responsibilities: Single-instance lock, port discovery, uvicorn thread, pywebview window

**Health:**
- Location: `backend/app/api/routes.py:13`
- Pattern: `GET /health` → `{"status": "ok", "version": "x.y.z", "mode": "none|free|api_key"}`

**Capabilities:**
- Location: `backend/app/api/routes.py:23`
- Pattern: `GET /api/capabilities` → tier label + capability limits dict

## Architectural Constraints

- **Threading:** Single-threaded async event loop (uvicorn). Background threads for QuoteService polling, webhook dispatch, backtest computation. `apscheduler` runs in asyncio mode.
- **Global state:** Module-level singletons in `backend/app/tickflow/client.py` (sync/async SDK clients), process-level history cache in `backend/app/services/screener.py`, module-level session store in `backend/app/services/auth.py`
- **Circular imports:** Avoided via lazy imports inside lifespan blocks (e.g., auth service, strategy modules imported at runtime within lifespan)
- **Data directory:** Every deployment (Docker, desktop, dev) must have a writable `data/` directory for parquet storage
- **Platform paths:** Frozen (PyInstaller) vs non-frozen path resolution handled in `backend/app/config.py` — critical for correct tier.yaml, static_dir, and data_dir resolution
- **No multi-user:** Single-user desktop/server design; auth uses PBKDF2 password + session tokens

## Anti-Patterns

### Module-level mutable state

**What happens:** Service-level caches and module-level dictionaries store mutable state at module scope (e.g., `_history_cache` dict in `backend/app/services/screener.py:23`, `_sessions` dict in `backend/app/services/auth.py:37`, `_sync_client` in `backend/app/tickflow/client.py:25`)

**Why it's wrong:** Module reloading across requests can cause stale state, and multi-worker setups (if ever introduced) would have divergent caches.

**Do this instead:** The codebase intentionally uses single-process deployment (single uvicorn worker + Gunicorn UvicornWorker not used). For single-process, this is acceptable and performs well. If multi-worker is needed, these should move to a shared cache (Redis / filesystem-based).

### Broad `except Exception` in lifespan

**What happens:** Nearly every initialization step in the lifespan handler (`backend/app/main.py:42-187`) wraps in `try/except Exception` to prevent any single service from blocking app startup.

**Why it's wrong:** Can silently swallow critical initialization failures, leading to partially-functioning services that log warnings but appear healthy.

**Do this instead:** Each service should have clear health-checkable status. The current approach is pragmatic for a self-hosted tool — the `GET /api/capabilities` endpoint exposes capability state to the frontend for graceful degradation.

### Large service modules

**What happens:** `backend/app/tickflow/repository.py` (~1841 lines), `backend/app/services/quote_service.py` (~1303 lines), `backend/app/backtest/engine.py` (~1647 lines), `backend/app/indicators/pipeline.py` (~1658 lines), `backend/app/jobs/daily_pipeline.py` (~969 lines), `backend/app/strategy/monitor.py` (~948 lines)

**Why it's wrong:** High cyclomatic density in a single file makes testing, reasoning about, and modifying behavior harder.

**Do this instead:** No current refactor needed — each file represents a cohesive module. But new features in these areas should be added as separate modules rather than extending the monolith further.

## Error Handling

**Strategy:** Multi-layered with graceful degradation
- API handlers return HTTP error codes (401, 403, 422, 500)
- CapabilityDenied exceptions → 403 via FastAPI exception handler (`backend/app/main.py:308-313`)
- Service-level errors logged and surfaced as HTTP errors with detail messages
- Initialization errors in lifespan are caught, logged as warnings, and non-blocking
- Frontend api.ts catches errors → toast notifications (except 401 which redirects to login)

**Patterns:**
- FastAPI exception handler for `CapabilityDenied` → 403 with suggestion text
- Frontend `@tanstack/react-query` `onError` → `_redirectToLogin()` for auth errors
- Frontend `api.ts` `request()`: 401 silently handled; other errors show toast
- SSE connection errors auto-reconnect on frontend

## Cross-Cutting Concerns

**Logging:** `logging` stdlib with basicConfig in `backend/app/main.py:23-27`; desktop adds FileHandler to `data/desktop.log` in `backend/app/desktop.py:120-148`

**Validation:** Pydantic models for API request/response schemas; Pydantic `Settings` for config validation

**Authentication:** Custom password auth middleware in `backend/app/main.py:242-272`; PBKDF2 hashing; session token via `secrets.token_urlsafe`; IP-based protection for initial setup; whitelist for `/auth/*` and health endpoints

**CORS:** Wide-open (`allow_origins=["*"]`) for self-hosted LAN access — `allow_credentials=False` per browser spec constraint

---

*Architecture analysis: 2026-07-10*
