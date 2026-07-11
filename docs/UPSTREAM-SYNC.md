# Upstream Synchronization Manifest

This manifest is the canonical source-manifest workflow for every Phase 1 adoption. It is deliberately **not** a Git remote, patch series, copied runtime, or deployment plan.

## Deployment and persistence boundaries

- Tickflow is the sole deployed host application. No PanWatch, HermesAlpha, daily-stock-data, second application, database, queue, quote feed, scheduler, or SSE endpoint is deployed.
- Parquet, DuckDB, and Polars remain the authoritative market-data boundary. `operational.db` (SQLite) owns accounts, positions, rules, alert and delivery history, AI-proposal provenance, decision snapshots, and replay records.
- Source projects are semantic references only. An adoption may transfer the listed behavior into its listed AthenaQuant seam; it must not transfer an upstream runtime or persistence boundary.

## Adoption map

| Upstream source and identity | Selected capability | AthenaQuant host target | Local owner | Adaptation style | Preserved boundary | Exact regression coverage |
| --- | --- | --- | --- | --- | --- | --- |
| `tchivs/tickflow-stock-panel` workspace baseline, Phase 1 host seam | FastAPI lifecycle, governed lake, `MonitorRuleEngine`, `QuoteService`, and the sole intraday SSE stream | `backend/app/main.py`, `backend/app/tickflow/`, `backend/app/strategy/monitor.py`, `backend/app/services/quote_service.py`, `backend/app/api/intraday.py` | Tickflow host maintainers | Extend existing seams in place | One deployed host; Parquet/DuckDB/Polars market authority; no second quote loop or EventSource | `backend/tests/test_phase1_fixture_sync.py`, `backend/tests/test_position_monitor.py`, `backend/tests/test_portfolio_sse.py`, `compose/phase1/verifier.py` |
| `tchivs/PanWatch` `src/web/models.py` (Account, Position, notification records) | Multi-account, holding, archive, and history semantics | `backend/app/operational/{migrations,repository}.py`, `backend/app/portfolio/`, `backend/app/api/portfolio.py` | Operational portfolio maintainers | Reimplement semantics through parameterized SQLite repository | `operational.db` owns only operational records; no SQLAlchemy/PanWatch DB, poller, or API | `backend/tests/test_portfolio_api.py` |
| `tchivs/PanWatch` `src/core/notifier.py` | Telegram-shaped notification semantics and nonblocking outcome handling | `backend/app/notifications/delivery.py`, `backend/app/services/quote_service.py`, `backend/app/api/alerts.py` | Notifications maintainers | Narrow Feishu/Telegram adapter, durable independent outcomes | No Apprise runtime, external endpoint, credential, or delivery path in fixtures; receiver-only internal test delivery | `backend/tests/test_notification_delivery.py`, `compose/phase1/verifier.py` |
| `tchivs/HermesAlpha` `app/engines/playbook.py` | Deterministic entry, stop, targets, sizing, action, and replay semantics | `backend/app/decision/{playbook,adjustments,ai_review,replay}.py`, `backend/app/api/decision.py` | Decision-domain maintainers | Reimplement pure calculation and guards over governed history | No Hermes ORM/PostgreSQL/service; SQLite keeps snapshots and audits, governed lake supplies history | `backend/tests/test_decision_playbook.py`, `backend/tests/test_decision_adjustments.py`, `backend/tests/test_decision_ai_review.py`, `backend/tests/test_decision_replay.py` |
| `bzcsk2/daily_stock_data` source contract reference | Primary keys, market-time semantics, repair window, and schema-drift governance | `backend/app/contracts/{market_data,validator}.py`, `backend/app/data_providers/fixture_provider.py`, `backend/app/jobs/daily_pipeline.py` | Data-governance maintainers | Map contracts to existing lake schemas and fixture provider | No copied database, pipeline, or feed; validation reads governed Parquet only | `backend/tests/test_data_contracts.py`, `backend/tests/test_phase1_fixture_sync.py` |

## Review and update workflow

1. Compare a proposed upstream revision or source identity with this manifest and record the candidate identity in the relevant row review.
2. Adapt only the listed capability into its listed host target. Preserve the stated deployment and persistence boundary; reject additions that introduce an upstream app, database, queue, quote feed, scheduler, or SSE endpoint.
3. Run every named regression in that row, plus the fixture-only Compose acceptance when a cross-boundary seam changes.
4. Record the accepted source identity/revision, owner review, behavior delta, and passing regression evidence in the change review that updates this manifest.

The manifest—not a fork merge, remote tracking branch, patch series, or copied upstream runtime—is the synchronization authority for Phase 1.
