# 37-03 SUMMARY — RC-04 `--force` + 只读 API 全规模 + 文档 + 阶段收口

**Phase**: 37 全量真列回测重跑 — wave 3 (with 37-01 `65426a3`, 37-02 `caecaf4`+`43211ca`, 37-03 `961141e`; this doc + docs/features.md in the 37-03 docs commit)
**Closed**: 2026-08-07
**Single handoff doc** for closing Phase 37. All numbers measured (RUN-EVIDENCE-37-02.md is the single evidence source; at-scale API evidence appended there as §9).

---

## 1. Verdict

**RC-01..04 all met**, with the ROADMAP goal-text deviation annotated honestly:

| Req | Verdict | Summary |
|---|---|---|
| RC-01 | **MET** | run_id lake-coverage fingerprint: digest `(auction_symbol_count, len(auction_enabled_dates))` in `_compute_run_id`; same command + lake change → fresh run_id; same lake → idempotent `reused=True` (measured on real lake, Run-2). |
| RC-02 | **MET (honest current-lake form)** | Full-market rerun on the current lake: coverage 0.036% → **0.67%** (37/5537), rows_present 496 → 8,951, gated-4 hits **12 → 720 [measured]**, EOD 329,087 **unchanged**, intraday 52,591 **unchanged**, runtime **5.2s wall (≤10s)**. **Deviation**: ROADMAP success criterion #2 assumed FA-04 completed the 5204-symbol backfill (≥0.94); FA-04 is source-gated (upstream 403) → this phase's rerun is the honest current-lake rerun; the ≥0.94 full-coverage rerun is a documented **post-recovery operator command** (5-10s, zero new code). Never interpolated, never claimed ≥0.94. |
| RC-03 | **MET** | `rows_present 8,951 < expected 1,373,176` honest partial, backfilled/5537 framing; intraday_confirm annotated `branch=real` with no auction-column consumption (manifest `minute_note` + CLI summary); BT-04 formulas + `n_missing_outcomes` verified to 9dp (spot-check PASS). |
| RC-04 (P2) | **MET** | `--force` CLI escape hatch (bypasses fingerprint check; `rewritten_at` provenance on the force path only); read-only API serves the 382,398-row part.parquet at scale (sub-second measured); AST guard E3 (+siblings) green; docs + SUMMARY updated. |

## 2. Delivered code

- **RC-01** (37-01 `65426a3`): `_lake_auction_symbol_count` read-only helper (mirrors `_coverage_symbols` partition-scan verbatim → zero view-vs-scan drift); `_compute_run_id` gains keyword-only `lake_digest: tuple[int, int] | None = None` (None → pre-fix blob, backward compatible; appended as `|lake:{n}:{m}`); run-time wiring in `run_full_backtest` (step ⑤-1); manifest fingerprint gains `lake_coverage` member.
- **RC-03** (37-02 `caecaf4`): manifest `_MINUTE_NOTE` + CLI `_print_summary` carry the intraday_confirm no-auction-column annotation ("日线初筛仅消费 open_gap … hits 不随湖覆盖增长 (52,591 恒定)"); CLI docstring W4 reword.
- **RC-04** (37-03 `961141e`): `run_full_backtest` + `_persist_run` gain keyword-only `force: bool = False`; on fingerprint match with force, the idempotent early-return is bypassed and the run is rewritten with `manifest["rewritten_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")` (provenance, **only** on the force path — exact key-set contract unchanged); CLI `--force` flag (after `--rpm`) passes through; zero API surface (GET-only guard untouched); writes via existing `_atomic_write_*` into `_BACKTEST_ROOT`-derived run_dir (E2 safe).

## 3. Test evidence

| Command | Result |
|---|---|
| `pytest tests/test_auction_backtest.py -k "run_id" -q` (37-01) | **2 passed** (extended idempotency + digest unit) |
| `pytest tests/test_auction_backtest.py -k "minute_annotation" -q` (37-02 T1) | green; manifest key-set exact-equality green |
| `pytest tests/test_auction_backtest.py -k "force or cli" -q` (37-03 T3) | **2 passed** (force rewrite semantics + CLI pass-through, W1 ok-shaped fake) |
| `pytest tests/test_auction_backtest.py -q` (full) | **9 passed** |
| `pytest tests/test_research_backtest_guard.py -q` (T5) | **7 passed** (E1/E2/E3/GET-only/whitelist/no-execution) |
| `pytest tests/test_research_backtest_api.py -q` | **4 passed** |
| `pytest tests/test_pool_hub.py -k "no_strategy_cache or no_execution or get_only or writes_only" -q` (T5) | **4 passed** (E3 mirror subset; W2: `no_strategy_cache` clause selects nothing in pool_hub — real E3 coverage is `test_backtest_no_strategy_cache_reference` in the guard file) |
| Pre-rerun batch (37-02 §8) | **18 passed** (backtest + guard + api) |
| Post-37-03 batch (belt-and-braces) | backtest 9 + guard 7 + api 4 = **20 passed** (verified by 37-02 re-check on `961141e`) |

## 4. Run evidence (from RUN-EVIDENCE-37-02.md, all measured 2026-08-07)

- **Fresh run**: `298d743e8083` (≠ pre-fix `1cbb901a5637` — RC-01 digest flips identity by design; `wrote=True`, `reused=False`); manifest fingerprint `lake_coverage: [37, 248]`.
- **Coverage**: `auction_symbol_count` **37**/5537 (**0.67%**), `symbol_coverage_ratio` 0.006682318945277226; `auction_rows_present` **8,951** / `auction_rows_expected` 1,373,176 → **honest partial** (never ≥0.94, never 100%).
- **Gated-4 real hits**: 12 → **720** (allround 214 / alpha 336 / fast_grab 31 / t1_flash 139) [measured].
- **EOD 4 strategies**: **329,087 unchanged** (32,686 + 203,221 + 11,926 + 81,254) — equals Run A `be4ce9bc038b`.
- **auction_intraday_confirm**: **52,591 unchanged** (branch=real; filter consumes only `open_gap`, intraday_confirm.py:38-43) — equals `1cbb901a5637`.
- **Runtime**: in-script 2.4s / wall **5.235s** (Run 1); ≤10s criterion PASS.
- **Idempotency (Run 2)**: same run_id, `status="reused"`, wrote=False/reused=True, part.parquet mtime + size **unchanged**.
- **9dp spot-check (BT-04)**: 12 rows × 3 dates × 4 symbols recomputed from `kline_daily` + global calendar — worst diff **0.0 < 1e-9** → PASS; `n_missing_outcomes` violations **0** (2,969 flagged rows: null formula columns, no (symbol, next-day) row, incl. terminal date 2026-08-05).
- **At-scale API (T4, §9)**: list 200 count=7 incl. fresh run; detail `298d743e8083` 200 n_rows=**382,398** sample=20 per_strategy/per_date sums reconcile; pushdown `?strategy=auction_fast_grab&branch=real` → n_rows=31; `1cbb901a5637` still 200 (381,690); `as_of=bad-date` → 422; `zzz` → 400. Response times: detail **0.052s**, pushdown **0.015s**, old detail 0.039s, list 0.012s (TestClient on real `data/`, no server).

## 5. Anchor corrections (handoff from planning; post-wave drift noted)

| Anchor | Research/patterns said | Correct (handoff, plan-check verified) | Post-wave (2026-08-07, after 37-01/02/03 deltas) |
|---|---|---|---|
| `_coverage_symbols` def | :260 | **:376** | :410 (37-01 inserted `_lake_auction_symbol_count` above it) |
| `_preload_full_enriched` def | :134-157 | **:121** | :128 (37-02 CLI docstring reword + 37-03 `--force` usage line) |
| intraday_confirm filter | :42-45 | **:38-43** | :38-43 (unchanged) |
| `_compute_run_id` def | :614-640 | — | :657 (37-01 digest param + docstring) |
| `_persist_run` def | :712-743 | :712 | :765 (force kwarg + branch, 37-03) |
| Measured lake state | — | 8,951 rows / 37 symbols / 248 partitions | unchanged (verified pre/post rerun) |
| Existing run_ids | — | `be4ce9bc038b` (Run A EOD 329,087 @ coverage 2/5537) · `191642f83b2d` (Run B real 12 @ 2 symbols) · `1cbb901a5637` (9-strategy full market, intraday 52,591, coverage 2/5537) · `45fb75b65731` (50-symbol 2,221 rows) · `0f2b91e93975` / `808be6bb00e1` | all still served via API (7 dirs after rerun) |

## 6. Acceptance table

| Req | Criterion | Evidence |
|---|---|---|
| RC-01 | digest in `_compute_run_id`; same inputs + lake change → fresh run_id; same lake → reused | 37-01 code + tests (2 passed); real-lake Run-2 reused=True (evidence §5) |
| RC-02 | honest current-lake rerun: 0.67%, gated-4 720, EOD/intraday unchanged, ≤10s; ≥0.94 = post-recovery command | evidence §2-§5, §7; docs/features.md 竞价回测节 |
| RC-03 | honest partial (8,951 < 1,373,176); backfilled/5537 framing; intraday annotation; BT-04 9dp | evidence §4, §6, §8; docs/features.md BT-10 节 |
| RC-04 (P2) | `--force` bypass + `rewritten_at` provenance (CLI-only); API serves 382,398-row run at scale; AST guard E3 green | 37-03 `961141e` + force/cli tests (2 passed); evidence §9 (6 calls, sub-second); guard 7 + pool_hub 4 passed |

## 7. Notes for Phase 38/39

- **Phase 38 (分钟确认接线 BT-10)**: `minute_confirm` stays `not_applied` — wiring is Phase 38's `MN-01..04`; the 52,591 intraday hits are daily-prefilter (open_gap-only), unaffected by minute wiring; `kline_minute` remains CLOSED.
- **Phase 39 (部署验证与残留)**: lake at **0.67%** (37/5537) until upstream recovers + Phase 36 FA-04 completes the backfill — the deploy checklist should reference the post-recovery operator command (`cd backend && time .venv/bin/python scripts/auction_backtest.py --range 248`, 5-10s, zero new code) as the full-coverage rerun path; the RC-01 digest guarantees a fresh run_id when it runs.
- **Ops note**: `--force` is the documented escape hatch for same-lake re-rewrites (e.g. operator rerun of the same command to overwrite an identical-fingerprint run) — CLI-only, zero API surface.
