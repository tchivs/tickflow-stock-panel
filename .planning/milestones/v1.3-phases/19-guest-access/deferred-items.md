# Deferred Items — Phase 19

## Out-of-scope discoveries (logged per executor scope boundary)

- **`backend/tests/advanced/test_production_host.py::test_spawned_governed_backtest_completes_split_evidence_within_budget`**
  Failed in the full-suite run with `AssertionError: 'resource_limited' == 'completed'` (1414 passed, 1 failed, 2 skipped).
  This is an advanced-sandbox governed-backtest resource-budget test, entirely unrelated to the guest
  masking (GUEST-01/02) changes in 19-01 (pool.py / pool_hub.py / main.py guest branch / guest_masking.py).
  The executor scope boundary prohibits fixing pre-existing failures in unrelated files.
  Re-run to confirm flakiness before /gsd-ship.
