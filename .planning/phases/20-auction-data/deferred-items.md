# Deferred Items — Phase 20 (竞价数据层)

## Known Failures / Flakes (pre-existing, unrelated to Phase 20)

| Item | Status | Notes |
|------|--------|-------|
| `backend/tests/portfolio/test_optimizer.py::test_nan_covariance_records_failed_run` | flaky | NaN covariance floating-point; passes in isolation (1 passed, 5 warnings), fails intermittently in the full 1439-test suite (`resource_limited` diff). Pre-existing Phase 11/12 optimizer code — zero Phase 20 touchpoints (auction/screener). Tracked; not a Phase 20 regression. |

## Deferred to Later Phases

| Category | Item | Phase |
|----------|------|-------|
| Feature | Data page 竞价列可用性 section UI rendering (real vs derived columns, unit labels 股/元) | Phase 23 (frontend) |
| Feature | 竞价湖覆盖 {N} 天 单复数文案 + 0 天不渲染为可用 | Phase 23 (frontend) |
| Feature | fail-closed 长文案换行 / probe 面板视觉回归 | Phase 23 (frontend) |
