# Phase 05 Kronos Capability Coverage

**Reviewed upstream:** `shiyu-coder/Kronos@67b630e67f6a18c9e9be918d9b4337c960db1e9a` (official README, `model/kronos.py`, regression test, examples, and fine-tuning tree)

**Policy:** Every official capability starts as **INTEGRATE**. An **OPT-OUT** is permitted only with a Phase 05 scope or safety reason. INTEGRATE means AthenaQuant implements or preserves the capability through its governed, local-only boundary; it does not mean copying upstream demos or granting downstream authority.

```coverage
[
  {"capability":"KronosTokenizer and Kronos loading","decision":"INTEGRATE","reason":""},
  {"capability":"Model/tokenizer matching","decision":"INTEGRATE","reason":""},
  {"capability":"Kronos-mini and Tokenizer-2k","decision":"INTEGRATE","reason":""},
  {"capability":"Kronos-small and Tokenizer-base","decision":"INTEGRATE","reason":""},
  {"capability":"Kronos-base and Tokenizer-base","decision":"INTEGRATE","reason":""},
  {"capability":"Kronos-large","decision":"OPT-OUT","reason":"Official checkpoint is not open-source, so it cannot be integrity-pinned or provisioned."},
  {"capability":"Single-series prediction","decision":"INTEGRATE","reason":""},
  {"capability":"Batch prediction predict_batch","decision":"OPT-OUT","reason":"D-09 excludes portfolio and multi-series batch forecasting."},
  {"capability":"Temperature T","decision":"INTEGRATE","reason":""},
  {"capability":"Top-k sampling","decision":"INTEGRATE","reason":""},
  {"capability":"Top-p sampling","decision":"INTEGRATE","reason":""},
  {"capability":"sample_count","decision":"INTEGRATE","reason":""},
  {"capability":"Upstream averaging across samples","decision":"OPT-OUT","reason":"The public upstream mean would violate D-10 and FORE-01."},
  {"capability":"Retained per-sample paths before averaging","decision":"INTEGRATE","reason":""},
  {"capability":"P10 P50 P90 derivation","decision":"INTEGRATE","reason":""},
  {"capability":"Required OHLC input","decision":"INTEGRATE","reason":""},
  {"capability":"Volume input and output","decision":"INTEGRATE","reason":""},
  {"capability":"Amount input and output variant","decision":"INTEGRATE","reason":""},
  {"capability":"Prediction without volume or amount example","decision":"OPT-OUT","reason":"D-09 requires governed daily OHLCV."},
  {"capability":"Input normalization and inverse normalization","decision":"INTEGRATE","reason":""},
  {"capability":"Max-context truncation","decision":"INTEGRATE","reason":""},
  {"capability":"Historical and future timestamps","decision":"INTEGRATE","reason":""},
  {"capability":"Checkpoint download and provisioning","decision":"INTEGRATE","reason":""},
  {"capability":"Local-only model loading","decision":"INTEGRATE","reason":""},
  {"capability":"Safetensors checkpoint handling","decision":"INTEGRATE","reason":""},
  {"capability":"Pinned official regression smoke","decision":"INTEGRATE","reason":""},
  {"capability":"Multi-GPU tokenizer fine-tuning","decision":"OPT-OUT","reason":"Training is outside FORE-01 and single-container bounded inference."},
  {"capability":"Multi-GPU predictor fine-tuning","decision":"OPT-OUT","reason":"Training would add mutable unapproved checkpoint authority."},
  {"capability":"Qlib preprocessing integration","decision":"OPT-OUT","reason":"Governed Parquet DuckDB Polars remains the sole market-data boundary."},
  {"capability":"Qlib top-K backtest example","decision":"OPT-OUT","reason":"D-12 forbids forecast-driven strategy or plan authority."},
  {"capability":"Standalone plotting example","decision":"OPT-OUT","reason":"Existing ECharts plus equivalent tables is the approved presentation path."},
  {"capability":"Official live web demo","decision":"OPT-OUT","reason":"External demo state is not local governed object-authorized AthenaQuant state."},
  {"capability":"Upstream GUI example","decision":"OPT-OUT","reason":"Existing Backtest and Analysis workspaces are binding; no second shell is allowed."},
  {"capability":"Upstream backtest examples","decision":"OPT-OUT","reason":"Forecast remains immutable evidence and never an automatic action."},
  {"capability":"AKShare acquisition examples","decision":"OPT-OUT","reason":"Runtime input comes only from AthenaQuant governed repository and synchronization boundaries."},
  {"capability":"Reviewed source synchronization","decision":"INTEGRATE","reason":""},
  {"capability":"CPU inference","decision":"INTEGRATE","reason":""},
  {"capability":"GPU inference","decision":"INTEGRATE","reason":""},
  {"capability":"GPU-parallel batch acceleration","decision":"OPT-OUT","reason":"It belongs to the D-09-excluded multi-series path."},
  {"capability":"Verbose autoregressive progress","decision":"OPT-OUT","reason":"Raw progress and logs can disclose internals; only allowlisted committed stages are exposed."}
]
```

## Capability-surface matrix

Only an existing PLAN task plus its named acceptance command is evidence. Plan creation is not execution: rows below are **planned executable coverage**, and remain pending until their commands pass.

| Official Kronos capability | Decision | Phase 05 integration or one-line opt-out reason | Real plan/task evidence | Automated acceptance |
|---|---|---|---|---|
| `KronosTokenizer` and `Kronos` loading | INTEGRATE | Deployment-owned local directories only after catalog revision/digest/type/root checks. | 05-07 T2/T3; 05-10 T1/T2 | `pytest tests/test_kronos_vendor_sync.py tests/test_kronos_provisioner.py tests/forecast/test_catalog.py tests/forecast/test_kronos_adapter.py -x` |
| Model/tokenizer matching | INTEGRATE | Catalog binds official pair and rechecks before task allocation. | 05-10 T1; 05-13 T2 | `pytest tests/forecast/test_catalog.py tests/forecast/test_runner.py -x` |
| Kronos-mini + Tokenizer-2k | INTEGRATE | Default CPU catalog profile; official 2048 metadata with deployment-bounded lookback. | 05-01 T1 approval; 05-07 T3; 05-10 T1 | `pytest tests/test_kronos_provisioner.py tests/forecast/test_catalog.py -x` |
| Kronos-small + Tokenizer-base | INTEGRATE | Approved catalog profile with official 512 context and pinned local assets. | 05-01 T1; 05-07 T3; 05-10 T1 | same provisioner/catalog command |
| Kronos-base + Tokenizer-base | INTEGRATE | Approved non-default profile; resource admission may report it unavailable. | 05-01 T1; 05-07 T3; 05-10 T1; 05-13 T2 | `pytest tests/test_kronos_provisioner.py tests/forecast/test_catalog.py tests/forecast/test_runner.py -x` |
| Kronos-large | OPT-OUT | Official checkpoint is not open-source, so it cannot be integrity-pinned/provisioned. | 05-01 T1; 05-07 T3; 05-10 T1 rejection cases | `pytest tests/test_kronos_provisioner.py tests/forecast/test_catalog.py -x` |
| Single-series prediction | INTEGRATE | One persisted A-share instrument is the D-09 request boundary. | 05-10 T1; 05-14 T1; 05-16 T2 | `pytest tests/forecast/test_input.py tests/test_phase5_optional_host.py -k forecast -x`; Playwright scenario 8/9 |
| Batch prediction (`predict_batch`) | OPT-OUT | D-09 excludes portfolio/multi-series batch forecasting. | 05-04 T1 contract; 05-10 T1 enforcement; 05-16 T2 absence | `pytest tests/forecast/test_input.py -x`; Playwright scenario 8 |
| Temperature `T` | INTEGRATE | Deployment-bounded and frozen into immutable run/record. | 05-04 T2; 05-10 T2; 05-13 T2 | `pytest tests/forecast/test_kronos_adapter.py tests/forecast/test_runner.py -x` |
| Top-k sampling | INTEGRATE | Bounded server config, never unbounded browser input. | 05-04 T2; 05-10 T2 | `pytest tests/forecast/test_kronos_adapter.py -x` |
| Top-p sampling | INTEGRATE | Bounded server config, never unbounded browser input. | 05-04 T2; 05-10 T2 | same adapter command |
| `sample_count` | INTEGRATE | Exactly 32 persisted paths; resource rejection cannot silently reduce it. | 05-04 T2; 05-10 T2; 05-16 T2 | adapter command; Playwright scenario 9 |
| Upstream averaging across samples | OPT-OUT | Public upstream mean would violate D-10/FORE-01. | 05-04 T2 contract; 05-10 T2 pre-mean adapter | `pytest tests/forecast/test_kronos_adapter.py -x` |
| Retained per-sample paths before averaging | INTEGRATE | Reviewed seam returns `[32,horizon,feature]` before mean. | 05-10 T2; 05-13 T2; 05-16 T2 | adapter/runner command; Playwright scenario 9 |
| P10/P50/P90 derivation | INTEGRATE | Fixed quantiles over path axis 0, with warnings preserved. | 05-04 T2; 05-10 T2; 05-16 T2 | adapter command; Playwright scenario 9 |
| Required OHLC input | INTEGRATE | Governed daily A-share OHLCV only; schema/order/coverage/adjustment/fingerprint frozen. | 05-04 T1; 05-10 T1 | `pytest tests/forecast/test_input.py -x` |
| Volume input/output | INTEGRATE | Volume remains validated and immutable; economic issues become warnings. | 05-10 T1/T2; 05-16 T2 | `pytest tests/forecast/test_input.py tests/forecast/test_kronos_adapter.py -x`; scenario 9 |
| Amount input/output variant | INTEGRATE | Included only when governed input supplies it; exact feature schema is frozen. | 05-10 T1/T2 | input/adapter command |
| Prediction without volume/amount example | OPT-OUT | D-09 requires governed daily OHLCV, so OHLC-only convenience input is inadmissible. | 05-04 T1; 05-10 T1 rejection case | `pytest tests/forecast/test_input.py -x` |
| Input normalization and inverse normalization | INTEGRATE | Reviewed adapter preserves upstream semantics and validates shape/finite output. | 05-10 T2 | `pytest tests/forecast/test_kronos_adapter.py -x` |
| Max-context truncation | INTEGRATE | Catalog records official context; server freezes bounded lookback and rejects insufficient coverage. | 05-10 T1/T2 | `pytest tests/forecast/test_catalog.py tests/forecast/test_input.py -x` |
| Historical and future timestamps | INTEGRATE | History comes from governed OHLCV; future dates from governed CN-A sessions, never weekdays. | 05-04 T1; 05-10 T1; 05-14 T1 | `pytest tests/forecast/test_input.py tests/forecast/test_calibration.py -x` |
| Checkpoint download/provisioning | INTEGRATE | Explicit operator action after approval; routine runtime/tests never download. | 05-01 T1; 05-07 T3 | `pytest tests/test_phase5_optional_dependencies.py tests/test_kronos_provisioner.py -x` |
| Local-only model loading | INTEGRATE | Worker receives catalog-approved local paths with no network/remote-code fallback. | 05-10 T1/T2; 05-13 T2 | catalog/adapter/runner command |
| Safetensors checkpoint handling | INTEGRATE | Only approved safetensors/config allowlist with full SHA-256. | 05-01 T1; 05-07 T3; 05-10 T1 | provisioner/catalog command |
| Pinned official regression smoke | INTEGRATE | Opt-in approved local pair, network denied; not part of routine suite. | 05-04 T2; 05-17 T1/human-check | `pytest tests/forecast/test_kronos_regression.py -m kronos_model -x` when approved assets exist |
| Multi-GPU tokenizer fine-tuning | OPT-OUT | Training is outside FORE-01 and single-container bounded inference. | 05-07 T2 vendor file allowlist | `pytest tests/test_kronos_vendor_sync.py -x` |
| Multi-GPU predictor fine-tuning | OPT-OUT | Training would add mutable/unapproved checkpoint authority. | 05-07 T2 | same vendor-sync command |
| Qlib preprocessing integration | OPT-OUT | Governed Parquet/DuckDB/Polars remains the sole market-data boundary. | 05-07 T2; 05-10 T1 | vendor-sync/input commands |
| Qlib top-K backtest example | OPT-OUT | D-12 forbids forecast-driven strategy/plan authority. | 05-07 T2; 05-13 T2; 05-17 T1/T2 | vendor-sync/runner/final no-action commands |
| Standalone plotting example | OPT-OUT | Existing ECharts plus equivalent tables is the approved presentation path. | 05-16 T2; 05-17 T2 | Playwright scenarios 9/12 |
| Official live web demo | OPT-OUT | External demo state is not local, governed, object-authorized, or part of AthenaQuant. | 05-16 T2; 05-17 T2 unexpected-request denial | full Phase 05 Playwright command |
| Upstream GUI example | OPT-OUT | Existing Backtest/Analysis workspaces are binding; no second shell/model console. | 05-15 T2; 05-16 T3; 05-17 T2 | Playwright scenarios 1/12 |
| Upstream backtest examples | OPT-OUT | Forecast remains immutable evidence and never automatic action. | 05-13 T2; 05-17 T1/T2 | runner no-action spies and Playwright scenario 13 |
| AKShare acquisition/examples | OPT-OUT | Runtime input comes only from AthenaQuant governed repository/sync boundary. | 05-10 T1 | `pytest tests/forecast/test_input.py -x` |
| Reviewed source synchronization | INTEGRATE | Minimal inference source, MIT license, fixed commit/file hashes, reproducible review-only sync. | 05-01 T1; 05-07 T2 | `pytest tests/test_kronos_vendor_sync.py -x` and `python scripts/sync_kronos.py --verify-local` |
| CPU inference | INTEGRATE | Mini default; applied CPU/thread/memory/wall limits are frozen. | 05-10 T1/T2; 05-13 T2; 05-17 T1/human-check | adapter/runner commands; optional real-model smoke |
| GPU inference | INTEGRATE | Allowed only for a locally approved catalog/device under the same bounded admission; CPU remains required. | 05-10 T1; 05-13 T2 | catalog/runner commands |
| GPU-parallel batch acceleration | OPT-OUT | It belongs to the D-09-excluded multi-series path. | 05-10 T1; 05-13 T2 | input/runner rejection commands |
| Verbose autoregressive progress | OPT-OUT | Raw progress/logs can disclose internals; only committed allowlisted stages enter bounded SSE. | 05-14 T1; 05-15 T1; 05-17 T1/T2 | host Forecast SSE tests and Playwright scenario 10 |

## Coverage invariants

- Every **INTEGRATE** row cites at least one existing PLAN task and a focused automated acceptance command.
- Every **OPT-OUT** row has a locked Phase 05 scope/safety reason plus a real enforcement/absence test; none is omitted for difficulty.
- Planned evidence remains pending until execution. A missing plan/task/command must be marked **MISSING**, never inferred covered.
- Runtime prediction is local-only. Network is restricted to explicit Plan 05-07 operator provisioning/synchronization after Plan 05-01 approval; routine startup, requests, workers, host tests, and browser tests deny network.
- Forecast results remain immutable research records. No capability grants thesis, strategy, monitor, decision-plan, portfolio, broker, or market-action authority.

## Phase source audit

| Source | ID / section | Required item | Real plan/task mapping | Status |
|---|---|---|---|---|
| GOAL | Phase 05 goal | Optional distillation, thesis evidence, and forecast capabilities leave completed v1 unchanged. | 05-14 T2; 05-15 T2; 05-16 T3; 05-17 T1/T2 | COVERED |
| GOAL | success 1 | Create/evaluate Shadow strategy from actual logs. | 05-08 T1/T2; 05-11 T1/T2; 05-15 T2; 05-17 | COVERED |
| GOAL | success 2 | Inspect thesis valuation, invalidation conditions, and periodic checks. | 05-09 T1/T2; 05-12 T1/T2; 05-16 T1/T3; 05-17 | COVERED |
| GOAL | success 3 | Request forecast with quantiles, sampled paths, and checkpoint. | 05-10 T1/T2; 05-13 T1/T2; 05-14 T1/T2; 05-16 T2/T3; 05-17 | COVERED |
| REQ | SHDW-01 | Immutable actual-log Shadow derivation/evaluation and safe UI. | 05-02, 05-06, 05-07, 05-08, 05-11, 05-14, 05-15, 05-17 named tasks | COVERED; descriptor-less flag closes only on final green scenarios |
| REQ | THES-01 | Immutable versions/anchors/conditions/checks/human review and safe UI. | 05-03, 05-06, 05-09, 05-12, 05-14, 05-16, 05-17 named tasks | COVERED; descriptor-less flag closes only on final green scenarios |
| REQ | FORE-01 | Approved Kronos catalog/input/paths/quantiles/tasks/recovery/calibration/API/SSE/UI. | 05-01, 05-04, 05-06, 05-07, 05-10, 05-13, 05-14, 05-15, 05-16, 05-17 named tasks | COVERED |
| CONTEXT | D-01 | Local execution logs only; no broker/manual entry. | 05-02 T1; 05-08 T1; 05-15 T2; 05-17 scenario 2 | COVERED |
| CONTEXT | D-02 | Every import immutable/attributable; corrections append. | 05-02 T1; 05-08 T1; 05-15 T2; 05-17 scenario 2/4 | COVERED |
| CONTEXT | D-03 | Explainable candidate with rules/features/params/sources/limits. | 05-02 T2; 05-08 T2; 05-15 T2; 05-17 scenario 3 | COVERED |
| CONTEXT | D-04 | Frozen non-overlap IS/OOS retention; no activation. | 05-02 T2; 05-11 T1; 05-15 T2; 05-17 scenario 3/13 | COVERED |
| CONTEXT | D-05 | Immutable predecessor-linked thesis versions/history. | 05-03 T1; 05-09 T1; 05-12 T2; 05-16 T1; 05-17 scenario 5 | COVERED |
| CONTEXT | D-06 | Valuation range plus assumptions. | 05-03 T1; 05-09 T1; 05-16 T1; 05-17 scenario 5 | COVERED |
| CONTEXT | D-07 | Restricted conditions; matched is pending; user confirms. | 05-03 T1/T2; 05-09 T2; 05-12 T1/T2; 05-16 T1; 05-17 scenarios 6/7 | COVERED |
| CONTEXT | D-08 | Per-condition cadence and append-only restart-safe checks. | 05-03 T2; 05-09 T1; 05-12 T1; 05-14 T2; 05-16 T1; 05-17 scenario 6 | COVERED |
| CONTEXT | D-09 | One governed stock, daily OHLCV, 5/20/60. | 05-04 T1; 05-10 T1; 05-14 T1; 05-16 T2; 05-17 scenario 8 | COVERED |
| CONTEXT | D-10 | Exactly 32 retained paths and fixed P10/P50/P90 visible. | 05-04 T2; 05-10 T2; 05-13 T2; 05-16 T2; 05-17 scenario 9 | COVERED |
| CONTEXT | D-11 | Approved pinned local catalog/provenance; no latest. | 05-01 T1; 05-07 T2/T3; 05-10 T1/T2; 05-16 T2; 05-17 scenarios 8/9 | COVERED |
| CONTEXT | D-12 | Immutable forecast, CAS/recovery, append-only outcomes/calibration, no authority. | 05-04 T2/T3; 05-13 T1/T2; 05-14 T1; 05-16 T2; 05-17 scenarios 10/11/13 | COVERED |
| RESEARCH | architecture/stack | Separate optional domains; one SQLite/lake/FastAPI/TanStack/SSE/ECharts; no second runtime. | 05-06 T1/T2; 05-14 T2; 05-15 T1; 05-16 T3; 05-17 T1/T2 | COVERED |
| RESEARCH | Shadow patterns/failures | Canonical mapping, immutable artifacts/rows, no destructive dedupe, allowlisted rule JSON, chronological IS/OOS. | 05-02; 05-08; 05-11; 05-15; 05-17 | COVERED |
| RESEARCH | Thesis patterns/failures | Fixed AST/evidence, event state, server principal, lease/restart due scanner. | 05-03; 05-09; 05-12; 05-14; 05-16; 05-17 | COVERED |
| RESEARCH | Forecast patterns/failures | Catalog/calendar/input/pre-mean adapter/bounded CAS runner/artifacts/calibration. | 05-04; 05-07; 05-10; 05-13; 05-14; 05-16; 05-17 | COVERED |
| RESEARCH | package audit | SUS approval precedes lock/vendor/provision mutation. | 05-01 T1 → 05-07 T1/T2/T3 explicit preconditions | COVERED |
| RESEARCH | Open Questions (RESOLVED) | Broker mapping, governed calendar, SUS lock, CPU resource policy have owners. | 05-02/08/17; 05-04/10/14; 05-01/07; 05-10/13/17 human-check | COVERED |
| RESEARCH | security/ASVS | File, AST/SQL, checkpoint, drift, resource, browser authority, disclosure, and no-action controls. | ASVS L1 traceability tables in every 05-01–05-17 threat model | COVERED |
| VALIDATION | 05-W0-01–10 | Strict RED contract creation maps to ordinary-green production owner and final acceptance. | 05-02–05 and 05-08–17 exactly as 05-VALIDATION.md | COVERED |
| VALIDATION | sampling continuity | No three implementation tasks without focused automated verification; no watch mode. | 05-VALIDATION.md Sampling Continuity Audit | COVERED |
| VALIDATION | real-model smoke | Approved local model only; no routine download; honest unavailable status. | 05-01 T1; 05-04 T2; 05-17 T1/human-check | COVERED |
| UI-SPEC | exact contract / 40 considerations | Exact copy, states, 24/16/14/12, tokens, 4px spacing, 1440/1024/375, WCAG/reduced motion/table equivalence/independence. | 05-05 T2 strict contract; 05-15 T1/T2; 05-16 T1/T2/T3; 05-17 T2 | COVERED |
| UI-SPEC | scenarios 1–13 | Each approved scenario is a distinct final production browser test. | 05-05 T2; 05-17 T2 | COVERED |
| COVERAGE | every INTEGRATE row | Governed local capability with real task and command. | Row-specific evidence above | COVERED |
| COVERAGE | every OPT-OUT row | Explicit scope/safety rejection plus enforcement/absence test. | Row-specific evidence above | COVERED |

**Audit result:** all GOAL, REQ, RESEARCH, and CONTEXT source items are mapped to existing plan tasks and executable acceptance. No item is silently dropped. Descriptor-less SHDW-01/THES-01 assumptions remain flagged until Plan 05-17's named green host/browser scenarios. FORE-01 concurrency is resolved by Plan 05-13's concrete CAS state/idempotency/global-lease/retry/commit/restart semantics and Plan 05-14's unique calibration append; coverage remains planned—not executed—until those commands pass.
