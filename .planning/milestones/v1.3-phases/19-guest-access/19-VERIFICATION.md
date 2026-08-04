---
phase: 19-guest-access
verified: 2026-08-04T15:41:36Z
status: passed
score: 20/20 truths verified
behavior_unverified: 0
overrides_applied: 0
gaps: []
human_signoff: user-approved 2026-08-04 (放行偏好延续自 Phase 18 — 24 Playwright e2e + 截图证据)
human_verification:
  - test: "Open /pool-hub under a guest session (mocked guest payload or guest API) and confirm the 数据不可用 strategy card (40% opacity, no click) coexists with the guest banner without layout interference in the card grid."
    expected: "The guest banner (bg-elevated/60, border, rounded-btn) sits above the card grid; the 数据不可用 card renders at 40% opacity with no click and no banner overlap; card positions and spacing are unaffected."
    why_human: "Visual layout check — grep/e2e presence cannot confirm perceived layout interference."
  - test: "With the guest banner present, confirm long strategy names still truncate with ellipsis and never wrap the card or push the 当日池 {N} 只 count off-layout."
    expected: "The long-name strategy card (e.g. 竞价高开强度叠加盘前量能与连板因子共振筛选策略…) keeps the name on one line with truncate; the count stays on the card and no card expands or overlaps."
    why_human: "Visual truncation/wrap behavior — cannot be proven by source presence alone."
  - test: "Render a large guest pool where many rows share the identical ****** identity and confirm rows remain visually distinct via 涨跌幅/概念板块/关联因子 and the 交叉共振 highlight; no row collapse, merge, or perceived duplication."
    expected: "12+ guest rows with identical masked 代码/名称 remain separate, distinguishable rows; 交叉共振 rows keep the accent tint + badge; the 共 {M} 只 footer is correct."
    why_human: "Visual distinctness under identical masked values — e2e asserts counts, not human perception of distinctness."
  - test: "Switch guest → VIP (or the reverse) by refreshing with the server re-declaring mode and confirm the 开盘涨幅 column toggles without a layout jump or page reflow; the table reflows cleanly inside the scroll container."
    expected: "The 开盘涨幅 column appears/disappears with the header set changing to exactly the VIP/GUEST column set; no whole-page reflow or horizontal scroll jump."
    why_human: "Perceived reflow/layout jump on the column-set shift — e2e confirms the DOM change, not the absence of visual jump."
---

# Phase 19: 游客/VIP 脱敏 + 前端 (Guest Access & Frontend) Verification Report

**Phase Goal:** Guests see only 涨跌幅 and 概念板块 with stock code/name masked server-authoritatively; VIP sessions see明文; the frontend pool page composes cards, lists, filtering, and resonance into one workspace.
**Verified:** 2026-08-04T15:41:36Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

**Roadmap Success Criteria (contract):**

| #   | Truth   | Status     | Evidence       |
| --- | ------- | ---------- | -------------- |
| SC1 | Guest session responses mask stock code/name (`******`) at the API DTO boundary and expose only 涨跌幅/概念板块; VIP responses are明文; no client-side masking is trusted | ✓ VERIFIED | `backend/app/services/guest_masking.py::mask_guest_hub` (MASKED_IDENTITY="******", `_GUEST_VISIBLE` whitelist, copy-safe rebuild); `backend/app/api/pool.py::get_pool_hub` derives `mode` from `request.state.reviewer_principal`; backend tests `test_guest_no_cookie_returns_masked_hub` / `test_vip_valid_cookie_returns_clear_hub` pass; frontend grep guard e2e passes; direct grep shows zero `******` in `frontend/src` |
| SC2 | Masking is display-only — underlying factor computation and strategy results remain unmasked and correct for all sessions | ✓ VERIFIED | `pool_hub.py::build_pool_hub` always projects real `name`/`code`/`open_gap`; `test_build_pool_hub_rows_stay_unmasked`; `test_guest_mask_does_not_mutate_cache_or_hub` (on-disk `strategy_cache.json` unchanged); AST guards `test_guest_masking_imports_no_engine_or_persistence` + `test_guest_masking_has_no_write_path` pass |

**19-01-PLAN must_haves truths:**

| #   | Truth   | Status     | Evidence       |
| --- | ------- | ---------- | -------------- |
| 1   | Guest-session responses to GET /api/pool/hub mask `code`/`name`/`symbol` to exactly `******`, `open_gap` omitted; `change_pct`/`concept_board`/`hit_factors`/`cross_resonance` + strategy `id`/`name`/`total`, `as_of`, `updated_at`, `resonance_count` intact | ✓ VERIFIED | `guest_masking.py` masked-row build + whitelist; `test_guest_no_cookie_returns_masked_hub` (real middleware, no cookie → mode=guest, all rows `******`, no `open_gap`) |
| 2   | VIP-session responses are明文: real `code`/`name`/`symbol` and `open_gap` unchanged | ✓ VERIFIED | `pool.py` `is_vip` branch skips the mask; `test_vip_valid_cookie_returns_clear_hub` (valid `tf_session` → mode=vip, real code 600000, name, open_gap 3.21) |
| 3   | Hub response declares `mode: "guest" | "vip"` server-side derived from `request.state.reviewer_principal` — never client input/row values | ✓ VERIFIED | `pool.py` lines 43-46; `test_guest_mode_vocabulary_and_no_identity_leak` (mode ∈ {guest,vip}); invalid-cookie → guest (`test_invalid_cookie_returns_guest`) |
| 4   | Masking is display-only: `build_pool_hub` always returns unmasked rows; mask applied only as copy-safe serialization at API boundary; never mutates persisted cache/engine results | ✓ VERIFIED | `pool_hub.py` unmasked projection (lines 118-127); `test_build_pool_hub_rows_stay_unmasked`; `test_guest_mask_does_not_mutate_cache_or_hub` (deep-copy compare + disk JSON check) |
| 5   | Guest access limited to read-only GET paths: unauthenticated sessions reach `/api/pool/hub` + `/api/screener/strategies`; every other `/api/` path and non-GET methods 401 | ✓ VERIFIED | `main.py` `_GUEST_READ_GET_PATHS` frozenset + `_is_guest_readable` GET-only (lines 776-783, 831-835); `test_guest_cannot_read_authed_surfaces` (settings/portfolio/watchlist → 401); `test_guest_read_paths_are_get_only` (POST/PUT/DELETE/PATCH → not 200) |
| 6   | Guest DTO leaks no real identity (masked literal `******`, no `open_gap` key) and is `json.dumps`-serializable in both modes | ✓ VERIFIED | `test_guest_mode_vocabulary_and_no_identity_leak` (no `\b\d{6}\b` token, no open_gap, code==name==symbol=="******"); `test_guest_response_json_serializable_roundtrip` (both modes round-trip) |
| 7   | Masking transform lives in a dedicated module importing no engine/persistence/execution module and containing no write path (source-level guard) | ✓ VERIFIED | `guest_masking.py` imports only `typing`; AST guards `test_guest_masking_imports_no_engine_or_persistence` + `test_guest_masking_has_no_write_path` pass |

**19-02-PLAN must_haves truths:**

| #   | Truth   | Status     | Evidence       |
| --- | ------- | ---------- | -------------- |
| 8   | Hub loading (mode unknown) renders `股池加载中…` + Loader2 + `role="status"`; no banner flash, guest column set not applied until mode known | ✓ VERIFIED | `PoolHubPage.tsx` lines 94-106 (pending block, role=status); banner gated on `data && mode === 'guest'` (line 123); e2e `hub loading renders 股池加载中… with status role and disables refresh` passes |
| 9   | Hub error (mode unknown) renders `股池加载失败：{message}。请检查数据源后重试。` in `role="alert"` with `重试`; no guest-specific error/banner | ✓ VERIFIED | `PoolHubPage.tsx` lines 109-120; e2e `hub error renders the alert with 重试 action` passes |
| 10  | Empty-as_of in guest mode renders `当日无股池结果` AND guest banner still renders when loaded hub declares `mode: "guest"` | ✓ VERIFIED | `PoolHubPage.tsx` lines 123-132; e2e `guest empty hub still renders the guest banner (session-policy state)` passes |
| 11  | Populated guest: renders server-masked rows verbatim (`******` in 代码/名称), no 开盘涨幅 column, 涨跌幅/概念板块/关联因子 unchanged; mode from server, never row values | ✓ VERIFIED | `StockListTable.tsx` `GUEST_COLUMNS` (line 13), masked cells render `row.code`/`row.name` verbatim (lines 179-204), `!isGuest &&` 开盘涨幅 cell (line 206); e2e `guest mode renders banner, masked cells, and the 5-column guest set` passes (exact header set, zero 开盘涨幅 columnheaders, 4 masked cells, no real codes/names) |
| 12  | Populated VIP: 明文 rows + 名称 column + 开盘涨幅 column; no guest banner | ✓ VERIFIED | `StockListTable.tsx` `VIP_COLUMNS` (line 14), board tag + real code (lines 183-192), name `truncate text-foreground` (line 200), 开盘涨幅 `PctCell` (line 206); e2e `vip mode renders 明文 with 名称 and 开盘涨幅` passes (6 headers, real 300750/宁德时代, +2.34%/+1.05%, no banner) |
| 13  | Zero-one-many guest rows: distinct rows keyed by strategy-scoped ordinal, never masked symbol — no duplicate React keys | ✓ VERIFIED | `StockListTable.tsx` line 169 `isGuest ? \`${strategy.id}-${index}\` : row.symbol`; e2e `guest↔vip mode switch toggles the 开盘涨幅 column from the server mode field` passes with `page.on('pageerror')` capturing zero duplicate-key errors |
| 14  | 交叉共振 in guest mode: badge + accent row highlight + legend unchanged and visible to guests | ✓ VERIFIED | `StockListTable.tsx` cross badge/tint shared (lines 172-176, 216-220); e2e `guest 交叉共振 badge and legend remain visible` passes |
| 15  | Partial guest rows: missing 概念板块/关联因子 render `—` (muted); masked `******` cells never blank or `—` | ✓ VERIFIED | `StockListTable.tsx` ConceptChips/`—` fallbacks (lines 208-215); e2e `guest accessibility and copy contract` asserts masked cells visible, non-empty, not `—`, no title/aria-label leak |
| 16  | Overflow guest: many rows + `共 {M} 只` footer + `overflow-x-auto` container; 5-column table fits `minWidth: 720`; 6-char `******` cell never truncated | ✓ VERIFIED | `StockListTable.tsx` lines 154-155, footer line 238; e2e `captures visual evidence for guest mode backstops` asserts maskedCount ≥ 24 and `共 12 只` visible |
| 17  | Long-text guest banner: title/body wrap safely (`overflow-wrap:anywhere`) at all viewports, ≥8px icon separation, no page-shell overflow | ✓ VERIFIED | `GuestModeBanner.tsx` `[overflow-wrap:anywhere]` (line 20), `gap-2` icon/title separation, `min-w-0` body (line 23); e2e guest banner tests pass |
| 18  | Security — no client masking: grep guard over `frontend/src` finds no masking function, no `******` literal, no row-value mode derivation; only e2e fixtures hold `******` | ✓ VERIFIED | Direct grep: zero `******` in `frontend/src`; zero `.code|.symbol === '******'` derivation; e2e `frontend contains no client-side masking code (grep guard)` passes over PoolHubPage, GuestModeBanner, StockListTable, ConceptFilter, StrategyCardGrid, api.ts |
| 19  | Guest column headers exactly `代码`·`名称`·`涨跌幅`·`概念板块`·`关联因子`; VIP exactly `代码`·`名称`·`开盘涨幅`·`涨跌幅`·`概念板块`·`关联因子` | ✓ VERIFIED | `StockListTable.tsx` GUEST_COLUMNS/VIP_COLUMNS (lines 13-14); e2e columnheader assertions in guest + VIP tests pass |
| 20  | Guest banner is a neutral info banner (`bg-elevated/60 border border-border rounded-btn px-3 py-2`, Lock 14px `aria-hidden`, title `text-sm text-secondary`, body `text-xs text-muted`, `role="status"`, accessible text `游客模式：股票代码与名称已脱敏，仅展示涨跌幅与概念板块。`) | ✓ VERIFIED | `GuestModeBanner.tsx` (all classes/copy/aria); e2e `guest accessibility and copy contract` asserts `role=status` + exact accessible name |

**Score:** 20/20 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `backend/app/services/guest_masking.py` | mask_guest_hub copy-safe transform | ✓ VERIFIED | MASKED_IDENTITY="******", `_GUEST_VISIBLE` frozenset, rebuilds new dicts; imports only `typing`; no write path |
| `backend/app/api/pool.py` | mode derivation + guest mask at DTO boundary | ✓ VERIFIED | `mode` from `request.state.reviewer_principal`; `mask_guest_hub(hub)` for guests |
| `backend/app/services/pool_hub.py` | name projection, service stays unmasked | ✓ VERIFIED | `"name": str(row.get("name") or "")` (line 121); unmasked in all modes |
| `backend/app/main.py` | `_GUEST_READ_GET_PATHS` + auth_middleware guest branch | ✓ VERIFIED | frozenset of exactly 2 GETs; GET-only `_is_guest_readable`; 401 for everything else |
| `backend/tests/test_guest_masking.py` | 15 tests (mask unit, real-middleware endpoint, GUEST-02 proofs, AST guard, surface guards) | ✓ VERIFIED | All pass (in the 32-pass run) |
| `backend/tests/test_pool_hub.py` | name fixtures + expected_keys + VIP-principal client | ✓ VERIFIED | `expected_keys` includes `name` (line 169); `_make_client` binds VIP principal (lines 381-383) |
| `frontend/src/lib/api.ts` | `PoolHubRow.name` + `PoolHubResponse.mode` | ✓ VERIFIED | lines 687, 706 |
| `frontend/src/pages/PoolHubPage.tsx` | mode-driven presentation + banner slot | ✓ VERIFIED | `mode` from `data?.mode` (line 39), banner gated on `data && mode==='guest'` (line 123), passes `mode` to table (line 160) |
| `frontend/src/components/pool-hub/GuestModeBanner.tsx` | new — exact copy, role=status, Lock aria-hidden | ✓ VERIFIED | full component matches UI-SPEC |
| `frontend/src/components/pool-hub/StockListTable.tsx` | 名称 column + guest/VIP column sets + masked cells + strategy-scoped keys | ✓ VERIFIED | GUEST_COLUMNS/VIP_COLUMNS, masked cells verbatim, 开盘涨幅 VIP-only, `\`${strategy.id}-${index}\`` row keys |
| `frontend/e2e/pool-hub.spec.ts` | guest/VIP fixtures + grep guard + visual evidence | ✓ VERIFIED | 24 tests pass; guest fixtures hold the only `******` literals |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `auth_middleware` (session → principal) | `pool.py getattr(request.state,"reviewer_principal")` → `mode` → `mask_guest_hub` → GET /api/pool/hub | request.state plumbing in middleware (line 829/833) | WIRED | Backend tests exercise the REAL middleware: no cookie → guest masked; valid cookie → vip 明文; invalid cookie → guest |
| strategy_cache results (name/code/open_gap/…) | `build_pool_hub` (unmasked projection incl. name) → `mask_guest_hub` (guest only; open_gap omitted) | service projection → DTO transform | WIRED | `pool_hub.py` projects name; `test_guest_mask_does_not_mutate_cache_or_hub` proves disk cache stays 明文 |
| `_GUEST_READ_GET_PATHS` → auth_middleware guest branch → PoolHubPage data fetches | GET /api/pool/hub + /api/screener/strategies with no session | `_is_guest_readable` GET-only check | WIRED | e2e guest fixtures stub both endpoints and the page loads cookie-less |
| GET /api/pool/hub `mode` → PoolHubPage `mode` state → GuestModeBanner + StockListTable column set | server-declared mode drives presentation | `data?.mode === 'guest' ? 'guest' : 'vip'` | WIRED | e2e guest (5-col) vs VIP (6-col) + mode-switch test |
| server-masked row code/name (`******`) → StockListTable masked cells verbatim | no client transform, no literal in src | `{row.code}`/`{row.name}` render | WIRED | grep guard zero matches; e2e asserts exact masked cells |
| mode + hit_factors → 交叉共振 badge + accent tint | unchanged both modes | shared code paths | WIRED | e2e guest 交叉共振 test |
| e2e guest fixture → banner + masked-cell + guest column-set assertions; grep guard over src → no masking code | fixture + guard in spec | `hubPayloadGuest`/`visualHubPayloadGuest` | WIRED | 24/24 e2e pass |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `StockListTable` guest 代码/名称 cells | `row.code`/`row.name` | server-masked `******` from GET /api/pool/hub (mask_guest_hub) | Yes — real masked value from API | ✓ FLOWING |
| `StockListTable` VIP 名称 cell | `row.name` | `build_pool_hub` name projection from strategy_cache rows | Yes — real name from persisted rows | ✓ FLOWING |
| `StockListTable` 开盘涨幅 cell (VIP) | `row.open_gap` | `build_pool_hub` `_safe_num(row.get("open_gap"))` | Yes — real value; missing → `—` | ✓ FLOWING |
| `StockListTable` 概念板块/关联因子 | `row.concept_board`/`row.hit_factors` | concept map join + persisted hit_factors | Yes — non-empty in fixtures/tests | ✓ FLOWING |
| `GuestModeBanner` | static copy + `mode` state | server `mode` field | Yes — renders only when mode==='guest' | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Guest/VIP masking + GUEST-02 display-only + surface guards | `cd backend && .venv/bin/python -m pytest tests/test_guest_masking.py tests/test_pool_hub.py -q` | **32 passed** in 2.00s | ✓ PASS |
| Frontend type-safety of mode/name plumbing | `cd frontend && npx tsc --noEmit` | exit 0 | ✓ PASS |
| Guest banner/masked cells/column sets/mode switch/grep guard/a11y/visual evidence | `cd frontend && npx playwright test e2e/pool-hub.spec.ts --project=desktop-chromium` | **24 passed** in 34.6s | ✓ PASS |
| No `******` literal in production frontend src | grep `\*{6,}` over `frontend/src` | 0 matches | ✓ PASS |
| No row-value mode derivation in frontend src | grep `.code|.symbol === '*'` + MASK_IDENT_RE | 0 matches | ✓ PASS |

### Probe Execution

Step 7c: No probes declared in either PLAN; no `scripts/*/tests/probe-*.sh` referenced. SKIPPED.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| GUEST-01 | 19-01 + 19-02 | Guest sessions see only 涨跌幅/概念板块 with code/name masked at API DTO boundary; VIP 明文; no client-side masking trusted | ✓ SATISFIED | Backend masking + mode + guest surface (tests pass); frontend mode-driven presentation + grep guard (e2e pass) |
| GUEST-02 | 19-01 + 19-02 | Masking is display-only; engine factor computation and strategy results unmasked/correct for all sessions | ✓ SATISFIED | `build_pool_hub` unmasked; AST import/write guard; cache non-mutation test; frontend renders server values verbatim |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| (none) | — | — | — | No TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER markers; no `Not implemented`/placeholder returns; the only `return []`/`return null` occurrences are legitimate guards (empty filtered-rows memo, no-strategy guard) |

### Human Verification Required

4 UI-SPEC `verification: backstop` scalars — visual evidence exists (screenshots `pool-guest-grid.png`, `pool-guest-masked.png`, `pool-vip-plaintext.png` captured and `toHaveScreenshot` assertions pass), but per plan 19-02 Task 3's end-of-phase human-check, explicit visual confirmation by a human is required. See frontmatter `human_verification` for the 4 items.

### Gaps Summary

No functional gaps found. All 20 must-have truths are verified by real, passing behavioral tests (32 backend + 24 e2e + tsc), and the roadmap's 2 success criteria are met. The status is `human_needed` solely because the 4 UI-SPEC backstop scalars are held-out visual judgments requiring end-of-phase human confirmation.

**Informational note (deferred, not a Phase 19 gap):** `backend/tests/advanced/test_production_host.py::test_spawned_governed_backtest_completes_split_evidence_within_budget` failed in the executor's full-suite run (`resource_limited` vs `completed`) — a pre-existing advanced-sandbox resource-budget test unrelated to GUEST-01/02 changes; logged to `deferred-items.md` for re-run before `/gsd-ship`.

---

_Verified: 2026-08-04T15:41:36Z_
_Verifier: Claude (gsd-verifier)_
