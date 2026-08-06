# Phase 35 Research: 遗留补全与部署验证 (Legacy Completion & Deploy Verification)

**Phase:** 35-legacy-completion · **Requirements:** LG-01..05 (LG-04/05 P2)
**Researched:** 2026-08-06 · **Researcher:** ResearcherP35
**Confidence:** HIGH on R13 test design (fixture shapes verified against 4 existing test files), CHART-04 stance evidence (labels read live), deploy-checklist placement (docs conventions read), WATCH-04 extension (component props + e2e guards read), OQ-3 smoke (script + snapshots verified on disk); MEDIUM on WATCH-04 snapshot churn size (visual diff unknown until run) and OQ-3 row counts (snapshot file present, exact row count from run).

---

## 0. Verdict

All five LG items are implementable now, zero new deps, `Watchlist.tsx` untouched. Two items are PURE DOCS (LG-02 stance, LG-03 checklist placement), one is a deterministic backend test (LG-01), two are P2 sandbox actions (LG-04 frontend+e2e, LG-05 probe smoke).

- **LG-01 (R13)**: recap-side EOD semantics are **already locked** (`test_auction_recap.py` — EOD join at 15:40, pre-EOD omission at 15:10, label discrimination). The actual gap is the **pipeline→refresh recipe**: nothing today calls `_pipeline_then_refresh`/`run_now` (no `test_daily_pipeline*` file exists). New file `backend/tests/test_daily_pipeline_refresh.py`, 3 tests, fixtures reused from `test_pool_eod_job.py`/`test_preopen_scheduling.py`/`test_minute_sync_verify.py`.
- **LG-02 (CHART-04)**: 估算 labels confirmed live at `StockListTable.tsx:319,321,335` + `api.ts:741-742`. Stance goes into **`docs/features.md`** as a new section (feature manual, actively maintained, updated today; ARCHITECTURE.md has zero auction content — skip it).
- **LG-03 (deploy checklist)**: copy into **`docs/deploy-verification.md`** (kebab-case matches docs convention; `DEPLOY-VERIFICATION.md`/`DEPLOY-CHECKLIST.md` deviate). Research-dir copy stays as provenance; cross-link from `docs/deployment.md` + `docs/features.md`.
- **LG-04 (WATCH-04)**: extension = row checkboxes (VIP only) + selection `Set` in PoolHubPage + batch scope = selected; zero backend change (`watchlist.py:35-40` batch endpoint + idempotent `add` at `watchlist.py:37-52`); e2e extends `pool-hub.spec.ts` (fixtures/payloads/guards all live there). **P1 risk: 3 VIP snapshot PNGs will change** (`pool-table-resonance`, `pool-table-filter-active`, `pool-vip-plaintext` — `toHaveScreenshot` at pool-hub.spec.ts:778,784,874) — must be regenerated + reviewed deliberately.
- **LG-05 (OQ-3)**: offline `capture()` is sandbox-runnable (verified: `data/ext_data/{ext_gn_ths,ext_hy_ths}/part.parquet` present, `data/ext_history` absent → first capture creates it, `_write_partition` mkdirs + script `probe_dir.mkdir`). Smoke must use **isolated `DATA_DIR`** (copy `data/ext_data/`) to avoid polluting the real lake. Weekly multi-day report stays deploy-gated (D7).

---

## 1. LG-01 — R13 deterministic regression test

### 1.1 Code facts (verified this session)

- `backend/app/jobs/daily_pipeline.py:1115-1136` — `_pipeline_then_refresh` (cron path): `run_now` inside `qs.paused()` (`:1123-1130`), `repo.refresh_cache()` in `finally` (`:1131-1135`, comment `:1116-1118` = ce5c705/9aa96ed fix). Manual path mirrors: `api/pipeline.py:70-77` (run → `repo.refresh_cache()`).
- `backend/app/tickflow/repository.py:351` `refresh_cache` → `_refresh_enriched` (`:461-577`) loads latest parquet partition into `_enriched_cache`; `_live_agg_baseline_date` at `:770-784`.
- `backend/app/tickflow/repository.py:920-935` `get_enriched_latest_asset("stock")` → cached `(df, cache_date)`.
- Recap read path: `screener.py:243-254` `_load_enriched_for_date` — `cache_date == target_date` → in-memory frame (no re-read); `auction_recap.py:524-530` single-load for Block 2+3.
- pre-EOD rule: `auction_recap.py:339-346` (`as_of==today ∧ now < get_pipeline_schedule()` default 15:30, `preferences.py:329-332`) → Block 3 omits `avg_change_pct`/`close_fulfill_rate`/`up_rate` + `_SIGNAL_NOTE_EOD_PENDING` (`:393-396`); header label `pre_eod` at `auction_recap.py:550-556`.

### 1.2 What tests exist today (how the 15:30 path is exercised)

There are **no `test_daily_pipeline*` files**. The module is tested piecewise, per job function:

| File | Job fn tested | Fixture shape |
|---|---|---|
| `test_pool_eod_job.py:23-97` | `_pool_eod_persist` | `_FakeRepo` (get_enriched_latest_asset/get_instruments_asset/get_enriched_history/enriched_latest_date) + `_make_app_state` (SimpleNamespace repo+strategy_engine) + monkeypatch `daily_pipeline._get_app_state` |
| `test_premarket_pool.py` | `_premarket_pool_preview` | same shape + monkeypatch `cn_today`/`resolve_auction_probe` |
| `test_preopen_scheduling.py:60-84` | 09:26 tail eval | `_make_app_state_with_quoteservice` — **fake qs with `paused()`** (mirrors `qs.paused()` wrap in `_pipeline_then_refresh`) |
| `test_auction_sync.py:281-307` | `_run_auction_sync` stage | real `DataStore`+`KlineRepository` tmp + monkeypatch stage fns + `preferences.save` |
| `test_minute_sync_verify.py:71-110` | pipeline-adjacent write seam | real repo + `repo.append_daily`/`append_enriched` seeding (**closest recipe precedent**) |
| `test_market_recap_delta.py:555-561` | registration-shape | grep gate on `daily_pipeline.py` source |

`run_now` itself is never invoked in tests (network-bound). The 15:30 **scheduler trigger** is never started (sandbox has no cron — `fixture_mode`). So the R13 recipe test targets `_pipeline_then_refresh` directly with stubbed `run_now` — deterministic, no network, no scheduler.

Recap side is **already covered** — do not duplicate:
- `test_auction_recap.py:541-559` `test_signal_quality_uses_eod_change_pct` — Block 3 at `now=15:40` computes `avg_change_pct` from the **EOD frame** (0.06/0.01), never preview rows (0.051/0.021).
- `test_auction_recap.py:636-643` — `now=15:10` + preview → `avg_open_gap` present, `avg_change_pct`/`close_fulfill_rate`/`up_rate` **absent**, note contains EOD-pending text.
- `test_auction_recap.py:275-295` — `pre_eod` vs `no_auction_lake` label discrimination (today<15:30 / today 15:40 no-lake / history never pre_eod).
- Fixtures to reuse: `repo_env` (`test_auction_recap.py:38-47`, DataStore+KlineRepository tmp isolation), `_FakeRepo`/`_eod_frame`/`_preview_payload`/`_write_premarket_preview` (`:50-222`), `now=` injection.

### 1.3 New test file: `backend/tests/test_daily_pipeline_refresh.py` (3 tests)

Mirror `test_pool_eod_job.py` header style; copy its `_FakeRepo`/`_make_app_state` shapes (self-contained, no cross-test imports). Fixture basis: real `DataStore`+`KlineRepository` on `tmp_path` (test_minute_sync_verify `_seed_daily_lake` pattern) so `refresh_cache` genuinely loads from parquet.

1. `test_pipeline_then_refresh_refreshes_cache_on_success` — stub `daily_pipeline.run_now` → `{"ok": True}`; `_get_app_state` → `SimpleNamespace(repo=repo, capabilities=capset, quote_service=None)`; call `_pipeline_then_refresh()`; assert result returned **and** `repo.refresh_cache` was called (spy-wrapped or assert via `enriched_latest_date()` after seeding).
2. `test_pipeline_then_refresh_refreshes_cache_in_finally_on_stage_error` — stub `run_now` raises `PipelineStageError` (defined `daily_pipeline.py:36`); seed enriched partition **inside the stub before raising**; assert `pytest.raises(PipelineStageError)` **and** cache still refreshed: `get_enriched_latest_asset("stock")` returns `(df, T)` — this locks the `finally` (9aa96ed "部分成功也生效") semantics, the core of ce5c705.
3. `test_refresh_cache_loads_latest_enriched_eod_frame` — real repo; `repo.append_enriched(eod_frame)` for fixed date T (cols ⊆ `ENRICHED_STORAGE_COLS`, `indicators/pipeline.py:57-71`; shape per `test_minute_sync_verify.py:95-110` incl. `quote_ts`, EOD close values distinct from any prior day); `repo.refresh_cache()`; assert `get_enriched_latest_asset("stock")` → `cache_date == T` and `df.close == EOD closes`; `enriched_latest_date() == T` (repository.py:1118-1120).

Optional (skip if time-boxed): one integration test `test_pipeline_then_refresh_end_to_end_eod_frame` merging 1+3 (stub `run_now` = the seed writer; after `_pipeline_then_refresh()`, latest asset is the EOD frame). Recap EOD consumption needs **no new test** (1.2 coverage) — cross-link in docstring.

Verify: `cd backend && uv run pytest tests/test_daily_pipeline_refresh.py -q` (full suite convention: `uv run pytest`, prior phases ran 1686 passed).

---

## 2. LG-02 — CHART-04 stance doc

### 2.1 Evidence (labels live, read this session)

- `frontend/src/components/pool-hub/StockListTable.tsx:319` — group header title "由竞价量与历史均量、委托量输入派生的估算值，非真实成交。"; `:321` group header 「派生 · 虚拟成交」; `:335` 「虚拟未匹配金额（元·估算）」 title "虚拟未匹配量 × 虚拟参考价的估算值，非真实成交金额。".
- `frontend/src/lib/api.ts:741-742` — `PoolHubRow.auction_unmatched_amount` doc 「元·估算, 派生」.
- Server-side precedent: `backend/app/api/pipeline.py:178` 「估算, 非真实成交」; derived chain `auction_columns.py:17-19,100-106,123-124` (two input columns → derived amount).
- Re-eval gate input columns: `auction_unmatched_volume` + `auction_virtual_price` (per REQUIREMENTS LG-02 / 26-RESEARCH §1.7 OQ-1 判定条件).

### 2.2 Placement recommendation

**`docs/features.md`**, new section `### 🧮 竞价列与派生列（Auction Columns & Derived Estimates）` — place after the 「盘前预览」 section (its 诚实边界 bullet `features.md:50` already references tier-2) or after 「竞价复盘」 (`:217`). ARCHITECTURE.md has **zero** auction content (grep: no 竞价/auction/tier-2/估算 matches) — do not touch it.

Section content (3 bullets, feature-manual style — emoji header + 诚实边界 bullets):
1. **Standing stance**: 派生列 (虚拟成交) 以「估算」标注为常态 — 已在 UI (`StockListTable.tsx:319,321,335`) 与 API 类型注释 (`api.ts:741-742`) 固定;任何新 UI 混排派生列必须沿用此标注纪律 (先例 `pipeline.py:178`);湖空 (0 分区) → 列永不出现 (诚实缺列, `auction_columns.py:123-124`).
2. **CHART-04 defer**: 「实时虚拟成交列」正式 defer — 实时 = 连续竞价实时行情无竞价字段, 且盘中实时虚拟成交列需 live 竞价流; 湖实数据 248 日已由 Phase 32 回填, 但**派生列仍为估算**, 与真实竞价列严格区分 (BT-05 分支互斥).
3. **Re-eval gate (tier-2 重开条件)**: 外部实时竞价源提供 `auction_unmatched_volume` + `auction_virtual_price` 两输入列 → tier-2 盘前真实竞价列 gate 重开 (部署清单 D3); 判定条件 = 源返回窗口内行且含两列 (`auction_probe` available, `kline_auction` 分区 6 列); 未提供 → 维持现状, 不伪造、不 0 填.

Cross-ref from the 竞价复盘 section note (one line) optional.

---

## 3. LG-03 — Deploy checklist placement

### 3.1 Recommendation: copy → `docs/deploy-verification.md`

- docs/ naming convention = lowercase kebab (`deploy-password.md`, `custom-data-source.md`, `configuration.md`; only `UPSTREAM-SYNC.md` deviates). `DEPLOY-VERIFICATION.md`/`DEPLOY-CHECKLIST.md` both break it → recommend `docs/deploy-verification.md`.
- **Copy (not reference-in-place)**: the operator needs the manual at deploy time without `.planning/` access; `.planning` is internal research provenance. Keep `.planning/research/v2.3-data-depth/DEPLOY-CHECKLIST.md` as the audited source (cited by v2.1/v2.2 audits); the docs copy is the canonical operating manual.
- Content: verbatim copy of DEPLOY-CHECKLIST.md (D1..D8, timing table, runbook, fail-closed 总则) + orchestrator-approval markers — a short header noting it consolidates v2.1/v2.2 audit open items + Phase 27/30/31 UAT (approved 2026-08-06), owner = 部署运维, and that D3 is **conditional** (external auction source gate, currently not configured → fail-closed pass state).
- Cross-links: `docs/deployment.md` header or bottom "部署验证" line → `./deploy-verification.md`; `docs/features.md:3` intro line already links configuration/deployment — add deploy-verification there; LG-02 section references D3.

### 3.2 What stays in .planning

- LEGACY-COMPLETION.md (domain research) + DEPLOY-CHECKLIST.md (audit provenance) unchanged.
- No other docs/ file needs editing beyond the two cross-link lines.

---

## 4. LG-04 — WATCH-04 batch-add extension (P2, pure frontend + e2e)

### 4.1 Current state (verified)

- `PoolHubPage.tsx:112-114` `handleBatchAdd` scope = `filteredRows` (all visible); batch button `:309-320` VIP-only, hidden when `watchlistOnly` (D6: visible rows all in watchlist); toast `:121-128`.
- `StockListTable.tsx` props `:22-51` (mode/rows/watchlistSet/onToggleWatchlist/watchlistPending/watchlistOnly…); VIP code cell `:359-384` (board badge + code + star button aria 加入自选/移出自选); header `:299-317` (columns map, no checkbox column).
- Backend: `watchlist.py:35-40` `POST /api/watchlist/batch` loops `watchlist.add` (idempotent dedupe `:37-52` — re-add moves to top); `api.ts:2092-2096` `watchlistBatchAdd(symbols, note)` exists; `useWatchlistBatchAdd` (`useSharedMutations.ts:31-40`) already invalidates `QK.watchlist` + `QK.watchlistEnriched()` on success. Body cap = display_limit ≤ 200 (`StrategySettingsDialog.tsx:390`).
- e2e: `pool-hub.spec.ts` WATCH-04 test `:1237-1254` (batch body set-compare `{300750.SZ, 600519.SH}` + toast); ALLOWED_RE `:628`; no-mutating relaxation `:658-662`; snapshots `:776-874`; hub payloads `:13-21,23-66,195-203`; `installShell` `:268-309` (+ `**/api/watchlist` empty-set default route `:308`).

### 4.2 Frontend design (2 files, zero backend, zero Watchlist.tsx)

**`frontend/src/components/pool-hub/StockListTable.tsx`**
- New props: `selection: Set<string>`, `onToggleSelection(symbol: string): void`, `onToggleSelectAll(): void`.
- VIP only (mirror star-button rule `:359-384`; guest renders nothing — guest 零控件 contract): prepend a checkbox column.
  - Header cell (first `<th>`, rowSpan=2 on grouped header path): checkbox with `aria-label="全选"`, `aria-checked` = all-visible-selected → `'true'`, some → `'mixed'`, none → `'false'`; indeterminate visual via ref/`el.indeterminate`.
  - Row cell (first `<td>` before board badge): `<input type="checkbox" aria-label={\`选择${row.code}\`} checked={selection.has(row.symbol)} onChange={() => onToggleSelection(row.symbol)}>`.
- `GUEST_COLUMNS`/`VIP_COLUMNS` untouched; the selection header renders only when `mode === 'vip'`.

**`frontend/src/pages/PoolHubPage.tsx`**
- `const [selected, setSelected] = useState<Set<string>>(new Set())`; clear whenever `activeStrategy?.id`, `filterText`, `watchlistOnly`, or `selectedDate` changes (clear-in-handler or `useEffect` on the tuple — recommend clear-in-handler, honest semantics: no stale selection across views).
- `handleBatchAdd` scope = `[...selected]` (intersect `filteredRows` defensively); empty → early return; existing toast flow reused.
- Batch button: `disabled={batchAdd.isPending || selected.size === 0}`; keep `aria-label="批量加自选"` stable (existing e2e + ALLOWED_RE depend on it); keep hidden when `watchlistOnly` (D6).
- Header checkbox state derives from `selected ∩ filteredRows`; wire `onToggleSelectAll` (all-or-none vs visible rows).
- Pass `selection`/`onToggleSelection`/`onToggleSelectAll` to `StockListTable`.

### 4.3 e2e design (extend `pool-hub.spec.ts` — fixtures live there; do NOT create a new spec)

New tests (all `DESKTOP_PROJECT`-skipped like siblings; `installShell` + `hubPayload` + `watchlistPayloadEmpty` + captured `POST /api/watchlist/batch` body — WATCH-04 `:1237-1254` recipe):

1. `WATCH-04 勾选单行批量加自选 — body=选中行 + toast`: click `getByRole('checkbox', { name: '选择300750' })` → click 批量加自选 → `expect.poll(batchBody).toEqual({ symbols: ['300750.SZ'] })` (order-sensitive here, single element) → toast 已添加 1 只到自选.
2. `WATCH-04 全选可见行 + 空选禁用`: initial 批量加自选 disabled (empty selection); click `getByRole('checkbox', { name: '全选' })` → batch enabled → body = both symbols (set-compare); click 全选 again → disabled.
3. `WATCH-04 切换清空选中`: select 选择300750 → switch strategy card (盘前强势量化) → checkbox `aria-checked=false` (selection cleared).
4. Guest zero-controls: extend the existing guest tests (e.g. `:1148` no-mutating guest) with `expect(page.getByRole('table').getByRole('checkbox')).toHaveCount(0)`; watchlistOnly-on hides batch button (existing D6) — add one assertion that with switch on, no row checkbox is rendered OR batch stays hidden (decide: checkboxes remain visible under watchlistOnly is fine — only the button hides; keep assertion to button only, mirroring `:309-320`).

Guard updates (P1 — the same change, or the suite fails):
- `ALLOWED_RE` at `:628`: add `选择\d{6}|全选`.
- The guard loop only scans `getByRole('button')` — add a parallel checkbox-name loop in the same test (`main.getByRole('checkbox')` → aria-label must match ALLOWED_RE).

**Snapshot risk (P1)**: VIP table gains a checkbox column → `pool-table-resonance.png` (`:778`), `pool-table-filter-active.png` (`:784`), `pool-vip-plaintext.png` (`:874`) change (guest snapshots unchanged). Plan must include a deliberate snapshot pass: run `npx playwright test e2e/pool-hub.spec.ts --project=desktop-chromium --update-snapshots`, review the diff, commit intentionally (mirror Phase 25 快照先例).

Verify: `cd frontend && npm run build` (tsc -b + vite build) then `npx playwright test e2e/pool-hub.spec.ts --project=desktop-chromium` (config: workers=1, retries=0; `webServer` auto-starts vite :4173 unless `PHASE1_BASE_URL` set; 5 projects — non-desktop WATCH tests self-skip).

---

## 5. LG-05 — OQ-3 probe smoke (P2)

### 5.1 Verified facts

- `backend/scripts/probe_concept_drift.py` — manual-only; offline `capture()` (`concept_history.py:171-196`) reads `data/ext_data/{id}/part.parquet` (`_current_rows` `:102-111`) → forward-archives `ext_history/{kind}/date={as_of}/` (`_write_partition` `:115-157`, mkdirs parents) + appends `_probe/drift.jsonl` (script `:45-74`, `probe_dir.mkdir(parents=True)` `:47`). **Zero network on the offline path** (no httpx import in capture; `--upstream` is separate).
- Disk reality (this session): `data/ext_data/ext_gn_ths/part.parquet` + `ext_hy_ths/part.parquet` present (configs colocated as `config.json` per `ExtConfigStore` `ext_data.py:182-215`); `data/ext_history` **absent** → first capture creates it (as designed, D7 expects operator creation).
- `DATA_DIR` env override supported (script `:27-28`) → isolated smoke without polluting the real lake.

### 5.2 Smoke run design (executed in 35-01; sandbox-verifiable, fully offline)

```bash
mkdir -p /tmp/oq3-smoke && cp -r data/ext_data /tmp/oq3-smoke/
cd backend && DATA_DIR=/tmp/oq3-smoke uv run python scripts/probe_concept_drift.py 2026-08-06
```

Pass criteria:
1. stdout: `probe 2026-08-06: gn_ths sha=<64hex> rows=<N> eff=<iso|None>; hy_ths sha=… rows=… eff=…; drift.jsonl lines=2` and exit 0.
2. `/tmp/oq3-smoke/ext_history/{gn_ths,hy_ths}/date=2026-08-06/{part.parquet,manifest.json}` exist; `_probe/drift.jsonl` has 2 lines (one per kind, fields date/kind/sha256/rows/effective_date).
3. Zero side effects: real `data/ext_data/*` byte-identical (copy source untouched), `data/ext_history` still absent in the real lake, `strategy_cache`/`screener_results` untouched (offline path writes only under DATA_DIR/ext_history).
4. Re-run idempotency: second run rewrites partitions (same sha — assert stable) and appends 2 more drift lines (`lines=4`) — append-only semantics documented, not a bug.

Honest note for the plan: this validates **mechanism only** (one forward capture + drift line). The weekly report (sha dedup over ≥5 trading days, concept add/drop samples, `effective_date` vs upstream publish lag calibration) is **deploy-gated** — D7 in the checklist, operator runs per trading day. `--upstream` mode NOT part of the smoke (live network; D7-4 optional).

---

## 6. Plan split (recommended: 3 plans, wave-able 35-01 ‖ 35-02 ‖ 35-03)

| Plan | Scope | Test names / verify commands |
|---|---|---|
| **35-01** (backend) | LG-01 + LG-05 | New `backend/tests/test_daily_pipeline_refresh.py`: `test_pipeline_then_refresh_refreshes_cache_on_success`, `test_pipeline_then_refresh_refreshes_cache_in_finally_on_stage_error`, `test_refresh_cache_loads_latest_enriched_eod_frame` (+ optional end-to-end variant). Verify: `cd backend && uv run pytest tests/test_daily_pipeline_refresh.py -q`. LG-05: isolated smoke per §5.2 + drift.jsonl line/shape asserts. Cross-link recap coverage to `test_auction_recap.py:541-559,636-643,275-295` (no new recap tests). |
| **35-02** (frontend + e2e) | LG-04 | Files: `StockListTable.tsx` (checkbox props), `PoolHubPage.tsx` (selection state + batch scope). e2e in `pool-hub.spec.ts`: 4 new tests (§4.3 names) + ALLOWED_RE/checkbox-loop update + guest zero-checkbox + snapshot regeneration (3 VIP PNGs). Verify: `cd frontend && npm run build` && `npx playwright test e2e/pool-hub.spec.ts --project=desktop-chromium`. |
| **35-03** (docs) | LG-02 + LG-03 | `docs/features.md` new section (§2.2) + `docs/deploy-verification.md` copy with orchestrator-approval header (§3.1) + cross-links in `deployment.md`/`features.md` intro. Verify: read-back + relative-link check (no automated test exists for docs). |

All three plans are independent (no cross-dependencies; 35-02 does not touch backend, 35-01 does not touch frontend/docs). Can run as one wave or sequential; execution-order convention favors 35-01 → 35-02 → 35-03 (backend regression first, docs last after feature freeze).

---

## 7. Risks

1. **e2e snapshot churn (P1, 35-02)**: VIP checkbox column changes `pool-table-resonance.png`/`pool-table-filter-active.png`/`pool-vip-plaintext.png` (pool-hub.spec.ts:778,784,874). Mitigation: intentional `--update-snapshots` pass + human review in the same change; do not ship updated PNGs unseen. Guest snapshots unaffected.
2. **e2e flakiness**: playwright config `workers=1, retries=0, fullyParallel:false` (playwright.config.ts) — new tests must be fully mocked (installShell routes) and use `expect.poll` for request-body capture (existing WATCH-04 pattern); 5 projects exist but non-desktop WATCH tests self-skip via `test.skip(testInfo.project.name !== DESKTOP_PROJECT)`.
3. **ALLOWED_RE/guard breakage (P1, 35-02)**: the POOL-03 zero-affordance guard (`:628` loop) fails the whole suite if new controls lack registered accessible names — update regex + add the checkbox loop in the same commit (the guard is a feature; do not weaken it).
4. **Backend test runtime**: `refresh_cache` recomputes indicators (300-day scan) — keep fixture to 1-2 symbols × 1-2 days (ms-level); avoid `background=True`; close DataStore db in finally (convention in all fixture files).
5. **docs drift**: features.md is actively maintained (updated today) — new sections must follow section style (emoji headers, 诚实边界 bullets); deploy-verification copy can drift from the .planning source → add a one-line provenance note in the header ("source: .planning/research/v2.3-data-depth/DEPLOY-CHECKLIST.md, update both").
6. **Watchlist.tsx zero-touch guard**: LG-04 touches only PoolHubPage/StockListTable/pool-hub.spec.ts — plan must keep `frontend/src/pages/Watchlist.tsx` unmodified (existing milestone guard); verify with `git status` at plan execution.
7. **OQ-3 append-only drift.jsonl**: re-runs append lines (idempotent partitions, non-idempotent drift log) — smoke asserts exact line counts; D7 weekly dedup logic handles repeats (acceptable dup hashes).

---

## 8. Evidence index (all read this session)

| Evidence | file:line |
|---|---|
| `_pipeline_then_refresh` finally refresh_cache | backend/app/jobs/daily_pipeline.py:1115-1136 |
| `PipelineStageError` | backend/app/jobs/daily_pipeline.py:36 |
| `run_now` signature | backend/app/jobs/daily_pipeline.py:185 |
| refresh_cache → `_refresh_enriched` → latest parquet | backend/app/tickflow/repository.py:351,461-577 |
| `_live_agg_baseline_date` | backend/app/tickflow/repository.py:770-784 |
| `get_enriched_latest_asset` | backend/app/tickflow/repository.py:920-935 |
| `enriched_latest_date` | backend/app/tickflow/repository.py:1118-1120 |
| DuckDB live-glob view (no rebuild needed for reads) | backend/app/tickflow/repository.py:142-150 |
| `ENRICHED_STORAGE_COLS` | backend/app/indicators/pipeline.py:57-71 |
| pre-EOD rule + note | backend/app/services/auction_recap.py:339-346,393-396; header label :550-556 |
| recap enriched load (cache-first) | backend/app/services/screener.py:243-254; auction_recap.py:524-530 |
| schedules (15:30 pipeline / 15:40 review) | backend/app/services/preferences.py:329-332,434-444 |
| recap EOD/pre-EOD tests | backend/tests/test_auction_recap.py:275-295,541-559,636-643 |
| recap fixtures (`repo_env`/`_FakeRepo`/`_eod_frame`/`_preview_payload`) | backend/tests/test_auction_recap.py:38-47,50-222 |
| pool EOD job fixture shape | backend/tests/test_pool_eod_job.py:23-97 |
| fake quote_service with `paused()` | backend/tests/test_preopen_scheduling.py:60-84 |
| real-repo seeding recipe | backend/tests/test_minute_sync_verify.py:71-110 |
| no test_daily_pipeline* file; piecewise job tests | backend/tests/ listing (test_pool_eod_job/premarket_pool/preopen_scheduling/auction_sync/minute_sync_verify) |
| 估算 labels (UI) | frontend/src/components/pool-hub/StockListTable.tsx:319,321,335 |
| 估算 label (API type) | frontend/src/lib/api.ts:741-742 |
| features.md style + 盘前预览 诚实边界 + 竞价复盘 section | docs/features.md:9,44-50,217-247 |
| deployment.md / docs naming (kebab) | docs/deployment.md; docs/deploy-password.md |
| ARCHITECTURE.md zero auction content | docs/ARCHITECTURE.md (grep 0 matches) |
| WATCH-04 current batch scope + button | frontend/src/pages/PoolHubPage.tsx:112-114,309-320 |
| StockListTable props + VIP code cell | frontend/src/components/pool-hub/StockListTable.tsx:22-51,359-384 |
| batch endpoint idempotent | backend/app/api/watchlist.py:35-40; services/watchlist.py:37-52 |
| `watchlistBatchAdd` + hook | frontend/src/lib/api.ts:2092-2096; useSharedMutations.ts:31-40 |
| e2e WATCH-04 + ALLOWED_RE + guards + snapshots | frontend/e2e/pool-hub.spec.ts:628,658-662,776-874,1237-1254 |
| e2e payloads/installShell | frontend/e2e/pool-hub.spec.ts:13-21,195-203,268-309 |
| playwright config (workers/projects/webServer) | frontend/playwright.config.ts |
| probe script offline path + DATA_DIR | backend/scripts/probe_concept_drift.py:27-28,45-74 |
| capture/`_write_partition`/`_current_rows` | backend/app/services/concept_history.py:102-111,115-157,171-196 |
| ExtConfigStore config location | backend/app/services/ext_data.py:182-215 |
| ext snapshots present / ext_history absent | data/ext_data/{ext_gn_ths,ext_hy_ths}/part.parquet (verified); data/ext_history missing |

## 9. Open questions (for planner/main)

1. **Snapshot policy for 35-02**: is regenerating the 3 VIP pool PNGs in-plan acceptable (they're visual-regression assets, `toHaveScreenshot` with `maxDiffPixelRatio:0.02`), or should the checkbox column be visually neutral (smaller control) to minimize churn? Default plan: regenerate deliberately.
2. **Selection clear-on-change vs persistent**: design clears selection on strategy/filter/date/watchlistOnly change (honest semantics). If product wants persistence across strategy switches, that's a scope add — confirm P2 intent.
3. **LG-05 smoke data dir**: isolated `DATA_DIR=/tmp/oq3-smoke` (recommended, zero real-lake pollution) vs real `data/` run (creates the first real forward archive + drift.jsonl in the actual lake, which D7 will then continue). Confirm the executor may write under `/tmp` (sandbox) — constraint says write only RESEARCH.md, so the smoke executes during 35-01, not now.
