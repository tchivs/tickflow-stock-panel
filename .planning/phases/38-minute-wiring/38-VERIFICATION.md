---
phase: 38-minute-wiring
verified: 2026-08-07T10:30:00Z
status: passed
score: 4/4 MN requirements — MN-01/02/03/04 verified (real lighting is deploy-gated by a live-day lake write, see behavior_unverified)
behavior_unverified: 1 — real lighting observation (kline_minute partition present for a live day + auction_intraday_confirm non-empty hits) NOT observable in sandbox: the minute lake currently has 0 partitions, so the wired runtime path exercised and proven byte-identical is the empty-lake fail-closed form (required → empty pool / optional → confirm skipped). Genuine lighting requires a live trading day's post-sync lake write (15:30 EOD pipeline or manual sync) and is a deploy-side observation recorded in deploy-verification.md D8
overrides_applied: 0 — no REQUIREMENTS.md/ROADMAP.md text changed; MN-01..04 delivered as written (W6 corrupt-partition fail-closed added as a bonus test beyond the 7 planned)
human_verification: 3 items (deploy-day lighting observation, probe_phase13 third construction site unwired by design, BT-10 minute-history CLOSED stance) — sandbox cannot assert; labeled deploy-verified per standing policy
---

# Phase 38 Verification — 分钟确认接线 BT-10 (MN-01..04)

**Verifier:** VerifierP38 · **Date:** 2026-08-07 · **Scope:** `.planning/REQUIREMENTS.md` MN-01..04 (Phase 38) — make_minute_loader factory, dual construction-site wiring, hermetic behavior-keep/lighting/read-only tests, P2 doc sync.
**Method:** Goal-backward, behavior-level — 4-file pytest batch (42 passed, reproduced exactly) + code-level file:line evidence + guard-rail checks (imports/deps/zero-touch surfaces) + cross-check of the 3 executor commits (4380545 / 2f8629e / a78173b) via `git log --name-only` + anchor rerun of the 38-01-BASELINE.md 5 commands (16 passed, byte-identical to pre-wiring). All claims re-derived by this verifier, not taken from SUMMARY text. **Real lighting remains deploy-gated** (minute lake = 0 partitions) — recorded honestly in `behavior_unverified`, never claimed.

## Verdict: **PASSED**

All four MN requirements verified against code + tests + anchors (MN-01 factory fail-closed read-only, MN-02 dual-site wiring byte-identical on empty lake, MN-03 11 hermetic tests incl. T-21-01 truncation via real `auction_intraday_confirm` + sha256/mtime read-only proof + not_applied anchors, MN-04 honest doc sync). 42 passed, 0 failures; anchor rerun identical (16). The only unobservable acceptance (real lighting) is a live-day lake-write gate with a documented deploy-side observation item — no needs-fix items in code.

---

## 1. Test batch (executor duty 1)

```
cd backend && .venv/bin/python -m pytest tests/test_minute_loader_wiring.py tests/test_auction_strategy_family.py tests/test_auction_strategy_family_p2.py tests/test_minute_sync_verify.py -q
→ 42 passed in 0.87s   (orchestrator claim: 42 passed in 0.94s — reproduced)
```

Per-file collect (42 collected): wiring **11** · family **16** · family_p2 **11** · minute_sync_verify **4**.
- Wiring file = 8 tests from 38-01 (7 planned + W6 corrupt-partition fail-closed) + 3 from 38-02 (2 structure gates + byte-identical proof) = 11.

## 1b. Behavioral summary (goal-backward, per MN)

- **MN-01 — make_minute_loader factory.** `backend/app/services/minute_loader.py` — `make_minute_loader(data_dir)` returns a `(candidates, as_of) -> pl.DataFrame` read-only loader. Reads `kline_minute/date={as_of}/part.parquet` and projects to the canonical column set (`CANONICAL_MINUTE_COLS`, kline_sync.py:535-538); filters candidates via `is_in`; sorts `["symbol","datetime"]`; missing partition → empty frame with canonical columns (deterministic, no raise); corrupt partition → `logger.warning` + empty frame (fail-closed, not silent); empty frame returned as-is. Zero write surface (constructive: only `exists`/`read_parquet`/`filter`/`sort`/`select` — structure-gated). Imports: stdlib `logging`/`datetime`/`pathlib` + pre-existing `polars` + kline_sync constant only — no new deps.
- **MN-02 — dual-site wiring.** `main.py:551` local `from app.services.minute_loader import make_minute_loader` (function-body, same shape as the ScreenerService local import) + `main.py:567` `minute_loader=make_minute_loader(store.data_dir)` on the `StrategyEngine(...)` call. `governed_runner.py:55` same local import **inside `_service()`** (indent > 0; module top level gains zero imports — structure-gated) + `:72` `minute_loader=make_minute_loader(data_dir)` (`data_dir = Path(self._data_dir)` already in scope at `:59`). Engine seam untouched (engine.py:154 param / :163 store / :375-379 consume). Empty-lake behavior byte-identical to `minute_loader=None` (per-field: `as_of`/`strategy_id`/`total`/`rows`/`scores`, `elapsed_ms` excluded) across required+optional strategies and the missing-partition state.
- **MN-03 — hermetic tests.** 11 tests in `tests/test_minute_loader_wiring.py`: empty-lake required → empty StrategyResult (byte-equal to None baseline); optional → confirm skipped, daily core pool kept (total==2, minute_confirm would have emptied it); partition present → real `auction_intraday_confirm` lights + single-point truncation `datetime.time() <= 09:45` (T-21-01) — assertion wrapper patched **before** engine construction (W2), proven live by direct-feed AssertionError then silent through-engine; candidate filter + sort; missing-partition empty (columns == canonical); corrupt-partition warning + empty (W6); read-only sha256+mtime tree snapshot byte-identical + empty-lake creates no directory; module no-write-paths structure gate; main.py/governed_runner.py wiring structure gates; wired-vs-unwired byte-identical proof (2 states).
- **MN-04 (P2) — doc sync.** `docs/features.md` BT-10 bullet +1 inline sentence: dual-site wiring landed (main.py + governed_runner.py, engine.py zero changes), empty-lake byte-identical, lighting precondition = live-day lake write **post-sync (15:30 EOD/manual), 绝非盘中 09:45 即时**. `docs/deploy-verification.md` D8 +1 bullet: post-sync observation item (`kline_minute/date={T}/part.parquet` exists + `auction_intraday_confirm` hits non-empty; empty lake → `total=0` honest pass state, no action). Header drift `^[+-]## ` = 0.

## 2. MN evidence table

| Req | Evidence (file:line) | Test(s) / live check | Result |
|-----|----------------------|----------------------|--------|
| **MN-01** | `minute_loader.py` — `make_minute_loader` factory + `_load` closure (module 50 lines); canonical cols `kline_sync.py:535-538` `CANONICAL_MINUTE_COLS = ["symbol","datetime","open","high","low","close","volume","amount"]`; partition path `data_dir/kline_minute/date={as_of}/part.parquet` matches production write seam; `is_in(candidates)` filter + `sort(["symbol","datetime"])`; missing partition → `_empty_minute_frame()` (`schema=CANONICAL_MINUTE_COLS`, dtype-neutral — engine only consumes `.is_empty()`); corrupt → `logger.warning(...)` + empty frame; zero write calls (`exists`/`read_parquet`/`filter`/`sort`/`select` only) | `test_make_minute_loader_candidate_filter_and_sort` (filter+sort, columns==canonical, height 6) · `test_make_minute_loader_missing_partition_returns_empty` (no raise, columns==canonical) · `test_make_minute_loader_corrupt_partition_fail_closed` (W6: empty + `"fail-closed" in caplog.text`) · `test_make_minute_loader_module_no_write_paths` (9-pattern write-surface structure gate) | **PASS** |
| **MN-02** | `main.py:551` `from app.services.minute_loader import make_minute_loader` + `:567` `minute_loader=make_minute_loader(store.data_dir)` (function-body local import, same shape as ScreenerService) · `governed_runner.py:55` local import inside `_service()` + `:72` `minute_loader=make_minute_loader(data_dir)` (`data_dir` in scope `:59`) · engine seam untouched (`engine.py:154/163/375-379`) | `test_main_wired_minute_loader` + `test_governed_runner_wired_minute_loader` (structure gates; import-line indent > 0 asserted) · `test_wired_empty_lake_byte_identical_to_unwired` (2 states × 2 strategies, per-field equality, `elapsed_ms` excluded; required → total==0/rows==[], optional → total==2) · **anchor rerun**: 5 baseline commands → cmd1 4/12 · cmd2 3/8 · cmd3 4 · cmd4 1/8 · cmd5 4/16 = **16 passed**, byte-identical to 38-01-BASELINE.md | **PASS** |
| **MN-03** | `tests/test_minute_loader_wiring.py` 11 tests — empty/truncate/readonly/minute_loader tokens; `_write_partition` mirrors `_synthetic_minute_frame` (`datetime` cast `Datetime("us")`, volume i×100k → real confirm threshold cum 1M × time_factor 16 ≥ 10M); T-21-01 wrapper patches `auction_intraday_confirm.minute_confirm` **before** engine `__init__` (W2) and the probe strategy re-imports it at exec → wrapper really runs through the engine | `test_make_minute_loader_partition_truncation_lights_confirm` (direct-feed AssertionError proves gate; through-engine silent; 600303 with only 09:50/10:00 bars dropped after truncation → total==2) · `test_make_minute_loader_readonly` (sha256+mtime snapshot equal; no dir created on empty lake) · anchors `backtest:455` + `validation_report:159/564/794/1054` rerun identical (not_applied semantics) | **PASS** |
| **MN-04** (P2) | `docs/features.md:89` BT-10 bullet +1 sentence ("**Phase 38 接线落地（2026-08-07）**… `kline_minute/date={T}/part.parquet` 需在同步后（15:30 EOD 管道或手动同步）落盘，**绝非盘中 09:45 即时**") · `docs/deploy-verification.md:175` D8 bullet +1 ("分钟确认点亮（Phase 38 接线落地）… 同步后…非盘中 09:45…空湖 total=0 为诚实通过态") | `git show a78173b --stat` (docs diff = features.md +1, deploy-verification.md +1, 38-03-SUMMARY +1) · header drift `git show a78173b -- docs/ | grep -c '^[+-]## '` → **0** · wording verified verbatim incl. "绝非盘中" | **PASS** |

## 3. Guard rails (executor duty 3)

- **Zero new module-top-level imports**: `governed_runner.py` top-level = `io/json/multiprocessing/os/signal/time/collections.abc/contextlib/datetime/hashlib/pathlib/queue/typing/resource` — no `minute_loader`; the import lives at `:55` inside `_service()` (indent > 0, structure-gated by `test_governed_runner_wired_minute_loader`). `minute_loader.py` imports only stdlib `logging/datetime/pathlib` + pre-existing `polars` + kline_sync constant.
- **Zero new deps**: no `pyproject.toml`/`requirements.txt`/`uv.lock` in any of the 3 phase-38 commit surfaces (`git log --name-only`: 4380545 → BASELINE.md + minute_loader.py + test file; 2f8629e → governed_runner.py + main.py + test file; a78173b → 38-03-SUMMARY.md + deploy-verification.md + features.md); `git diff 4380545^..a78173b --stat` over pyproject/requirements/uv.lock → empty.
- **engine/backtest/validation zero-touched**: `git diff 4380545^..a78173b --stat -- backend/app/strategy/engine.py backend/app/services/auction_backtest.py backend/app/services/auction_validation.py` → **empty**; report semantics intact (`auction_backtest.py:66 _MINUTE_CONFIRM = "not_applied"`, `auction_validation.py:434` hardcode — both pre-existing, unchanged).
- **Watchlist untouched**: `git status --short` → staged 0, unstaged 1, untracked 0; sole entry `M frontend/src/pages/Watchlist.tsx` (pre-existing user change, never read by this verifier or any executor); zero frontend files in the 3 phase commits.
- **strategy_cache untouched**: absent from all 3 commit surfaces; guard diff over `backend/app/services/strategy_cache.py` → empty.
- **Hermeticity**: all 11 wiring tests use `tmp_path` lakes + real engine + real `auction_intraday_confirm`; live minute lake untouched (0 partitions, verifier re-checked).

## 4. Cross-check claims (executor duty 4)

- **(a) wiring present at the claimed sites** — verifier's own grep: `main.py:551` `from app.services.minute_loader import make_minute_loader`, `main.py:567` `minute_loader=make_minute_loader(store.data_dir)`; `governed_runner.py:55` local import (inside `_service()`, indent > 0), `:72` `minute_loader=make_minute_loader(data_dir)`. Exact lines match the handoff (551/567, 55/72). **PASS**
- **(b) report-semantics files zero-touched** — `git log --name-only` for the 3 commits shows only `.planning/phases/38-minute-wiring/` docs, `backend/app/services/minute_loader.py` (new), `backend/app/main.py`, `backend/app/advanced/governed_runner.py`, `backend/tests/test_minute_loader_wiring.py` (new), `docs/features.md`, `docs/deploy-verification.md` — **no** auction_backtest.py / auction_validation.py / engine.py / strategy_cache.py / frontend. **PASS**
- **Anchor lines unchanged**: `test_full_backtest_minute_annotation_and_manifest` at `tests/test_auction_backtest.py:455`; `test_empty_lake_honest_report_all_9_strategies` :159, `test_per_strategy_coverage_and_minute_confirm` :564, `test_endpoint_forward_stats_branch_minute_confirm` :794, `test_minute_confirm_regression_after_coverage` :1054 — all present, all green in the rerun.
- **Engine seam consumed**: `engine.py:154` `minute_loader` kw-only param, `:163` stored, `:375-379` None-skip vs loader-call branch — the factory plugs exactly into the pre-existing seam.

## 5. SUMMARY cross-checks (executor duty 5)

- All 3 phase-38 commits present and in order: `4380545` (MN-01+MN-03 factory/tests/baseline), `2f8629e` (MN-02 wiring + structure gates + byte-identical proof), `a78173b` (MN-04 docs + 38-03-SUMMARY) — surfaces match claims exactly (docs commit touches only docs).
- "8 用例全绿 (7 计划 + W6 损坏分区 fail-closed 附加)" → reproduced: 8 tests in 38-01 portion (W6 corrupt-partition present at `test_make_minute_loader_corrupt_partition_fail_closed`).
- "11 用例" → reproduced: 11 passed on the wiring file (0.21s).
- "cmd1=4/12, cmd2=3/8, cmd3=4, cmd4=1/8, cmd5=4/16 → 16 passed" → reproduced byte-for-byte (see §1b).
- Orchestrator's "42 passed in 0.94s" → reproduced (0.87s).
- W1 corrected header-drift command (`git diff docs/features.md docs/deploy-verification.md | grep -c '^[+-]## '` → 0) reproduced as `git show a78173b -- docs/ | grep -c '^[+-]## '` → 0 (this verifier's form also covers the SUMMARY file).
- 38-03-SUMMARY line-number claims (main.py:551/567, governed_runner.py:55/72, kline_sync.py:535-538) all confirmed by direct grep.

## 6. Honest boundary (behavior_unverified)

**What is verified**: the entire empty-lake fail-closed contract end-to-end — factory read path (missing/corrupt partition → canonical-column empty frame with warning, deterministic), dual-site wiring (structure-gated), byte-identical wired-vs-unwired behavior (required → empty StrategyResult / optional → confirm skipped, per-field equality across 2 lake states), T-21-01 truncation semantics through the **real** `auction_intraday_confirm` with fixture partitions, read-only guarantees (sha256+mtime), and the not_applied report anchors staying green.

**What is NOT verified (behavior_unverified)**: genuine runtime lighting — a real `kline_minute/date={T}/part.parquet` present for a live trading day feeding `auction_intraday_confirm` non-empty hits. The minute lake currently has **0 partitions** (verifier re-checked: `data/kline_minute` empty), so every exercised production path is the empty-lake form. Cause: minute history is a live-day sync product (15:30 EOD pipeline or manual sync), never a sandbox artifact. The deploy-side observation item is written into deploy-verification.md D8 (post-sync partition existence + confirm hits non-empty; empty lake → `total=0` honest pass state). The phase's committed acceptance is the wiring + behavior-keep proof — delivered; lighting is an operator observation, not a phase deliverable.

## 7. Human items (deploy-verified — not assertable in sandbox)

1. **Deploy-day lighting observation (external gate)**: after a live trading day's 15:30 EOD pipeline (or manual minute sync) writes `data/kline_minute/date={T}/part.parquet`, operator confirms (a) partition exists and (b) `auction_intraday_confirm` produces non-empty hits (engine logs/result); empty lake → `total=0` remains the honest pass state (D8). Sandbox cannot produce a live-day lake write.
2. **probe_phase13.py third construction site unwired by design**: `backend/scripts/probe_phase13.py:59-62` holds a third `StrategyEngine(...)` construction with **no** `minute_loader` argument (verifier re-read) — `None` → the same pre-wiring fail-closed path, behavior correct. MN-02's named scope (main.py + governed_runner.py) is structure-gated only for those two sites; wiring every site is a future refactor needing its own gate. No action required.
3. **BT-10 minute-history CLOSED stance (long-standing)**: `kline_minute` 248-day backfill remains formally CLOSED (features.md AQ-06 / BT-10 bullet: xyz 1m ≈ 21 trading days, ifzq/sina trailing-window only, TickFlow minute tier gated at pro+); BT-10 P2 acceptance = annotation honesty (`minute_confirm:"not_applied"` in backtest rows/reports + `minute_note` provenance), not minute implementation. Phase 38 wires the confirm layer for the sync path without reopening history backfill — consistent with the standing stance.

## 8. Honesty notes

- All PASS evidence is hermetic `[TEST]` or directly re-observed by this verifier: my own 42-test batch run, my own 6-command anchor rerun (16 identical), my own git greps/diffs for every guard, my own reads of the factory/wiring/docs/test source.
- The factory uses `pl.DataFrame(schema=CANONICAL_MINUTE_COLS)` for the empty frame (plan sketched `columns=`; executor used the `schema=` keyword — same dtype-neutral result, engine consumes only `.is_empty()`). No contract drift.
- `docs/features.md` BT-10 bullet is a 1253-char line (long-standing style); the Phase 38 sentence is an in-line append, not a new bullet — matches MN-04's "one status line" acceptance and the +1 diff stat.
- Real lighting is deliberately **not** marked verified; the phase passes on wiring + behavior-keep with the lighting observation recorded in `behavior_unverified` and D8 — matching the standing honesty policy (never present incomplete work as delivered).
