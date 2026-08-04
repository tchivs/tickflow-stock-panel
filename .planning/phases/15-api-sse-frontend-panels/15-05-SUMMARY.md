# Plan 15-05 Summary — SSE Streaming + Reporting Breadth (SC3)

**Status:** complete · **Committed:** e63ad08 (+ polish commit for shared-job fixes)

## What landed

- `api/walkforward_sse.py`: durable `_WfJob` pattern (module-level `_wf_jobs` dict keyed deterministically per plan, thread-safe lock, TTL cleanup):
  - `POST /api/research/wf/plans/{plan_id}/run` — records fold-by-fold progress (fold_index / total_folds / is_oos / status) + terminal `done` into the job; 409 while a run is in progress.
  - `GET /api/research/wf/plans/{plan_id}/stream` — SSE: replays recorded history on connect, then live events + keepalives; closes after `done`.
- `portfolio_panels.py`: paper approve/reject emit the shared SSE fan-out (`quote_service.notify_quote`), so RebalancePlan auto-refreshes via `SSE_INVALIDATE_PREFIXES` (`'paper'` added; `optimization-runs`/`rebalance-plans` prefixes already registered in 15-01/15-04).
- Frontend: `api.runWfPlan`, `QK.wfPlanStream` (per plan), `WalkForward.tsx` `LiveProgress` component (EventSource with reconnect state, fold progress bar, OOS fold amber-labeled).
- `tests/api/test_walkforward_sse.py`: 5 tests (fold progress, replay→done, idle keepalive→replay after run, **re-run replaces history**, **stream observes a run started after connect**).

## Evidence

- `pytest tests/api/test_walkforward_sse.py` — 5/5 green; full backend suite green (1330 passed, 2 skipped at phase gate).
- Frontend `tsc -b` + `vite build` clean; browser-verified live cycle: idle "未运行" → 运行前推 → progress → 已完成 → re-run streams again.
- Zero-execution-UI grep gate == 0; SSE only refreshes read panels — no SSE-driven write path.

## Deviations / polish fixes (post-commit)

1. **Idle chip lied ("运行中 · 折 1/0"):** `es.onopen` flipped status to running with zero evidence. Fixed — status is claimed only on a real progress event.
2. **Re-run never streamed:** POST run on a completed job appended history after the first `done`; every stream client closes at the first `done`, so re-runs were invisible and reconnects replayed stale history. Fixed — a fresh run REPLACES the recorded history (reset before recording).
3. **Per-stream placeholder missed late runs:** a stream connected before a run held a local job copy the run never wrote to. Fixed — idle placeholder jobs are registered under the shared key; streams always observe the same object; idle placeholders TTL-clean after 5 min.
4. **Frontend stream closed after done:** the `done` handler closed the EventSource, so a UI-initiated re-run had no listener (button stuck "运行中…"). Fixed — `start()` reopens the stream after a successful POST when the previous stream closed (reopen AFTER the POST so replay carries the fresh run).
