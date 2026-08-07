# Requirements: AthenaQuant v2.4 全量数据解锁

**Defined:** 2026-08-07
**Core Value:** An investor can turn reliable market data and their own holdings into an auditable, actionable research and monitoring workflow without operating multiple disconnected tools.

## v2.4 Requirements

Requirements for the v2.4 milestone. Each maps to a roadmap phase. Research basis: `.planning/research/v2.4-full-universe/SUMMARY.md` (full-universe auction backfill FEASIBLE — measured 0.96s/request, 3.5-5.5h, BJ 333 upstream-empty → 94.0% ceiling; real-column rerun is a 2.3s compute but run_id fingerprint misses lake coverage; BT-10 minute wiring is pure-code sandbox-implementable; D8 stale container proven, build+boot preflight sandbox-executable). Cross-cutting guards: zero new runtime deps, honest provenance (`empty_response` ledger / `rows_present < expected` partial framing / coverage ≤94.0% never claimed 100%), POOL-03 zero-execution AST guard, user `Watchlist.tsx` zero-touch.

### 全量竞价回填 (Full-Universe Auction Backfill) — Phase 36

- [ ] **FA-01**: Long-job timeout exemption — `job_store.create(timeout_s=...)` persists a per-job timeout; `reap_stale()` honors `j.get("timeout_s", STALE_JOB_TIMEOUT_S)`; the auction backfill API passes `timeout_s=21600` (6h). A backfill job running past the old 600s ceiling is no longer reaped mid-run (regression test: fake job older than 600s with `timeout_s=21600` survives `reap_stale`; the 600s self-kill trap at `STALE_JOB_TIMEOUT_S` + cooperative-cancel break is closed).
- [ ] **FA-02**: Resume/only-missing — `run_auction_backfill(only_missing=True)` pre-scans `kline_auction` coverage over the aligned date set (`SELECT symbol, COUNT(*) … GROUP BY symbol`, mirroring `_lake_distinct_symbols`); fully-covered symbols are skipped; partial coverage (interrupted residue) is re-fetched; the API body accepts `only_missing`; idempotent merge-upsert semantics preserved.
- [ ] **FA-03**: Operator CLI `backend/scripts/auction_backfill.py` — mirrors `scripts/auction_backtest.py` conventions: `--symbols|--all`, `--start`, `--end`, `--rpm`, `--only-missing`; job_id=None → no job_store (no reap/single-flight); per-symbol progress to stdout; terminal dict (8 keys, failure + `failed_symbols` ledger) written to a JSON file; detached full-universe run carrier.
- [ ] **FA-04**: Sandbox full-universe run — detached CLI executes the full 5537-symbol × 248-day backfill (3.5-5.5h observed); acceptance: backfilled_symbols ≥ 5200 (SZ/SH 5204; BJ 333 honestly recorded as `empty_response`), rows ≈ 1,290,592, lake = 248 partitions × ~5204 rows, no `.tmp` residue; cross-check sampled `auction_virtual_price` == `kline_daily.open` (≥3 dates, ≥3 symbols); top-up via `--only-missing` until stable.
- [ ] **FA-05**: BJ honest ceiling — all 333 BJ symbols (920xxx) upstream-empty are recorded in `failed_symbols` with reason `empty_response` (never retried-forever, never fabricated); coverage reported ≤ 94.0% honestly (never claimed 100%); documentation stance records the 5 alternative code formats tested and the upstream gap.
- [ ] **FA-06** (P2): EOD interplay regression — after the full backfill, EOD `sync_and_persist_auction` for covered symbols is an idempotent no-op crop (re-write leaves lake row count unchanged); cross-process write discipline documented (backfill scheduled outside the EOD run_all window; in-process run-slot serialization unchanged).

### 全量真列回测重跑 (Full Real-Column Backtest Rerun) — Phase 37

- [ ] **RC-01**: run_id lake-coverage fingerprint — `_compute_run_id` (auction_backtest.py:614-640) includes a lake coverage digest (e.g. `auction_symbol_count` + `len(auction_enabled_dates)`); same inputs + different lake coverage → different run_id; same lake → still idempotent `reused=True`. Regression test extends `test_full_backtest_deterministic_run_id_idempotent` (same input + coverage change → fresh run_id; same coverage → reused).
- [ ] **RC-02**: Full-market real-column rerun — CLI full-market 248-day run post-backfill: `coverage.symbols` flips from 0.036% to ≥ 0.94 (auction_symbol_count ≈ 5204/5537); the 4 auction-column-gated strategies (fast_grab/allround/t1_flash/alpha) real-branch hits grow 12 → thousands+; EOD 4 strategies hits unchanged (329,087); `auction_intraday_confirm` hits unchanged (52,591, filter consumes no auction columns by design); total runtime ≤ 10s measured.
- [ ] **RC-03**: Honest coverage reporting — `rows_present < expected` shown as honest partial (no interpolation); coverage ratio framed as backfilled/5537; intraday_confirm annotated in the run summary as `branch=real` without auction-column consumption (BT-10 note, semantics never silently changed); BT-04 forward formulas and `n_missing_outcomes` counting unchanged (verifier spot-check to 9dp).
- [ ] **RC-04** (P2): Persistence & read-only surface at scale — `backtest_results` run_id directories (40-60 万行 part.parquet) queryable via `GET /api/research/backtest/{run_id}`; `--force` escape hatch bypassing the fingerprint check for operator reruns; AST guard E3 (mirror `test_pool_hub`) still green.

### 分钟确认接线 BT-10 (Minute Confirm Wiring) — Phase 38

- [ ] **MN-01**: `make_minute_loader(data_dir)` factory — reads `kline_minute/date={as_of}/part.parquet` canonical columns, filters candidate symbols, sorts; missing partition → empty frame (fail-closed, no exception masking).
- [ ] **MN-02**: Both construction sites wired — `main.py:562-565` (app engine) and `advanced/governed_runner.py:63-66` (research runner) pass `minute_loader`; empty-lake behavior byte-identical to today (required-strategy → empty StrategyResult; optional → confirm skipped, core daily pool kept).
- [ ] **MN-03**: Hermetic tests — production factory + fixture partitions: empty-lake behavior-keep; partition-present lights `auction_intraday_confirm` with single-point truncation `datetime.time() <= evaluation_time` (T-21-01: no input after confirmation moment); loader read-only (zero writes to `kline_minute`); research/validation reports keep `minute_confirm='not_applied'`.
- [ ] **MN-04** (P2): Documentation sync — one status line in docs/features.md + docs/deploy-verification.md: wiring live in sandbox, lighting requires live-day lake writes (post-sync 15:30/manual, NOT intraday 09:45 — honest fail-closed).

### 部署验证与残留 (Deploy Verification & Residue) — Phase 39

- [ ] **DV-01**: D8 deploy-recipe preflight — `docker build` from repo HEAD + fresh container boot smoke on a scratch port (e.g. 3020) with a temp data dir: container boots, new endpoints present (auction backfill/backtest read-only/validation available), md5 parity vs the stale 3018 container documented; proves the rebuild recipe without touching the running stale container.
- [ ] **DV-02**: Deploy checklist v2.4 refresh — docs/deploy-verification.md updated with measured facts (pilot latencies, full-backfill runtime + coverage 94%, container diff evidence, minute wiring status); `.planning` research ↔ docs parity check maintained (no `## ` header drift, content preserved).
- [ ] **DV-03** (P2): Honest gap summary — consolidated gap doc: `premarket_results` double-gate (deploy + live 09:15-09:25 data), BJ upstream gap, minute live-day gate, AI-key default-off; each with evidence, owner, and trigger condition.
- [ ] **DV-04** (P2): Observation-window plan — D1..D8 post-deploy execution calendar (which trading day each item opens; sequencing D4 after D1, D5 after D2, D7 at ≥5th trading day; D8 at rebuild) — the operator's schedule, not sandbox work.

---

## Traceability

| Phase | Requirement | Status |
|-------|-------------|--------|
| 36. 全量竞价回填 | FA-01 | Complete |
| 36. 全量竞价回填 | FA-02 | Complete |
| 36. 全量竞价回填 | FA-03 | Complete |
| 36. 全量竞价回填 | FA-04 | Deferred (source-gated) |
| 36. 全量竞价回填 | FA-05 | Complete |
| 36. 全量竞价回填 | FA-06 | Complete |
| 37. 全量真列回测重跑 | RC-01 | Planned |
| 37. 全量真列回测重跑 | RC-02 | Planned |
| 37. 全量真列回测重跑 | RC-03 | Planned |
| 37. 全量真列回测重跑 | RC-04 | Planned |
| 38. 分钟确认接线 BT-10 | MN-01 | Planned |
| 38. 分钟确认接线 BT-10 | MN-02 | Planned |
| 38. 分钟确认接线 BT-10 | MN-03 | Planned |
| 38. 分钟确认接线 BT-10 | MN-04 | Planned |
| 39. 部署验证与残留 | DV-01 | Planned |
| 39. 部署验证与残留 | DV-02 | Planned |
| 39. 部署验证与残留 | DV-03 | Planned |
| 39. 部署验证与残留 | DV-04 | Planned |

**Cross-cutting guards (apply to every phase):** zero new runtime dependencies · honest provenance (`empty_response` ledger, coverage ≤94.0% never claimed 100%, `rows_present < expected` partial framing) · POOL-03 zero-execution AST guard · `strategy_cache` single-as_of integrity · user `frontend/src/pages/Watchlist.tsx` never touched · no backfill forgery (upstream-limited items documented, not fabricated).
