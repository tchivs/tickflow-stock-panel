# Codebase Concerns

**Analysis Date:** 2026-07-10

## Tech Debt

### Widespread bare `except Exception` swallowing

**Issue:** The codebase has 100+ instances of `except Exception:  # noqa: BLE001` that silently swallow all exceptions during startup, data processing, and service initialization. This makes debugging failures extremely difficult — errors are logged as warnings and execution continues, often with corrupted state.

**Files:** Nearly every file in `backend/app/`. Hotspots include:
- `backend/app/main.py` — 8 occurrences during lifespan startup (services can silently fail)
- `backend/app/services/quote_service.py` — 15 occurrences in the polling loop
- `backend/app/services/kline_sync.py` — 12 occurrences during data sync
- `backend/app/services/depth_service.py` — 8 occurrences
- `backend/app/backtest/engine.py` — 4 occurrences
- `backend/app/indicators/pipeline.py` — 4 occurrences
- `backend/app/services/wecom_bot_service.py` — 5 occurrences
- `backend/app/services/webhook_adapter.py` — 2 occurrences
- `backend/app/jobs/daily_pipeline.py` — 1 occurrence in stream retry

**Impact:** If a critical service like QuoteService, DepthService, or WecomBotService fails during initialization, the application starts in a degraded state but reports "ready". Users see missing data with no clear error indication. Similarly, during data pipeline processing, individual failures are swallowed, potentially corrupting downstream analysis.

**Fix approach:** 
1. Replace critical init failures with explicit error propagation (fail fast on essential services)
2. Use structured error types instead of bare `Exception`
3. Add health check endpoints that reflect actual service availability (not just "app started")
4. Remove `# noqa: BLE001` suppressions and use specific exception types

### Pervasive `any` types in TypeScript frontend

**Issue:** The frontend uses `any` types extensively (>90 explicit `as any` casts, plus hundreds of `Record<string, any>` and implicit `any` types), defeating TypeScript's type safety guarantees. The `api.ts` file alone uses `[key: string]: any` in 12 different type definitions.

**Files:**
- `frontend/src/lib/api.ts` — 2200+ lines, massive use of `Record<string, any>`, `any[]`, `any` return types
- `frontend/src/components/financials/StockFinancialDetail.tsx` — 60+ `as any` casts
- `frontend/src/components/EChartsIntraday.tsx` — 8+ `as any` casts
- `frontend/src/pages/Watchlist.tsx` — 10+ `as any` usages
- `frontend/src/pages/backtest/StrategyBacktest.tsx` — `e.target.value as any` pattern
- `frontend/src/pages/Analysis.tsx` — `e.target.value as any` pattern
- `frontend/src/pages/settings/ExtPages.tsx` — `e.target.value as any` pattern
- `frontend/src/components/screener/StrategyBuilderDialog.tsx` — `catch (e: any)`
- 15+ `catch (e: any)` blocks throughout frontend

**Impact:** Type errors that could be caught at compile time manifest as runtime errors. Refactoring is risky because there are no type contracts between API responses and UI components. Data shape mismatches from the backend cause silent UI failures.

**Fix approach:**
1. Generate TypeScript types from Pydantic models (e.g., using `openapi-typescript`)
2. Replace `Record<string, any>` with proper typed interfaces, starting with `api.ts`
3. Replace `catch (e: any)` with `catch (e: unknown)` and proper type narrowing
4. Add an ESLint rule banning `any` and `as any`

### Monolithic 2221-line API client (`api.ts`)

**Issue:** `frontend/src/lib/api.ts` at 2221 lines contains ALL API interactions as a single module — auth, kline, settings, backtest, screener, strategy, alerts, webhooks, preferences, and more. This creates a merge bottleneck, high cognitive load, and makes partial imports impossible.

**Impact:** Any change to API surface requires editing this single massive file. Type relationships between endpoint groups are invisible. Tree-shaking cannot eliminate unused endpoints.

**Fix approach:** Split into domain modules: `api/auth.ts`, `api/kline.ts`, `api/settings.ts`, `api/backtest.ts`, `api/strategy.ts`, etc.

### 4 extremely large backend modules (1400-1841 lines)

**Issue:** Several backend modules exceed 1400 lines, indicating high complexity and multiple responsibilities.

**Files:**
- `backend/app/tickflow/repository.py` — 1841 lines (data access, caching, schema migration, DuckDB views)
- `backend/app/indicators/pipeline.py` — 1658 lines (all technical indicators in one file)
- `backend/app/backtest/engine.py` — 1647 lines (data loading, matching, statistics in one file)
- `backend/app/api/settings.py` — 1390 lines (all settings endpoints monolithic)
- `backend/app/services/quote_service.py` — 1303 lines (polling, enriched cache, SSE broadcast)
- `backend/app/api/kline.py` — 1080 lines (all K-line endpoints)
- `backend/app/jobs/daily_pipeline.py` — 969 lines (pipeline orchestration)
- `backend/app/strategy/monitor.py` — 948 lines (monitoring + rule engine)
- `backend/app/services/kline_sync.py` — 787 lines

**Impact:** Difficult to understand, test, and modify. High risk of merge conflicts. Single-file bottlenecks for code review.

**Fix approach:** Split by responsibility. For example, `backtest/engine.py` should split into data loading, matching/cost model, and statistics. `indicators/pipeline.py` should split indicators into separate modules.

### Frontend ESLint configured but no ESLint config file

**Issue:** `frontend/package.json` has `"lint": "eslint ."` configured, but there is no `.eslintrc.*` or `eslint.config.*` file in the frontend directory. Running `pnpm lint` would fail.

**Impact:** No linting enforcement in CI or pre-commit. Code quality issues go undetected.

**Fix approach:** Add an ESLint configuration (flat config) with appropriate rules for React/TypeScript.

### No `ruff` config for `__init__.py` naming conventions

**Issue:** `backend/pyproject.toml` selects the `N` (naming) rule group for ruff, but several `__init__.py` modules such as `backend/app/indicators/__init__.py`, `backend/app/data_providers/__init__.py`, `backend/app/jobs/__init__.py`, and `backend/app/services/__init__.py` appear to exist with minimal or no content — which may trigger naming/custom-import checks.

**Impact:** Potential lint failures when running ruff in CI, or inconsistent application of naming conventions.

### No conftest.py or shared test infrastructure

**Issue:** Backend tests have 27 test files but no `conftest.py` for shared fixtures, no test configuration for mocking external APIs (TickFlow), and no CI test runner configuration. Tests require real data to function.

**Files:** `backend/tests/` (27 test files, no conftest.py)

**Impact:** Tests can't run in CI without real API keys. Tests are fragile — they depend on external data availability.

**Fix approach:** Create `conftest.py` with mock fixtures for TickFlow API, add CI test step with mocked tests.

## Known Bugs

### Timezone handling in market_time.py

**Issue:** While comments indicate market time uses explicit Beijing time (`app/market_time.py`), timestamps elsewhere throughout the codebase may not be consistently converted. The Dockerfile sets `TZ=Asia/Shanghai` as a "fallback" for "naive" times, indicating potential timezone-related inconsistencies in logs and data timestamps.

**Files:**
- `backend/app/market_time.py`
- `Dockerfile` (line 104)

**Trigger:** Running the application in a non-Asia/Shanghai timezone environment (e.g., a UTC-based CI/CD pipeline or server outside China).

**Workaround:** Docker deployment works because `TZ=Asia/Shanghai` is set, but non-Docker deployments may have incorrect market time calculations.

### TickFlow API bridge may leak subprocess resources

**Issue:** `backend/app/plugins/stocksdk/bridge.py` uses `subprocess.run()` (blocking) to call a Node.js bridge script. Each call spawns a new Node.js process. While `subprocess.run` does clean up after completion, the 120-second default timeout and lack of connection pooling mean:
- Under high load, many Node.js processes may be in-flight simultaneously
- Timeouts leave the subprocess running until complete (no force-kill)

**Files:**
- `backend/app/plugins/stocksdk/bridge.py` (lines 54-70)
- `backend/app/plugins/stocksdk/provider.py`

**Trigger:** High-frequency data requests, particularly `quote` operations during market hours.

### secrets.json chmod silently fails on some platforms

**Issue:** `secrets_store.py` calls `os.chmod(p, 0o600)` but wraps it in `try/except OSError: pass`, meaning on filesystems that don't support Unix permissions (FAT32, exFAT, some network mounts), the secrets file may have world-readable permissions without warning.

**Files:**
- `backend/app/secrets_store.py` (line 42-44)
- `backend/app/services/auth.py` (line 64-67)

**Impact:** API keys stored in `secrets.json` could be leaked if the data directory is accessible to other processes/users on the same machine.

## Security Considerations

### CORS allow_origins=["*"] with allow_credentials=False

**Issue:** `backend/app/main.py` sets `allow_origins=["*"]` with `allow_credentials=False`. While the code acknowledges the browser restriction, this means cookie-based auth (session tokens) cannot be used with credentialed requests. The design relies on "header (API Key)" auth instead — but the auth middleware actually checks cookies (`request.cookies.get(auth_api.COOKIE_NAME)`), not headers.

**Files:**
- `backend/app/main.py` (lines 221-227)
- `backend/app/main.py` (line 268 — cookie-based auth)

**Impact:** The auth middleware validates sessions via cookies, but CORS is configured for `allow_credentials=False` with `allow_origins=["*"]`. In cross-origin scenarios (like a browser extension or third-party integration), cookies cannot be sent, making authentication impossible despite `allow_origins=["*"]` being set.

### Secrets in environment variable AUTH_PASSWORD

**Issue:** `backend/app/services/auth.py` reads `auth_password` from the environment variable `AUTH_PASSWORD`. While it's documented as "read-once, only for initialization", the plaintext password exists in the environment for the entire process lifetime after startup.

**Files:**
- `backend/app/config.py` (line 100)
- `backend/app/services/auth.py` (lines 124-149)

**Risk:** If an attacker gains access to the running process's environment (via `/proc/pid/environ`, debug hooks, or container escape), they can recover the plaintext initial password. The `.env` file comment recommends "权限保持 600" (mode 0600), but this is only advisory.

### No CSRF protection

**Issue:** The application uses cookie-based session auth but has no CSRF protection. Any authenticated endpoint can be called from any origin because CORS allows `*`, and cookies are sent automatically by browsers.

**Files:**
- `backend/app/main.py` (CORS config + auth middleware)

**Risk:** If a user is logged in, cross-site request forgery attacks could execute API calls on their behalf.

### Missing content security policy

**Issue:** `backend/app/main.py` line 332 serves `index.html` with `Cache-Control: no-store` but no `Content-Security-Policy` header. Static assets have no security headers at all.

**Risk:** XSS vulnerabilities in the SPA are not mitigated by CSP. Inline scripts and connections to arbitrary origins are unrestricted by policy.

## Performance Bottlenecks

### Polars enriched cache warmup blocks startup

**Issue:** `backend/app/main.py` line 56 calls `repo.refresh_cache(background=True)` which triggers recomputation of 1M+ rows of enriched indicators. While nominally "background", this still consumes significant CPU and I/O during application startup.

**Files:**
- `backend/app/main.py` (line 56)
- `backend/app/tickflow/repository.py`

**Impact:** On resource-constrained machines (e.g., low-end VPS), the enriched cache warmup can cause startup time to exceed 60 seconds, potentially triggering the desktop app's health-check timeout (`backend/app/desktop.py` line 249, 60s timeout).

### QuoteService polling uses synchronous ThreadPoolExecutor for webhooks

**Issue:** `backend/app/services/quote_service.py` uses `_WEBHOOK_EXECUTOR = ThreadPoolExecutor(max_workers=2)` for fire-and-forget webhook delivery. However, the webhook adapter (`backend/app/services/webhook_adapter.py`) has internal retry logic with exponential backoff that can take up to ~15 seconds per failing webhook. With only 2 workers, back-to-back webhook failures can queue up and cause delivery delays.

**Files:**
- `backend/app/services/quote_service.py` (line 44)
- `backend/app/services/webhook_adapter.py` (lines 109-140)

**Impact:** If multiple webhook targets become slow, the 2-worker pool becomes saturated and subsequent webhook deliveries are delayed or dropped.

### DuckDB in-memory (no persistence)

**Issue:** `backend/app/tickflow/repository.py` connects DuckDB in `:memory:` mode (line 80). All views and queries are lost on process restart, forcing expensive rebuilds from parquet files.

**Files:**
- `backend/app/tickflow/repository.py` (line 80)

**Impact:** Every application restart triggers a DuckDB view rebuild, which involves scanning parquet files and re-registering all views. For large datasets, this adds unnecessary latency to application startup.

### Two separate monitoring systems run in parallel

**Issue:** `backend/app/strategy/monitor.py` contains both `StrategyMonitorService` (legacy, type=strategy) and `MonitorRuleEngine` (newer, 4 rule types including strategy). Comments indicate the old system is being migrated to the new one, but both run simultaneously during market hours, duplicating work.

**Files:**
- `backend/app/strategy/monitor.py` (lines 8-10 comment)

**Impact:** During market hours, every quote update triggers processing in both systems, consuming approximately double the CPU time for strategy monitoring.

## Fragile Areas

### Lifespan startup chain — cascading failures silently ignored

**Issue:** `backend/app/main.py` lines 30-188 define a `lifespan` context manager with 10+ sequential initialization steps, each wrapped in `try/except Exception:  # noqa: BLE001`. Any step can silently fail, leaving `app.state` partially initialized with `None` attributes.

**Files:**
- `backend/app/main.py` (lines 30-188)

**Why fragile:** The startup sequence is tightly coupled and has no dependency graph. Step 7 (depth_service.boot_check) depends on Step 6 (pipeline scheduler) indirectly, but there's no explicit dependency enforcement. Adding a new service requires careful ordering and manual `try/except` boilerplate.

**Safe modification:**
1. Group services into layers with explicit dependency declarations
2. Make essential services (repo, quote_service, strategy_engine) fail hard
3. Make optional services (wecom_bot_service, financial_scheduler) fail soft
4. Add a health endpoint that reports which services are actually running

**Test coverage:** 0 — there are no integration tests for the startup lifespan.

### WecomBotService WebSocket reconnection logic

**Issue:** `backend/app/services/wecom_bot_service.py` implements a long-lived WebSocket connection with exponential backoff reconnection. The reconnection runs in a daemon thread with an asyncio event loop. There's no health check endpoint, status reporting, or metrics for connection state.

**Files:**
- `backend/app/services/wecom_bot_service.py` (278 lines)

**Why fragile:** 
- No reconnection attempt limit (continues retrying indefinitely)
- WebSocket credentials are read once at startup — if user changes bot_id/secret in settings, requires full service restart
- No monitoring to detect disconnected state
- The asyncio event loop runs in a daemon thread that is not properly shut down if the service is stopped

### stock-sdk subprocess bridge coupling

**Issue:** `backend/app/plugins/stocksdk/bridge.py` uses `subprocess.run` to call Node.js, creating a hard runtime dependency on Node.js being installed and available. The bridge parses stdout for JSON, making it sensitive to any Node.js stdout output (logging, warnings).

**Files:**
- `backend/app/plugins/stocksdk/bridge.py`
- `backend/app/plugins/stocksdk/provider.py`

**Why fragile:**
- If Node.js is not installed, the entire stock-sdk provider raises `StockSDKBridgeError`
- If Node.js outputs anything to stdout before the JSON result (e.g., a deprecation warning), JSON parsing fails
- No health check endpoint exposes bridge availability proactively
- The provider silently degrades to TickFlow provider on failure, which may have different data semantics

### Instruments and cache schema compatibility

**Issue:** `backend/app/parquet.py` defines storage schemas for daily and enriched parquet, and `scan_parquet_compat` handles additive schema changes with `extra_columns="ignore"` and `missing_columns="insert"`. However, this means schema evolution can silently drop or add columns without explicit migration.

**Files:**
- `backend/app/parquet.py` (lines 39-43)
- `backend/app/tickflow/repository.py` (cache layer)

**Why fragile:** 
- Stocks/ETFs have separate enriched paths (`kline_daily_enriched` vs `kline_etf_enriched`) sourced from different parquet files — schema drift between them causes silent failures
- No schema versioning in parquet files
- The `_migrate_legacy_data_dir()` function in DataStore provides no rollback if migration fails mid-way

### SSLError/network failure handling in ext_data.py

**Issue:** `backend/app/api/ext_data.py` creates temporary directories (`tempfile.mkdtemp()`) on lines 433 and 666 for downloading external data files. These temporary directories are not cleaned up if the download or processing fails, leading to temp directory leaks.

**Impact:** Accumulated temp directories waste disk space. On systems with limited `/tmp` space, this can cause failures.

### Auth rate limiting is in-memory only

**Issue:** `backend/app/api/auth.py` implements login rate limiting as an in-memory `defaultdict` with threading lock. If the application restarts, the rate limit counter resets. In a multi-worker deployment (e.g., gunicorn with multiple workers), each worker has its own counter, effectively allowing 5× failures per IP.

**Files:**
- `backend/app/api/auth.py` (lines 35-39)

**Impact:** Brute-force protection only works in single-process deployments and is reset on restart.

## Scaling Limits

### Single-user auth model

**Issue:** The auth system (`backend/app/services/auth.py`) uses a single-password, single-user model with in-memory session storage. There's no concept of users, roles, or permissions.

**Impact:** Cannot support multi-user deployments (e.g., team access to a shared panel). No audit trail for which user performed which action.

### No database for persistent state

**Issue:** All persistent state is stored in parquet files, JSON files, and DuckDB in-memory views. There is no relational database. This means:
- No transaction support for financial data operations
- No referential integrity
- Complex queries require loading data into Polars dataframes
- No concurrent write safety beyond process-level file locking

**Impact:** At scale, concurrent pipeline runs and data writes could cause corruption. The JSON-based stores (`secrets.json`, `auth.json`, `strategy_cache.json`, `preferences.json`) use read-modify-write patterns that race under concurrent access.

### No data partitioning/retention policy

**Issue:** Parquet data accumulates indefinitely. There's no data retention policy, archival strategy, or partition management for old data.

**Impact:** Disk usage grows unboundedly. Over time, scan operations slow down as more parquet files accumulate in date-partitioned directories.

## Dependencies at Risk

### No pinned transitive deps for frontend

**Issue:** `frontend/package.json` uses `^` ranges (e.g., `"react": "^18.3.1"`) for all dependencies. The lockfile (`pnpm-lock.yaml`) provides some reproducibility, but `pnpm install --frozen-lockfile` in Docker fails and falls back to `pnpm install` (Dockerfile line 23), which ignores the lockfile.

**Impact:** Docker builds can produce different dependency trees depending on when `pnpm install` is run. A transitive dependency breaking change can silently break the build.

### `vectorbt` as optional-extras with platform-specific builds

**Issue:** `backend/pyproject.toml` lists `vectorbt` as an optional dependency in the `backtest` extras group, with a comment noting it requires `numba` → `llvmlite` and may need `brew install cmake` on macOS/Intel.

**Impact:** The backtesting feature is gated behind a complex build requirement. Users on macOS Intel without cmake get mysterious build failures when trying to use backtesting.

### `pandas` kept as "border-only" dependency

**Issue:** `backend/pyproject.toml` line 20 includes `pandas>=2.2` with a comment "仅在 BacktestService 边界使用,见 §7.4 / ADR-19". This means the codebase has two dataframe libraries (Polars and Pandas) in play, adding cognitive overhead and potential conversion bugs.

**Impact:** The dual-dependency increases maintenance burden and potential for subtle bugs when converting between Polars and Pandas dataframes.

## Missing Critical Features

### No health check aggregating all services

**Issue:** The `/health` endpoint only returns `{"status": "ok", "version": "...", "mode": "..."}`. It does not report the health of QuoteService, DepthService, WecomBotService, enriched cache readiness, or stock-sdk bridge availability. A startup where all services silently fail still reports "status: ok".

**Files:**
- `backend/app/api/routes.py` (lines 13-20)

**Blocks:** Operational monitoring, debugging startup failures, deployment health checks.

### No structured logging

**Issue:** Logging is done exclusively via `logging.basicConfig` with text format (`backend/app/main.py` lines 23-26). There is no structured logging (JSON, logfmt), no correlation IDs, and no integration with log aggregation systems.

**Files:**
- `backend/app/main.py` (lines 23-26)
- All backend modules use `logging.getLogger(__name__)`

**Blocks:** Searching logs across modules for a single request trace, integrating with log aggregation services, automated log analysis.

## Test Coverage Gaps

### Zero frontend tests

**Issue:** The frontend has zero test files — no unit tests, no component tests, no E2E tests. There is no test runner configured in `frontend/package.json` (no vitest, jest, or playwright).

**Files:** Entire `frontend/src/` directory

**Risk:** All frontend behavior (rendering, state management, API interaction, SSE streaming, routing) is completely untested. Refactoring any component (pages are 500-1157 lines each) risks breakage with no safety net. The SSE quote stream (`frontend/src/lib/useQuoteStream.ts`), with its complex reconnection logic and race conditions, is particularly concerning.

**Priority:** High

### No end-to-end tests

**Issue:** There are no E2E tests covering the full backend-to-frontend flow: authentication, data loading, watchlist management, strategy execution, backtesting pipeline.

**Risk:** Backend API changes may silently break frontend functionality. Schema changes in parquet files or API responses go undetected until users notice.

**Priority:** Medium

### Backend tests lack mocking infrastructure

**Issue:** All 27 backend test files appear to require real TickFlow API access or real parquet data files. There's no `conftest.py` with mock fixtures, no FakeTickFlowClient, no test data factories.

**Files:** `backend/tests/` (27 test files)

**Risk:** Tests cannot run in CI without real API keys and real data, making them useless for automated quality gates. Tests may also fail when external API behavior changes.

**Priority:** High

### No tests for startup lifecycle

**Issue:** The entire `lifespan` function in `backend/app/main.py` (158 lines, 10+ initialization steps) has zero test coverage. Critical initialization logic for QuoteService, DepthService, strategy engine, monitor engine, and scheduler are untested.

**Risk:** Adding a new service or modifying the startup order risks breaking the entire application initialization, only detectable at runtime.

**Priority:** High

### No tests for auth flow

**Issue:** The auth system (`backend/app/services/auth.py` — password hashing, session management, rate limiting, `bootstrap_from_env`) has no test coverage. Password verification, session persistence/restoration, and rate limiting behavior are all untested.

**Risk:** Security-critical code paths are unverified. Edge cases in password hashing, session timeout, or concurrent session management can go undetected.

**Priority:** High

---

*Concerns audit: 2026-07-10*
