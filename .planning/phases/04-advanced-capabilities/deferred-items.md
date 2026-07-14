# Deferred Items

## 2026-07-12 - Existing Quote Service Ruff Findings

`uv run ruff check backend/app/services/quote_service.py` reports pre-existing whole-file documentation punctuation, import-order, and legacy-style violations outside Plan 04-08's SSE hunk. The focused advanced API lint, compilation, and workflow/SSE test suites pass. Address these separately to avoid mixing unrelated formatting changes with scoped advanced capability work.

## 2026-07-14 - Existing Advanced Experiment Test Failures

The focused Plan 04-22 command continues to fail on two pre-existing assertions outside the provenance work: `test_strategy_backtest_collaborator_derives_split_evidence_from_distinct_governed_windows` expects obsolete split metrics/checksum values, and `test_strategy_backtest_collaborator_prepares_parent_frozen_panels_and_child_consumes_them` calls a missing `prepare()` method. Both failed before Plan 04-22 edits and were left untouched to avoid mixing unrelated runner behavior into the safety fix. The five new binding regressions pass.

## 2026-07-14 - Existing Viewpoint Ruff Findings

`cd backend && uv run ruff check app/advanced/repository.py app/advanced/viewpoints.py tests/advanced/test_viewpoints.py` reports pre-existing import-order violations in `repository.py` and an earlier test-local import block. The Plan 04-25 implementation did not alter either import block; focused viewpoint regression coverage passes.
