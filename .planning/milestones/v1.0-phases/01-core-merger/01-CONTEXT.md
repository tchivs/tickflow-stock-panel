# Phase 1: Core Merger - Context

**Gathered:** 2026-07-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver a single tickflow-hosted Docker Compose application where an investor can synchronize governed market data, verify its data contract, manually manage multi-account holdings, receive and review holding-aware alerts, observe live monitoring updates, and inspect auditable deterministic playbooks. The phase also documents how adopted upstream capabilities are synchronized without crossing Parquet/SQLite boundaries. It integrates selected PanWatch portfolio and notification capabilities into tickflow; it does not run, embed, or deploy a separate PanWatch application.

</domain>

<decisions>
## Implementation Decisions

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

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Product And Scope
- `docs/ARCHITECTURE.md` -- target architecture, Phase 1 scope, data boundaries, and progressive adoption sequence.
- `.planning/PROJECT.md` -- core value, integration decision, data and deployment constraints.
- `.planning/REQUIREMENTS.md` -- Phase 1 requirements `CORE-01` through `CORE-07` and `PLAN-01` through `PLAN-02`.
- `.planning/ROADMAP.md` -- Phase 1 goal and observable success criteria.
- `.planning/intel/SYNTHESIS.md` -- planning-ingest source summary.

### Tickflow Integration Points
- `backend/app/strategy/monitor.py` -- `MonitorRuleEngine` rule evaluation, cooldown, event construction, and alert-handler boundary.
- `backend/app/strategy/monitor_rules.py` -- persisted monitor-rule model and validation helpers.
- `backend/app/api/monitor_rules.py` -- monitor rule API and engine synchronization.
- `backend/app/services/quote_service.py` -- quote subscription, event broadcast, alert handoff, and notification integration.
- `backend/app/api/intraday.py` -- SSE event stream and existing alert event contract.
- `backend/app/services/notify_adapter.py` -- nonblocking notification adapter behavior.
- `backend/app/api/routes.py` -- health endpoint used by Compose smoke verification.
- `docker-compose.yml` -- current single-service deployment boundary.
- `backend/tests/` -- established pytest conventions for monitor, data, and real-time regression coverage.

### PanWatch Source Reference
- `/root/source/tmp/PanWatch/src/web/models.py` -- source account, holding, price-alert rule, and hit persistence semantics to selectively adapt.
- `/root/source/tmp/PanWatch/src/web/api/accounts.py` -- source multi-account and holding CRUD behavior.
- `/root/source/tmp/PanWatch/src/web/api/price_alerts.py` -- source price-alert API and history behavior.
- `/root/source/tmp/PanWatch/src/core/notifier.py` -- source Telegram and multi-channel notifier behavior.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `MonitorRuleEngine` already evaluates strategy, signal, price, market, and ladder rules, emits structured events with condition snapshots, and applies per-rule/symbol cooldowns.
- `QuoteService` already fans events to independent SSE subscribers; `api/intraday.py` exposes `strategy_alert`, `quotes_updated`, `depth_updated`, and review-progress events.
- `api/monitor_rules.py` already validates, persists, and synchronizes rule changes with the monitoring engine.
- `services/notify_adapter.py` and `services/webhook_adapter.py` already preserve the rule-processing path when external delivery fails.
- PanWatch provides source models for accounts, one holding per account/instrument, cost/quantity/funds/style fields, and Telegram notification configuration.

### Established Patterns
- Tickflow keeps time-series market data in Parquet and broadcasts intraday state through one QuoteService/SSE path.
- Tickflow's current monitor rules are persisted independently of the Parquet lake and are synchronized into an in-memory engine after API changes.
- Docker Compose packages FastAPI and built frontend assets as one service; `/health` is intentionally public for readiness checks.
- Existing backend tests are pytest-based and cover monitor and real-time behavior, providing the default testing style for new backend work.

### Integration Points
- Register Portfolio persistence and API routes inside the existing FastAPI app and data-directory lifecycle.
- Extend monitor-rule types/scopes and alert persistence without creating a second scheduler, quote feed, or SSE endpoint.
- Add Portfolio navigation, desktop table, mobile cards, and form dialogs to the existing React workspace.
- Drive Compose verification through the current one-service deployment plus test-only isolation and local receiver dependencies.

</code_context>

<specifics>
## Specific Ideas

- Keep tickflow as the sole host application and treat `/root/source/tmp/PanWatch/` as an external upstream reference, not a nested repository or deployable service.
- Show user-facing data freshness for position valuation rather than presenting an unstated last price as live.
- Deliver notification outcomes as observable history alongside the underlying rule hit.

</specifics>

<deferred>
## Deferred Ideas

- Broker connections, transaction imports, realized-gain accounting, and tax-lot calculation are outside Phase 1.
- PWA installation, offline behavior, and a standalone mobile shell are outside Phase 1.
- Notification channels beyond Feishu and Telegram are future adapter extensions.
- Strict screenshot-based visual regression is not required for Phase 1; browser workflow checks are required.

</deferred>

---

*Phase: 1-Core Merger*
*Context gathered: 2026-07-10*
