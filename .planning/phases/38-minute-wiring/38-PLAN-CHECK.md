# Phase 38 PLAN-CHECK — 分钟确认接线 BT-10 (Minute Confirm Wiring)

**Checked**: 2026-08-07 (PlanCheckerP38, read-only except this file)
**Inputs**: RESEARCH.md, PATTERNS.md, 38-01/02/03-PLAN.md, REQUIREMENTS.md (MN-01..04), ROADMAP.md, live source + tests + real lake
**Verdict**: **EXECUTABLE** — 0 blockers, 8 warnings (1 substantive, 7 minor/execution-detail)

---

## 1. Verdict

No structural blocker. Goal-backward trace MN-01..04 → waves → tasks → files/commands/acceptance is complete and anchored. The seam facts (engine.py:154/163 param+attr, :373-392 branch, dual unwired construction sites main.py:562-565 + governed_runner.py:63-66, 0-partition kline_minute lake) were re-verified verbatim against the live repo this session. The fail-closed factory design, the byte-identical proof method (wired-vs-unwired field comparison + pre/post anchor-batch rerun), the truncation test (real `auction_intraday_confirm` + module-object monkeypatch), the report-semantics freeze (not_applied anchors), and the docs single-line sync are all internally consistent with the code. All plan-filed anchor corrections are accurate.

---

## 2. Blockers

None.

---

## 3. Warnings

| # | Severity | Location | Finding | Fix |
|---|---|---|---|---|
| W1 | **MEDIUM** (automated gate is inert) | 38-03 T4: `git diff docs/features.md docs/deploy-verification.md \| grep -c '^## ' \|\| true` | Diff output lines are prefixed with `+`/`-`/space/`@@` — a line starting with `^## ` **never occurs** in `git diff` output, so the count is unconditionally 0 (or the `\|\| true` fallback) and the "无 header 漂移" gate can never fail. It would report 0 even if a header line WERE added/moved. | Use `grep -c '^[+-]## '` (counts +/- prefixed header lines) or `git diff -U0 ... \| grep '^[+-]## '`. The manual T1 acceptance ("git diff 无 header 行变更") stays as the real backstop. |
| W2 | LOW (execution order can silently neuter T-21-01) | 38-01 T2-3 (monkeypatch + engine) | `minute_confirm_fn` is captured via `getattr(mod, "minute_confirm", None)` at `_load_all()` inside `__init__` (engine.py:260), so the asserting wrapper must be installed **before** `StrategyEngine(...)` is constructed. p2:222-273 orders it correctly (patch → `_engine(...)` → run) and 38-01 mirrors that test — but if the executor constructs the engine first, the assertion never runs and the truncation gate silently passes. | State the ordering explicitly in the executor brief: `monkeypatch.setattr(auction_intraday_confirm, "minute_confirm", asserting)` must precede engine construction; mirror p2:246-249 verbatim. |
| W3 | LOW (fixture thresholds) | 38-01 T2-3 (`result.total == 2`) | With the **real** `auction_intraday_confirm`, confirmation requires cum_volume×time_factor ≥ 10,000,000 (i.e. per-bar ≥ 156,250 over the 4 pre-09:45 bars) AND last_close ≥ first_open; all 3 symbols (incl. 600003) must pass the daily filter (open_gap ≥ 2%) and the daily fixture must carry `auction_volume` (requires_auction_data short-circuit). Low volumes → `keep=[]` → required → total 0, test fails. p2's `_minute_frame` (volume = i×100k → cum 1M × 16 = 16M) satisfies the threshold. | Mirror p2 `_minute_frame`/`_write_minute_partition` (`datetime` cast `Datetime("us")`, volume i×100k) and p2 `_intraday_daily_frame` shape (open_gap 0.03 + auction_volume) exactly; do not invent a low-volume fixture. |
| W4 | LOW (scope note) | 38-02 T1/T2 vs `scripts/probe_phase13.py:59-62` | A third `StrategyEngine` construction site exists (probe_phase13.py:59-62) that stays `minute_loader=None`. This matches MN-02's named scope exactly (main.py + governed_runner) and None → identical fail-closed, so it is correct as planned — flag only for awareness: the 38-02 structure gates lock exactly the two named sites and will not catch a future "wire all sites" refactor touching the probe. | No action; document in 38-03 SUMMARY that probe_phase13 stays unwired by design. |
| W5 | LOW (baseline durability) | 38-01 T3 acceptance ("写入 38-01-SUMMARY.md (无此文件则 T3 内联在 38-01 计划执行记录)") | The MN-02 byte-identical proof (38-02 T5: "复跑同命令同通过数") depends on a durable exact pass-count record from 38-01. The conditional phrasing invites skipping the artifact. | Make recording mandatory regardless of whether a SUMMARY file exists: write test names + per-command pass counts into a durable file under `.planning/phases/38-minute-wiring/` (e.g. `38-01-ANCHOR-BASELINE.md`), referenced by 38-02 T5. |
| W6 | LOW (untested branch) | 38-01 T1 factory corrupt-partition path | The `logger.warning + empty frame` fail-closed branch (read raises → warning → `_empty_minute_frame()`) has no dedicated test — T2-6 covers only the missing-partition path. The "no exception masking" claim rests on code inspection. | Optional: add a corrupt-file test (write non-parquet bytes at `kline_minute/date={d}/part.parquet` → loader returns empty, does not raise, `caplog` shows the warning). Not required by MN-01 acceptance. |
| W7 | LOW (proof completeness nit) | 38-02 T4 field set | Byte-identical comparison covers `strategy_id`/`total`/`rows`/`scores` (elapsed_ms excluded). `as_of` is identical by construction (same date passed to both engines) but is not in the comparison set. | Optionally add `as_of` to the asserted fields — zero cost, airtight proof. |
| W8 | LOW (line-drift nits) | RESEARCH/PATTERNS vs source | RESEARCH cites family.py:59-62 helpers (actual: `_write_strategy` :45-51, `_minute_partition_dir` :54-58 — plan's own "镜像 :31-62" range is correct); auction_backtest.py:66-71 `_MINUTE_NOTE` (actual `_MINUTE_CONFIRM` :66 ✓, `_MINUTE_NOTE` :67-73); kline_sync `CANONICAL_MINUTE_COLS` :535-537 (actual :535-538). None affect implementation. | No action. |

---

## 4. Anchor verification (all re-read live this session)

| Anchor | Claimed | Verified |
|---|---|---|
| engine.py `minute_loader` param / attr | :154 / :163 | :154 / :163 ✓ (param type `Callable[[list[str], date], pl.DataFrame] \| None` matches PATTERNS factory signature contract) |
| engine.py minute branch | :373-392 | :373-392 ✓ — :375-377 None/empty-candidates → required empty StrategyResult; :379 loader call; :380-384 empty frame → required empty / optional skip; :385-387 truncation `pl.col("datetime").dt.time() <= s.evaluation_time`; :388 `minute_confirm_fn(truncated, params)`; :389-392 keep + required-empty |
| main.py construction site | :562-565 | :562-565 ✓ (3 kwargs, no minute_loader yet; `store.data_dir` already in scope at :559-560 — wiring value valid); local import block :551-553 (ScreenerService/StrategyEngine/StrategyMonitorService) — insertion point after monitor import is free |
| governed_runner.py `_service()` / site | :59-66 | :49-72 `_service()` ✓; `data_dir = Path(self._data_dir)` :59; `store = DataStore(data_dir)` :60; `StrategyEngine(` :63-66 ✓ (no minute_loader yet); all imports local inside `_service()` :50-54 ✓ |
| kline_sync `CANONICAL_MINUTE_COLS` | :535-537 | :535-538 ✓ (`["symbol","datetime","open","high","low","close","volume","amount"]`) |
| kline_sync partition write path | :899 | :899 ✓ (`data_dir / "kline_minute" / f"date={trade_date}" / "part.parquet"` — matches factory read path) |
| auction_validation.py hardcode | :434 | :434 ✓ `"minute_confirm": "not_applied",` (report path zero-touches minute layer) |
| auction_backtest.py hardcode | :66 | `_MINUTE_CONFIRM = "not_applied"` :66 ✓; `_MINUTE_NOTE` :67-73 |
| family.py `_engine` helper | :31-39 | :31-39 ✓ (`minute_loader` kwarg passthrough); `_run_auction` :41-44; `_write_strategy` :45-51; `_minute_partition_dir` :54-58 |
| family.py anchor tests | :70/102/176/199 | `test_engine_short_circuit` :70 ✓, `test_minute_truncation_no_future` :102 ✓, `test_time_window_default_and_validation` :176 ✓, `test_missing_minute_required_fail_closed` :199 ✓; inline loader + 600003-drop pattern :139-175 ✓ (T2-3 mirrors) |
| p2 anchor tests | :222/252/269 | `test_intraday_truncation` :222 ✓, `test_time_factor` :252 ✓, `test_intraday_minute_absent_empty` :269 ✓; monkeypatch-before-engine ordering :225-248 ✓; `_minute_frame` volume i×100k :55-79 ✓ (satisfies real confirm threshold) |
| backtest anchor | :455 | `test_full_backtest_minute_annotation_and_manifest` :455 ✓ |
| validation_report anchors | :159/564/1054/794 | :159 ✓ / :564 ✓ / :1054 ✓ / :794 ✓ (all four `-k` clauses collect exactly these) |
| test_minute_sync_verify.py | — | exists; `_synthetic_minute_frame` casts `datetime` `Datetime("us")` :1-32 ✓ (T2 fixture mirrors) |
| structure gates | — | test_auction_backfill.py `_main_src()` :658-667 ✓ (substring asserts, unaffected by an added import line); test_auction_history.py main.py gate :324-329 ✓; test_concept_history.py write-pattern grep :637-641 ✓ |
| governed_runner spawn-serializability | — | tests/advanced/test_experiments.py:66-72 pickle test ✓ — covers the "import stays in `_service()`" requirement |
| features.md BT-10 bullet | :89 | :89 ✓ — ends verbatim "**全量分钟 248 日回填 CLOSED**（BT-10 P2 验收 = 注解诚实，非实现分钟）。" (38-03 T1 append point matches) |
| deploy-verification.md D8 | :170 | `## D8 — 信息项（无 action，仅确认立场）` :170 ✓; bullets OQ-1/WATCH-04/BT-07 :172-174 (append point after :174, before `---` :176); timing table :182-189 untouched by plan ✓ |
| kline_minute lake | 0 partitions | `data/kline_minute/` exists, **zero** `date=*` subdirs ✓ (RESEARCH "0 分区" claim exact) |

## 5. Live cross-checks (this session, read-only)

- **Byte-identical soundness (MN-02 core)**: unwired `minute_loader=None` → engine :375-377 skips loader, required → `StrategyResult(as_of, strategy_id)`; wired factory on empty lake → :379 loader returns canonical-cols empty frame → :380 `is_empty()` → :382-383 same required/optional split. Both paths converge on identical outputs for required (total 0 / rows [] / scores {}) and optional (full scoring on the same daily pool). The 38-02 T4 comparison set (strategy_id/total/rows/scores, elapsed_ms excluded) is valid; missing-partition state (lake has `date={other}`, target absent) exercises the same factory empty path — sound.
- **No `minute_loader` anywhere in main.py / governed_runner.py today** (grep: zero hits) — "双未接线" claim exact; no stale partial wiring to conflict with.
- **Strategy loader is per-engine fresh**: `_load_file` uses `module_from_spec` + `exec_module` (engine.py:180-190) without sys.modules caching → two engines on the same strategy dir (38-02 T4) get independent module objects; `minute_confirm_fn` bound per engine at `__init__` — confirms W2 ordering requirement and T4's two-engine comparison safety.
- **Existing main.py structure gates are substring-based** (backfill :663-667, history :327-329) — adding one constructor kwarg + one local import cannot break them; no test asserts the absence of `minute_loader` in either construction site.
- **Anchor `-k` filters collect exactly the intended tests** (verified all 10 named test defs exist at the cited lines); extra substring matches would only be additive and both waves rerun identical commands, keeping counts comparable.
- **Factory import chain is side-effect-free**: `minute_loader.py` → `kline_sync` → `preferences` (import-safe, defers settings to `_path()` call time) / `indicators.pipeline` / `tickflow.client`; all already imported by the app factory (main.py:126,627) and by scripts today. Local import inside `_service()` runs in the spawned worker — consistent with the DuckDB-singleton convention; pickle test (test_experiments.py:66-72) only serializes `_data_dir`.
- **Report freeze structurally guaranteed**: wiring touches only engine constructor args; `auction_validation.py:434` and `auction_backtest.py:66` are hardcoded report paths with zero dependency on the engine's minute branch — the not_applied anchor reruns (38-02 T5 cmd 4/5) are the proof, and governed_runner's wired engine on an empty lake yields the same strategy results as `minute_loader=None`.

## 6. Per-MN coverage

| Req | Criterion (goal-backward) | Where in plans | Verdict |
|---|---|---|---|
| MN-01 | `make_minute_loader(data_dir)` factory: canonical-cols partition read, candidate filter, sort; missing partition → empty frame (fail-closed, no exception masking) | 38-01 T1 (new module, contract docstring, corrupt→warning+empty), T2-5 (filter/sort), T2-6 (missing partition) | COVERED — fail-closed on missing AND corrupt (warning visible, not silent); signature matches engine param type |
| MN-02 | Both construction sites wired (main.py:562-565 + governed_runner.py:63-66); empty-lake byte-identical (required → empty StrategyResult; optional → confirm skipped, core daily pool kept) | 38-02 T1/T2 (wiring, local imports), T3 (structure gates), T4 (wired-vs-unwired field equality incl. missing-partition state, elapsed_ms excluded), T5 (pre/post anchor batch identical counts) | COVERED — proof layered (direct field comparison + anchor rerun); W5/W7 are recording/comparison-set nits |
| MN-03 | Hermetic tests: empty-lake behavior-keep; partition-present lights `auction_intraday_confirm` with single-point truncation ≤ evaluation_time (T-21-01); loader read-only (zero writes); reports keep `minute_confirm='not_applied'` | 38-01 T2-1/2 (empty required/optional), T2-3 (real confirm + monkeypatch + truncation), T2-4 (sha256/mtime snapshot + empty-state no-dir-created), T2-7 (module no-write structure gate), T3 (anchor baseline), 38-02 T5 (rerun + not_applied anchors) | COVERED — W2 (patch-before-engine order), W3 (fixture thresholds), W6 (corrupt-path test optional) |
| MN-04 (P2) | One status line in features.md + deploy-verification.md; lighting requires live-day lake writes (post-sync 15:30/manual, NOT intraday 09:45 — honest fail-closed) | 38-03 T1 (BT-10 bullet inline append, verbatim-matched anchor), T2 (D8 one bullet, timing table untouched), T3 (38-03-SUMMARY.md 5 sections), T4 (diff-scope + header check) | COVERED — W1 (header-drift grep command is vacuous; fix to `^[+-]## `) |

## 7. Notes for the executor

- Land 38-01 first (38-02/38-03 depend on factory + tests + baseline). Never touch `frontend/src/pages/Watchlist.tsx`; engine.py, auction_backtest.py, auction_validation.py, backtest_results stay zero-change.
- 38-01 T2-3: install the `minute_confirm` monkeypatch **before** constructing the engine (W2); feed the raw untruncated frame to the wrapper first (`pytest.raises(AssertionError)`) to prove the gate, then run through the engine; use p2-style volumes (i×100k) and the `_intraday_daily_frame` shape incl. `auction_volume` (W3).
- 38-01 T3: record test names + per-command pass counts durably even if no SUMMARY file is created (W5) — 38-02 T5's byte-identical proof reads it.
- 38-03 T4: use `grep -c '^[+-]## '` for the header-drift gate, not `'^## '` (W1).
- Full-suite regression (38-02 T6) is the backstop for the governed_runner import chain and the spawn-serializability test; kline_sync's import chain is side-effect-free and already exercised by the app factory, so no surprise there.
