# Phase 1: Core Merger - Research

**Researched:** 2026-07-10
**Domain:** Single-host market-data, portfolio, monitoring, decision-playbook, and real-time integration
**Confidence:** MEDIUM

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

### Portfolio And Account Model
- **D-01:** Support manual multi-account portfolio management. Each account has its own holdings and available funds; the portfolio view also provides an aggregate summary.
- **D-02:** A holding retains account, instrument, cost price, quantity, invested amount, and short-term/swing/long-term trading style.
- **D-03:** Market value and profit/loss use the latest shared tickflow quote. The interface shows update freshness and uses the most recent close outside trading hours.
- **D-04:** Accounts and holdings are disabled/archived rather than deleted when they contain useful history or alert associations. Deletion is reserved for empty records.

### Alerts And Notifications
- **D-05:** Holding-aware rules are a type and scope within the existing Monitor center, not a second alert product. Reuse `MonitorRuleEngine`, its cooldown behavior, stored alert history, and the shared SSE pipeline.
- **D-06:** Phase 1 supports configurable Feishu and Telegram delivery. Other PanWatch channels remain future extensions behind the same adapter boundary.
- **D-07:** Rules have cooldown and active-time controls. High-severity rules may explicitly bypass quiet periods; every hit is retained in alert history.
- **D-08:** External notification delivery never blocks rule evaluation, persistence, or SSE. Store per-delivery outcome and error information for review.

### Main Workspace And Mobile Scope
- **D-09:** Add Portfolio as a first-class workspace page. It shows account totals and profit/loss before the holdings list; rule management remains in the Monitor center.
- **D-10:** Use a data-dense desktop holdings table and compact mobile holding cards. Both views expose price, profit/loss, alert state, and the necessary actions without horizontal overflow.
- **D-11:** Phase 1 makes Portfolio, monitoring rules, and alert history fully responsive in a mobile browser. PWA installation, offline support, and a separate mobile application shell are not in scope.
- **D-12:** Add and edit account, holding, and rule records in page-level form dialogs, then refresh the affected data without a separate edit route.

### Docker Compose Verification
- **D-13:** Compose acceptance uses deterministic offline fixtures in an isolated data directory. It must not require a market-data API key, external network, or a real notification credential.
- **D-14:** Verify Feishu and Telegram adapters with a local HTTP test receiver that captures outbound requests and delivery outcomes instead of sending real messages.
- **D-15:** The automated flow covers Compose health, SQLite-backed portfolio and rule APIs, emitted SSE alert events, and key desktop/mobile browser workflows.
- **D-16:** Run the flow through a dedicated test Compose configuration with an isolated project name, port, temporary data directory, and cleanup after execution; it must not modify a developer's normal `data/` volume.

### Data Governance And Upstream Synchronization
- **D-17:** Preserve the data-lake contract as part of the Phase 1 workflow: synchronization checks and automated verification cover primary-key, time-semantics, repair-window, and schema-drift expectations for adopted market data.
- **D-18:** Document the synchronization path for each adopted upstream capability. The integration must preserve tickflow as the host, Parquet/DuckDB/Polars for time series, and SQLite for operational state; it must not introduce a second deployed application or persistence boundary.

### the agent's Discretion
- Exact SQLite migration mechanism, schema naming, repository/service boundaries, and test-fixture shape.
- The precise desktop column order, mobile-card layout, empty states, alert copy, and noncritical visual details, subject to the UI design contract.
- The implementation-level mapping from the existing Feishu adapter and PanWatch Telegram adapter into a shared delivery interface.

### Deferred Ideas (OUT OF SCOPE)
- Broker connections, transaction imports, realized-gain accounting, and tax-lot calculation are outside Phase 1.
- PWA installation, offline behavior, and a standalone mobile shell are outside Phase 1.
- Notification channels beyond Feishu and Telegram are future adapter extensions.
- Strict screenshot-based visual regression is not required for Phase 1; browser workflow checks are required.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CORE-01 | User can synchronize A-share instruments, daily prices, adjustment factors, financial data, and enriched indicators into the governed Parquet data lake. | Extend the existing pipeline through an injected offline fixture source; retain the existing Parquet partition, DuckDB-view, and Polars enrichment path. [VERIFIED: project codebase] |
| CORE-02 | Operator can verify the time-series data contract, including primary keys, time semantics, repair windows, and schema-drift checks for synchronized data. | Add a contract manifest and a deterministic validator over fixture and synchronized Parquet partitions. [VERIFIED: project codebase] |
| CORE-03 | User can manage accounts and positions and view current position-level profit and loss. | Build a SQLite operational repository plus a Portfolio API/page that joins current quotes without copying market series into SQLite. [VERIFIED: project codebase] |
| CORE-04 | User can define position, price, and market monitoring rules; receive a notification when a rule matches; and review persisted alert history. | Extend the existing MonitorRuleEngine/SSE event contract with position scope and persist hits plus individual delivery attempts in SQLite. [VERIFIED: project codebase] |
| CORE-05 | User can view current market and position updates through the shared real-time SSE pipeline. | Add `portfolio_updated` to the existing `/api/intraday/stream` subscriber fan-out and invalidate Portfolio queries from the root SSE hook. [VERIFIED: project codebase] |
| CORE-06 | Operator can start the Phase 1 workflow with one Docker Compose command and run an automated check covering data sync, position maintenance, a price-rule trigger, notification delivery, and SSE display without an external database or queue. | Add a test-only Compose override with a unique project/port/data directory, fixture mode, local receiver, and browser verifier. [VERIFIED: project decisions] |
| CORE-07 | Operator can update each adopted upstream integration through a documented synchronization path without replacing the shared data-lake or operational-state boundaries. | Record an adoption map that identifies copied/adapted code, upstream source paths, local owner, and regression tests. [VERIFIED: project decisions] |
| PLAN-01 | User can generate deterministic market state, quality-screened pools, and a playbook with entry range, stop, target, and position sizing. | Adapt Hermes' pure deterministic calculations to a host-native decision package over Tickflow data, with SQLite snapshots. [VERIFIED: upstream source] |
| PLAN-02 | User can compare a deterministic playbook baseline with field-bounded, audited AI adjustments and replay historical decisions with AI influence disabled. | Store baseline/final fields and adjustment audit rows; use a replay guard that fails if an AI client is reached. [VERIFIED: upstream source] |
</phase_requirements>

## Summary

Phase 1 is an integration phase, not a multi-application merger. The current Tickflow host already starts FastAPI and the built React application in one container, writes market data to Parquet, serves DuckDB views and Polars-derived frames, and exposes a shared multi-subscriber SSE stream. The implementation must place new accounts, positions, rule state, notification-delivery history, and decision snapshots in one SQLite operational database under the existing mounted data directory. [VERIFIED: project codebase]

The existing `MonitorRuleEngine -> QuoteService -> /api/intraday/stream` path is the correct alert and real-time seam. It already persists rule events before emitting named `strategy_alert` SSE events, applies per-rule/symbol cooldowns, and sends Feishu work asynchronously after the user-visible path. Extend this spine for position context and delivery outcomes; do not run PanWatch's separate quote polling, price-alert scheduler, API, or database. [VERIFIED: project codebase]

HermesAlpha is not transplantable as a runtime because its current stage orchestration depends on PostgreSQL, SQLAlchemy, and its own models. Its portable value is the deterministic playbook calculation, the bounded AI-review policy, and the replay invariants. Reimplement that thin core in a Tickflow-owned module using governed historical data and SQLite snapshots, with an explicit upstream adoption document. [VERIFIED: upstream source]

**Primary recommendation:** Build a host-native `operational.db` and decision package first, then make the existing rule engine and root SSE stream consume their state; prove the complete loop using fixture-only Compose acceptance.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Market synchronization and contract validation | API / Backend | Database / Storage | The backend owns provider selection, repair and validation while Parquet/DuckDB own series persistence and queries. [VERIFIED: project codebase] |
| Accounts, holdings, rules, alert history, delivery history | Database / Storage | API / Backend | SQLite owns durable operational records; APIs validate and expose transactions. [VERIFIED: project decisions] |
| P&L and freshness calculation | API / Backend | Database / Storage | The service joins operational holdings to the latest shared quote or close without duplicating market data. [VERIFIED: project decisions] |
| Rule evaluation and cooldown | API / Backend | Database / Storage | MonitorRuleEngine evaluates Polars frames; SQLite provides rule state and auditable history. [VERIFIED: project codebase] |
| Feishu and Telegram delivery | API / Backend | External dependency | Delivery adapters run after persistence/SSE and report a per-channel outcome. [VERIFIED: project decisions] |
| Live Portfolio refresh | Browser / Client | API / Backend | The browser invalidates Portfolio queries from events emitted by the shared server stream. [VERIFIED: project codebase] |
| Playbook baseline, bounded adjustment, replay | API / Backend | Database / Storage | Deterministic logic reads governed history; SQLite retains baseline/final/audit/replay records. [VERIFIED: upstream source] |
| Offline acceptance | API / Backend | Browser / Client | A test Compose topology supplies local fixtures and receiver while browser tests prove desktop/mobile workflows. [VERIFIED: project decisions] |

## Project Constraints (from AGENTS.md)

- No `./AGENTS.md` or `./.opencode/AGENTS.md` exists in the project, so there are no project-local directives beyond the supplied phase context. [VERIFIED: project filesystem]
- Use the indexed code graph for structural discovery and use literal search only for strings/configuration when implementation begins. [VERIFIED: workspace instruction]
- Keep Tickflow as the sole host; `/root/source/tmp/PanWatch` is upstream reference only, not a deployed nested application. [VERIFIED: project decisions]
- Preserve one production Compose app, Parquet/DuckDB/Polars for time series, SQLite for operational state, and no external database or queue. [VERIFIED: project decisions]

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python `sqlite3` | Python 3.11 standard library | SQLite operational repository and versioned SQL migrations. | No new runtime package is needed for the required single-container SQLite boundary. [VERIFIED: project runtime] |
| FastAPI | Existing `>=0.115` | Register operational APIs and initialize repositories in the existing lifespan. | The host already uses FastAPI lifespan and routes; FastAPI documents lifespan plus `TestClient` context use for lifecycle tests. [CITED: https://github.com/fastapi/fastapi/blob/master/docs/en/docs/advanced/testing-events.md] |
| Polars, DuckDB, PyArrow | Existing `>=1.0`, `>=1.0`, `>=16.0` | Governed Parquet data lake, historical decision reads, and valuation quote access. | These are the host's declared data stack and must remain the only time-series boundary. [VERIFIED: project codebase] |
| `sse-starlette` | Existing `>=2.0` | Shared named-event SSE endpoint. | The host already uses `EventSourceResponse`; its official documentation supports async generators, named events, pings, and send timeouts. [CITED: https://github.com/sysid/sse-starlette/blob/main/_autodocs/INDEX.md] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `httpx` | Existing `>=0.27` | Feishu and Telegram HTTP delivery with short timeouts. | Reuse for adapters and the local receiver verification path; do not add an alternate HTTP client. [VERIFIED: project codebase] |
| `pytest`, `pytest-asyncio` | Existing dev `>=8.0`, `>=0.23` | Unit, integration, and offline fixture tests. | Follow the current backend testing convention. [VERIFIED: project codebase] |
| `@playwright/test` [WARNING: flagged as suspicious - verify before using.] | `1.61.1` | Desktop and mobile browser workflow acceptance. | Official Playwright documentation supports `webServer`, `baseURL`, and device projects, but the package gate marks its current release SUS because it is recently published. [CITED: https://github.com/microsoft/playwright/blob/main/docs/src/test-webserver-js.md] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Host-native SQLite repository | PanWatch SQLAlchemy application/database | Rejected: creates a second model/runtime boundary and conflicts with the single-host integration decision. [VERIFIED: project decisions] |
| Shared QuoteService/SSE | PanWatch price-alert polling/SSE path | Rejected: duplicates quote acquisition, cooldown ownership, alert delivery, and client event streams. [VERIFIED: project codebase] |
| Native deterministic decision adapter | Full HermesAlpha service | Rejected: Hermes' stage runtime is tied to PostgreSQL/SQLAlchemy models, which violates the Phase 1 storage boundary. [VERIFIED: upstream source] |
| Playwright browser acceptance | Screenshot-only visual regression | Rejected: Phase decisions require browser workflows but explicitly do not require screenshot regression. [VERIFIED: project decisions] |

**Installation:**

```bash
# Human checkpoint required before this install because the legitimacy seam returned SUS.
pnpm --dir frontend add -D @playwright/test@1.61.1
pnpm --dir frontend exec playwright install --with-deps chromium
```

**Version verification:** `@playwright/test` currently resolves to `1.61.1`, was created on 2020-09-24, and has repository metadata for `microsoft/playwright`; `sse-starlette` currently has PyPI release `3.4.5`, while the host's compatible lower bound is `>=2.0`. [VERIFIED: npm registry]

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `@playwright/test` | npm | Created 2020-09-24; current 1.61.1 published 2026-06-23 | 43.9M/week | `github.com/microsoft/playwright` | SUS | Flagged - planner must add `checkpoint:human-verify` before installing. [VERIFIED: npm registry] |

**Packages removed due to [SLOP] verdict:** none. [VERIFIED: package-legitimacy seam]

**Packages flagged as suspicious [SUS]:** `@playwright/test`; the seam's sole reason is that the current release is too new. [VERIFIED: package-legitimacy seam]

## Architecture Patterns

### System Architecture Diagram

```text
Offline fixture files / live provider
              |
              v
Pipeline -> Parquet partitions -> DuckDB views / Polars enriched frame
              |                             |
              |                             +--> Decision service -> SQLite playbook/audit/replay
              v
QuoteService -> MonitorRuleEngine <- SQLite accounts/positions/rules
              |       |                         |
              |       +--> SQLite alert event + delivery rows
              v
Shared SSE /api/intraday/stream -> React root hook -> Monitor + Portfolio query invalidation
              |
              +--> async delivery executor -> Feishu/Telegram or local test receiver
```

The production Compose topology remains one app container. The acceptance override may add ephemeral receiver/verifier services only; neither is a production database, queue, or second product. [VERIFIED: project decisions]

### Recommended Project Structure

```text
backend/app/
├── operational/              # SQLite connection, migrations, repositories, typed records
├── portfolio/                # valuation and position-aware quote projection service
├── notifications/            # Feishu/Telegram delivery interface and delivery worker
├── decision/                 # deterministic baseline, adjustment guard, replay service
├── contracts/                # Parquet contract definitions and validator
├── api/portfolio.py          # account/position/summary endpoints
└── api/decision.py           # playbook, adjustment, and replay endpoints
frontend/src/
├── pages/Portfolio.tsx
├── components/portfolio/
└── lib/useQuoteStream.ts     # shared event invalidation only
tests/
├── test_operational_*.py
├── test_portfolio_*.py
├── test_notification_*.py
├── test_contracts_*.py
└── test_decision_*.py
compose/
└── phase1.test.yml           # isolated fixture/receiver/verifier topology
```

### Pattern 1: One Operational SQLite Boundary

**What:** Create `data/operational.db` with versioned SQL migrations tracked by `PRAGMA user_version`; open a short-lived connection per request/worker, enable foreign keys on each connection, and keep transactions small. [ASSUMED]

**When to use:** Use it for accounts, positions, rule definitions, alert events, delivery attempts, decision runs, baseline/final playbooks, adjustment audit rows, and replay snapshots. Never store Parquet market bars, quote series, or copied enriched data there. [VERIFIED: project decisions]

**Required schema shape:**

| Table group | Required fields and constraints |
|-------------|---------------------------------|
| `accounts`, `positions` | `enabled`/`archived_at`; `UNIQUE(account_id, instrument_symbol)`; reject deletion when a history/rule reference exists. [VERIFIED: project decisions] |
| `monitor_rules` | Existing rule fields plus `type='position'`, position scope/targets, active-time and quiet-bypass settings; retain stable IDs for event linkage. [ASSUMED] |
| `alert_events`, `notification_deliveries` | Immutable event payload/snapshot, rule and position references, `pending/sent/failed/skipped` delivery status, sanitized error, timestamps, and channel. [VERIFIED: project decisions] |
| `decision_runs`, `playbooks`, `adjustment_audit`, `replay_runs` | Input/config version, deterministic baseline, final values, allowed-field adjustment disposition, and replay result hash/snapshot. [VERIFIED: upstream source] |

### Pattern 2: Quote Projection Rather Than Market Duplication

**What:** Resolve position valuation from `QuoteService.get_enriched_today()` when its snapshot is fresh; otherwise query the latest shared daily close through the existing repository and label the value with `source` and `as_of`. [VERIFIED: project codebase]

**When to use:** Use this projection in the Portfolio summary/list endpoint and position rule evaluation. It provides per-account and aggregate P&L without storing market-price copies in SQLite. [VERIFIED: project decisions]

**Formula:** `market_value = latest_price * quantity`, `cost = cost_price * quantity`, `unrealized_pnl = market_value - cost`, and `pnl_pct = unrealized_pnl / cost` only when cost is nonzero. [ASSUMED]

### Pattern 3: Extend the Existing Alert Event Contract

**What:** Maintain one ordered flow: evaluate rule -> persist `alert_event` -> enqueue SSE -> enqueue delivery work -> update delivery outcome. Persistence and SSE must finish before delivery starts. [VERIFIED: project decisions]

**When to use:** Use the existing `strategy_alert` payload shape with additive `position_id`, `account_id`, `delivery_summary`, and condition snapshot fields. Add a separate `portfolio_updated` named event for account/position mutations; use `quotes_updated` for price-driven revaluation. [ASSUMED]

**Implementation detail:** Model holding-aware rules as `type='position'` with an explicit selected position set. Build a temporary holding projection with one row per position from the shared quote frame, evaluate only these rules against it, and include the matched position/account in the event. This prevents a generic all-market price rule from emitting duplicate alerts when several accounts own one symbol. [ASSUMED]

### Pattern 4: Nonblocking Notification Delivery With Durable Outcomes

**What:** Introduce a narrow `NotificationChannel` interface: `deliver(event, channel_config) -> DeliveryResult`. Submit it to a bounded executor only after the event record exists. [ASSUMED]

**When to use:** Implement Feishu by adapting the existing webhook payload/signature path and Telegram by constructing requests only to the fixed Bot API origin. Use a local receiver endpoint only under the test Compose profile. [VERIFIED: project codebase]

**Quiet-period rule:** Always retain the alert event. Apply active-time/quiet settings only to delivery, recording `skipped` plus the reason; a critical rule with `bypass_quiet_period=true` may deliver. Cooldown stays in MonitorRuleEngine and suppresses duplicate rule events before they become alert hits. [ASSUMED]

### Pattern 5: Deterministic Baseline First, Bounded AI Second

**What:** Port the pure playbook calculation into `backend/app/decision/` and make it return a typed baseline object containing entry range, stop, targets, position percentage, action, reason snapshot, data-as-of, and engine/config version. [VERIFIED: upstream source]

**When to use:** Persist the baseline before any optional AI call. Permit adjustment only to `entry_low`, `entry_high`, `stop`, `target1`, `target2`, and `position_pct`; retain `action`, score, and risk/reward as deterministic facts. Store proposed, clamped, rejected, and applied values per field. [VERIFIED: upstream source]

**Replay rule:** Replay consumes historical Parquet data only through the requested `as_of` boundary, runs the deterministic baseline pipeline, and activates a context-local replay guard that raises if the AI gateway is invoked. Re-running the same fixtures/configuration must produce the same ordered snapshot. [VERIFIED: upstream source]

### Pattern 6: Offline Acceptance Is a First-Class Adapter Mode

**What:** Add a fixture provider selected by a test-only environment variable. It loads a tiny instrument/daily/adjustment/financial fixture set into the normal repository and runs the normal view/enrichment/contract path. [ASSUMED]

**When to use:** The acceptance command uses this mode, a unique Compose project name, a temporary data bind mount, a local receiver, and a verifier; it must not call Tickflow, Telegram, Feishu, or any external network endpoint. [VERIFIED: project decisions]

### Code Example: Lifespan-Managed Operational State

```python
# Source pattern: https://github.com/fastapi/fastapi/blob/master/docs/en/docs/advanced/testing-events.md
@asynccontextmanager
async def lifespan(app: FastAPI):
    store = DataStore()
    app.state.repo = KlineRepository(store)
    app.state.operational = OperationalRepository(store.data_dir / "operational.db")
    app.state.operational.migrate()
    yield
    app.state.operational.close()
```

The actual test must use `with TestClient(app) as client:` so startup creates and migrates the isolated database and shutdown closes it. [CITED: https://github.com/fastapi/fastapi/blob/master/docs/en/docs/advanced/testing-events.md]

### Code Example: Additive Named SSE Event

```python
# Source pattern: https://github.com/sysid/sse-starlette/blob/main/_autodocs/02-serversentevent.md
yield {
    "event": "portfolio_updated",
    "data": json.dumps({"ts": now_ms, "account_ids": changed_accounts}),
}
```

The event must be emitted from the existing subscriber stream, not a new EventSource endpoint. [VERIFIED: project codebase]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Time-series store/query layer | SQLite copies of daily bars, quotes, factors, or enriched rows | Existing Parquet/DuckDB/Polars repository | Duplicated price history creates divergent freshness and repair behavior. [VERIFIED: project decisions] |
| Alert engine or SSE server | A PanWatch scheduler, polling loop, or second streaming endpoint | Existing MonitorRuleEngine, QuoteService, and `/api/intraday/stream` | Existing code already handles cooldown, independent subscribers, and UI fan-out. [VERIFIED: project codebase] |
| Notification protocol clients | Generic multi-channel framework or arbitrary callback URLs | Narrow Feishu/Telegram adapters over existing `httpx` | The phase supports only two channels and needs auditable outcomes, timeouts, and safe endpoint control. [VERIFIED: project decisions] |
| AI authority | An AI-produced playbook without a baseline | Hermes-derived bounds guard and a deterministic baseline | The product constraint requires bounded, audited adjustment and AI-free replay. [VERIFIED: project decisions] |
| Browser automation | Custom DOM/event test harness | Playwright Test after human legitimacy approval | Official tooling supports a local server, device profiles, and web-first assertions. [CITED: https://github.com/microsoft/playwright/blob/main/docs/src/browsers.md] |

**Key insight:** SQLite is the operational source of truth, while the existing lake is the market-data source of truth; every service boundary should make that direction explicit. [VERIFIED: project decisions]

## Common Pitfalls

### Pitfall 1: Porting PanWatch as an application
**What goes wrong:** A copied PanWatch API/SQLAlchemy model layer brings its own database, quote fetchers, and scheduler into the deployment. [VERIFIED: upstream source]

**How to avoid:** Adapt only needed semantics into Tickflow-owned repositories and document source-to-host mapping. Never run PanWatch in Compose. [VERIFIED: project decisions]

### Pitfall 2: Updating P&L from a second quote source
**What goes wrong:** Portfolio prices disagree with Monitor, SSE, and synchronized data, especially outside trading hours. [VERIFIED: project decisions]

**How to avoid:** Value every position from the shared QuoteService snapshot, falling back to the latest governed close and returning freshness/source metadata. [VERIFIED: project decisions]

### Pitfall 3: Treating outbound delivery as part of rule evaluation
**What goes wrong:** Network timeout/retry blocks the polling thread or hides a persisted/SSE event when delivery fails. [VERIFIED: project decisions]

**How to avoid:** Persist and broadcast first; enqueue bounded asynchronous delivery afterward and write a delivery result independently. [VERIFIED: project decisions]

### Pitfall 4: Duplicating holding alerts for shared instruments
**What goes wrong:** Joining holdings before evaluating every generic market rule emits one alert per account/position instead of one market event. [ASSUMED]

**How to avoid:** Evaluate normal rules over the deduplicated quote frame and position rules over an explicit per-position projection. [ASSUMED]

### Pitfall 5: Breaking existing alert history identity
**What goes wrong:** The current JSONL history identifies deletion by millisecond timestamp, which is not a durable unique identifier and cannot represent multiple delivery outcomes cleanly. [VERIFIED: project codebase]

**How to avoid:** Give SQLite alert events immutable IDs and preserve the old JSONL import only as a one-time compatibility migration, not a second write path. [ASSUMED]

### Pitfall 6: Offline Compose that still calls live services
**What goes wrong:** Startup capability probing, provider selection, or a real webhook makes acceptance flaky or leaks credentials. [VERIFIED: project codebase]

**How to avoid:** Make fixture mode explicit, disable live provider/scheduler paths in it, route both delivery adapters to the receiver, and assert the receiver captured exactly the expected payloads. [ASSUMED]

### Pitfall 7: Copying Hermes persistence rather than behavior
**What goes wrong:** PostgreSQL-specific SQL, ORM models, and `TRUNCATE` semantics leak into a phase constrained to SQLite. [VERIFIED: upstream source]

**How to avoid:** Port pure calculation and guard logic only; use SQLite transactions and snapshot/replay table semantics native to the host. [ASSUMED]

### Pitfall 8: Non-deterministic replay
**What goes wrong:** Current timestamps, unordered queries, mutable AI calls, or future adjustment factors make identical replay requests differ. [VERIFIED: upstream source]

**How to avoid:** Sort symbols, derive replay timestamps from `as_of`, version configuration, prohibit AI calls, and test identical replay output twice. [VERIFIED: upstream source]

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| `startup`/`shutdown` handlers | FastAPI lifespan async context manager | Use the existing lifespan to initialize/close shared operational state and use `TestClient` context management in tests. [CITED: https://github.com/fastapi/fastapi/blob/master/docs/en/docs/advanced/events.md] |
| One shared alert consumption slot | Independent QuoteService subscriber queues | All connected browser clients can receive the same SSE alert/update event. [VERIFIED: project codebase] |
| JSON files/JSONL for monitor rules and history | SQLite operational entities with migrations and keyed delivery history | Required to support account/position relations, archive semantics, and per-delivery audit. [ASSUMED] |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Docker Engine and Compose | Isolated Compose acceptance | Yes | Docker 29.2.1; Compose 5.0.2 | None. [VERIFIED: environment probe] |
| Python / uv | Backend tests and container build | Yes | Python 3.11.2; uv 0.9.30 | None. [VERIFIED: environment probe] |
| Node / pnpm | Frontend build and Playwright test runner | Yes | Node 25.6.0; pnpm 11.1.1 | None. [VERIFIED: environment probe] |
| Chromium/Google Chrome and Playwright CLI | Local browser workflow execution | Yes | Google Chrome and `playwright` executable found | Install the project-pinned browser during the test setup for reproducibility. [VERIFIED: environment probe] |
| `curl`, `sqlite3`, `jq`, `timeout` | Compose verifier diagnostics | Yes | Commands found | Python verifier remains the primary acceptance authority. [VERIFIED: environment probe] |

**Missing dependencies with no fallback:** none. [VERIFIED: environment probe]

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest with pytest-asyncio; Playwright Test after checkpoint approval. [VERIFIED: project codebase] |
| Config file | `backend/pyproject.toml` provides pytest asyncio mode; no Playwright configuration exists yet. [VERIFIED: project codebase] |
| Quick run command | `uv run --directory backend pytest tests/test_operational_portfolio.py tests/test_position_monitor.py -q` [ASSUMED] |
| Full suite command | `uv run --directory backend pytest -q && pnpm --dir frontend build` [VERIFIED: project codebase] |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CORE-01 | Fixture synchronization writes governed Parquet and refreshes views/enriched data. | integration | `uv run --directory backend pytest tests/test_phase1_fixture_sync.py -q` | No - Wave 0. [ASSUMED] |
| CORE-02 | Duplicate key, wrong time semantics, repair-window, and schema drift fail validation. | unit/integration | `uv run --directory backend pytest tests/test_data_contracts.py -q` | No - Wave 0. [ASSUMED] |
| CORE-03 | Account/position CRUD, archive rule, latest quote/close fallback, and aggregate P&L. | integration | `uv run --directory backend pytest tests/test_portfolio_api.py -q` | No - Wave 0. [ASSUMED] |
| CORE-04 | Position/price/market rules persist events, respect cooldown/active time, and record Feishu/Telegram outcomes. | unit/integration | `uv run --directory backend pytest tests/test_position_monitor.py tests/test_notification_delivery.py -q` | No - Wave 0. [ASSUMED] |
| CORE-05 | Portfolio update and alert events reach two independent SSE subscribers; frontend invalidates Portfolio data. | unit/browser | `uv run --directory backend pytest tests/test_portfolio_sse.py -q` | No - Wave 0. [ASSUMED] |
| CORE-06 | Isolated fixture Compose performs health, sync, CRUD, trigger, receiver, SSE, desktop, and mobile flows. | Compose/E2E | `docker compose -p athenaquant-phase1-test -f docker-compose.yml -f compose/phase1.test.yml up --build --abort-on-container-exit --exit-code-from verifier` | No - Wave 0. [ASSUMED] |
| CORE-07 | Upstream adoption map names source, host module, boundary, and regression test. | documentation check | `test -f docs/UPSTREAM-SYNC.md` | No - Wave 0. [ASSUMED] |
| PLAN-01 | Fixed data produces expected playbook entry/stop/target/position values and stored baseline. | unit/integration | `uv run --directory backend pytest tests/test_decision_playbook.py -q` | No - Wave 0. [ASSUMED] |
| PLAN-02 | Bounds reject/clamp invalid fields and replay twice without an AI invocation. | unit/integration | `uv run --directory backend pytest tests/test_decision_adjustments.py tests/test_decision_replay.py -q` | No - Wave 0. [ASSUMED] |

### Sampling Rate

- **Per task commit:** Run the targeted pytest files for the module changed, plus `pnpm --dir frontend build` for UI/API type changes. [ASSUMED]
- **Per wave merge:** `uv run --directory backend pytest -q && pnpm --dir frontend build`. [VERIFIED: project codebase]
- **Phase gate:** Run the isolated Compose command and its Playwright desktop/mobile suite after the backend and frontend suite are green. [VERIFIED: project decisions]

### Wave 0 Gaps

- [ ] `backend/tests/test_phase1_fixture_sync.py` - deterministic offline lake fixture and normal pipeline path.
- [ ] `backend/tests/test_data_contracts.py` - key/time/repair/schema validation.
- [ ] `backend/tests/test_portfolio_api.py`, `test_position_monitor.py`, `test_notification_delivery.py`, and `test_portfolio_sse.py` - operational and event loop behavior.
- [ ] `backend/tests/test_decision_playbook.py`, `test_decision_adjustments.py`, and `test_decision_replay.py` - deterministic decision safety.
- [ ] `frontend/playwright.config.ts` and Phase 1 desktop/mobile specs - browser workflow coverage.
- [ ] `compose/phase1.test.yml`, receiver/verifier images or scripts, and fixture data - isolated acceptance topology.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Yes | Preserve existing API middleware; acceptance uses the documented local test setup only. [VERIFIED: project codebase] |
| V3 Session Management | Yes | Preserve existing authenticated session behavior; no new credential/session mechanism for Portfolio. [VERIFIED: project codebase] |
| V4 Access Control | Yes | Treat archive/delete, notification configuration, and decision adjustment/replay as authenticated operational actions. [ASSUMED] |
| V5 Input Validation | Yes | Pydantic request models plus domain validation for quantities, prices, timestamps, IDs, rule scopes, and adjustment allowlist. [VERIFIED: project codebase] |
| V6 Cryptography | Yes | Reuse the existing HMAC SHA-256 Feishu signing implementation; do not implement custom cryptography. [VERIFIED: project codebase] |

### Known Threat Patterns For This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQLite query construction from filters | Tampering | Parameterize all values; keep table/column choices internal and whitelisted. [ASSUMED] |
| Malformed position/rule/adjustment input | Tampering | Pydantic plus explicit domain constraints and a strict AI-adjustment field allowlist. [VERIFIED: project codebase] |
| Webhook credential leakage or arbitrary callback SSRF | Information disclosure / elevation | Redact credentials/errors, accept Feishu URLs only through the known prefix, construct Telegram Bot API URLs from fixed origin, and make receiver routing test-only. [VERIFIED: project codebase] |
| Slow/failed delivery blocks quote processing | Denial of service | Bounded executor, per-request timeout, persistence/SSE before delivery, and outcome recording. [VERIFIED: project decisions] |
| Replay invokes an AI provider or future data | Tampering | Context-local replay guard, as-of filtered queries, deterministic fixtures, and double-run equality tests. [VERIFIED: upstream source] |
| User-supplied event text rendered as HTML | Elevation | Keep React's normal escaped rendering; do not introduce `dangerouslySetInnerHTML` for alert or delivery content. [ASSUMED] |

## Sources

### Primary

- Project source: `backend/app/main.py`, `backend/app/services/quote_service.py`, `backend/app/strategy/monitor.py`, `backend/app/api/intraday.py`, `backend/app/jobs/daily_pipeline.py`, `backend/app/services/webhook_adapter.py`, and current pytest files - host seams and behavior. [VERIFIED: project codebase]
- Upstream source: `/root/source/HermesAlpha/app/engines/playbook.py`, `app/llm/review_agent.py`, `app/services/replay.py`, and tests - portable decision/replay safety semantics. [VERIFIED: upstream source]
- Upstream source: `/root/source/tmp/PanWatch/src/web/models.py`, `src/web/api/accounts.py`, `src/web/api/price_alerts.py`, and `src/core/notifier.py` - source portfolio/notification semantics to adapt rather than deploy. [VERIFIED: upstream source]
- [FastAPI documentation](https://github.com/fastapi/fastapi/blob/master/docs/en/docs/advanced/testing-events.md) - lifespan and TestClient lifecycle. [CITED: https://github.com/fastapi/fastapi/blob/master/docs/en/docs/advanced/testing-events.md]
- [sse-starlette documentation](https://github.com/sysid/sse-starlette/blob/main/_autodocs/INDEX.md) - EventSourceResponse event/ping/send timeout support. [CITED: https://github.com/sysid/sse-starlette/blob/main/_autodocs/INDEX.md]
- [Playwright documentation](https://github.com/microsoft/playwright/blob/main/docs/src/test-webserver-js.md) - local web server and base URL configuration. [CITED: https://github.com/microsoft/playwright/blob/main/docs/src/test-webserver-js.md]

### Secondary

- `/root/source/tmp/daily_stock_data/docs/SCHEMAS.md` and tests - upstream contract concepts for keys, market-time semantics, and repair replacement. [VERIFIED: upstream source]

## Assumptions Log

| # | Claim | Section | Risk If Wrong |
|---|-------|---------|---------------|
| A1 | A small versioned-SQL migration runner over Python `sqlite3` is the best fit and can safely replace JSON operational persistence without an ORM package. | Architecture Pattern 1 | Migration rollback/concurrency requirements may justify a different mechanism. |
| A2 | Position rules should use an explicit per-position projection and a `type='position'` model to avoid duplicate generic alerts. | Architecture Pattern 3 | Existing rule model/API may need a different compatible representation. |
| A3 | Quiet periods should suppress only delivery while retaining the event, and cooldown should suppress duplicate events. | Architecture Pattern 4 | Product interpretation of "every hit" may require recording cooldown-suppressed evaluations too. |
| A4 | The acceptance fixture provider can run through the host's normal repository/pipeline path without a live Tickflow capability probe. | Architecture Pattern 6 | The provider/capability seams may require a narrower test-only orchestration entry point. |
| A5 | The exact P&L formula should use cost-price times quantity and expose null/unknown valuation when no shared quote/close exists. | Architecture Pattern 2 | Product may require invested amount to override cost for some accounting cases. |

## Resolved Decisions

1. **Cooldown and quiet-period semantics are distinct.**
   - Cooldown-suppressed evaluations are non-events: they create no alert-history or delivery row. Quiet-period or active-time-suppressed delivery follows an accepted hit: the alert event remains persisted and the channel attempt records a `skipped` outcome with a safe reason. An explicit high-severity bypass may deliver during a quiet period. This preserves D-05, D-07, and D-08 without creating high-volume cooldown history. [RESOLVED: phase revision]

2. **`docs/UPSTREAM-SYNC.md` is the canonical upstream source-manifest workflow.**
   - It records each source path and selected revision/source identity, AthenaQuant host target, local owner, adaptation style, preserved boundary, named regression coverage, and review/update procedure. Phase 1 does not use a Git remote, patch series, or copied upstream runtime as its synchronization workflow. [RESOLVED: phase revision]

3. **Optional live review uses the existing configured OpenAI-compatible client only.**
   - The Tickflow-owned decision gateway calls `app.services.ai_provider.generate_ai_text` only when the current provider is the configured OpenAI-compatible provider, records the configured provider/model with a typed proposal and per-field provenance, and treats the response as a bounded proposal rather than decision authority. Unit tests inject an offline fake provider. Missing configuration, malformed output, and provider failure return the deterministic baseline with an unavailable-review state. Replay and fixture Compose prohibit the gateway; fixture Compose disables review and contains no AI credential or provider URL. [RESOLVED: `backend/app/services/ai_provider.py`, phase revision]

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM - existing host stack is directly verified; Playwright documentation is official but its current package release is flagged SUS. [VERIFIED: project codebase]
- Architecture: HIGH - core host, PanWatch, and Hermes integration seams were inspected directly. [VERIFIED: project codebase]
- Pitfalls: MEDIUM - host/upstream pitfalls are evidenced; migration and position-rule representations remain implementation choices. [VERIFIED: project codebase]

**Research date:** 2026-07-10
**Valid until:** 2026-08-09 for host architecture; re-check Playwright package legitimacy immediately before installation. [ASSUMED]
