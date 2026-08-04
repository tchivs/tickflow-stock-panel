---
phase: 19-guest-access
plan: 1
subsystem: api
tags: [guest-access, masking, auth, fastapi, pytest]

# Dependency graph
requires:
  - phase: 18-pool-hub
    provides: GET /api/pool/hub (single-as_of projection, concept filter, cross_resonance)
provides:
  - Server-authoritative guest masking at the GET /api/pool/hub DTO boundary (GUEST-01)
  - Server-declared presentation `mode` field (guest|vip) derived from session principal
  - name projection in pool-hub rows (名称 column source)
  - Minimal guest read-only GET surface in auth_middleware (2 endpoints)
  - GUEST-02 display-only proofs: masking is a pure copy, engine/persisted results untouched
affects: [19-02 (frontend pool page), verify-work, ui-review]

actuals:
  tokens: 7396        # chars/4 over the realized git diff (29583 chars, 6 files +582 -4)
  tasks: 3
  commits: 4          # 3 task commits + final docs commit

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Copy-safe DTO masking transform: mask_guest_hub builds new dicts, never mutates input"
    - "AST import/write guard on the masking module (mirrors POOL-03)"
    - "Server-declared presentation mode: mode derived from request.state.reviewer_principal, never client input"

key-files:
  created:
    - backend/app/services/guest_masking.py
    - backend/tests/test_guest_masking.py
  modified:
    - backend/app/api/pool.py
    - backend/app/main.py
    - backend/app/services/pool_hub.py
    - backend/tests/test_pool_hub.py

key-decisions:
  - "Guest masking is applied only at the API DTO boundary in pool.py; the service layer build_pool_hub stays unmasked in all modes (GUEST-02)."
  - "mode = vip iff request.state.reviewer_principal resolves; otherwise guest. Never derived from client input or row values (T-19-02)."
  - "Masked identity is the literal 6-asterisk string ******; open_gap is omitted (no key) for guest rows, not nulled."
  - "Guest surface is exactly GET /api/pool/hub + GET /api/screener/strategies; every other /api/ path and every non-GET method still 401 (T-19-03)."

patterns-established:
  - "mask_guest_hub: frozenset _GUEST_VISIBLE whitelist + copy-safe rebuild per strategy row"
  - "_GUEST_READ_GET_PATHS frozenset + _is_guest_readable(path, method) GET-only check in auth_middleware"
  - "Endpoint tests through the REAL auth_middleware by re-registering app.main.auth_middleware on a minimal FastAPI app"

requirements-completed: [GUEST-01, GUEST-02]

coverage:
  - id: D1
    description: "Guest session GET /api/pool/hub returns mode=guest with code/name/symbol masked to ****** and no open_gap key, market factors intact"
    requirement: GUEST-01
    verification:
      - kind: integration
        ref: "backend/tests/test_guest_masking.py#test_guest_no_cookie_returns_masked_hub"
        status: pass
    human_judgment: false
  - id: D2
    description: "VIP session GET /api/pool/hub returns mode=vip with 明文 code/name/symbol/open_gap"
    requirement: GUEST-01
    verification:
      - kind: integration
        ref: "backend/tests/test_guest_masking.py#test_vip_valid_cookie_returns_clear_hub"
        status: pass
    human_judgment: false
  - id: D3
    description: "mode is server-declared (guest|vip), derived from request.state.reviewer_principal, never from client input"
    requirement: GUEST-01
    verification:
      - kind: unit
        ref: "backend/tests/test_guest_masking.py#test_guest_mode_vocabulary_and_no_identity_leak"
        status: pass
    human_judgment: false
  - id: D4
    description: "Masking is display-only: build_pool_hub stays unmasked, mask_guest_hub never mutates hub input or on-disk strategy_cache.json, module imports no engine/persistence/execution module and has no write path"
    requirement: GUEST-02
    verification:
      - kind: unit
        ref: "backend/tests/test_guest_masking.py#test_build_pool_hub_rows_stay_unmasked"
        status: pass
      - kind: unit
        ref: "backend/tests/test_guest_masking.py#test_guest_mask_does_not_mutate_cache_or_hub"
        status: pass
      - kind: unit
        ref: "backend/tests/test_guest_masking.py#test_guest_masking_imports_no_engine_or_persistence"
        status: pass
    human_judgment: false
  - id: D5
    description: "Guest surface is read-only and minimal: exactly the two pool-page GETs; authed surfaces and non-GET methods still 401"
    requirement: GUEST-01
    verification:
      - kind: unit
        ref: "backend/tests/test_guest_masking.py#test_guest_cannot_read_authed_surfaces"
        status: pass
      - kind: unit
        ref: "backend/tests/test_guest_masking.py#test_guest_read_paths_are_get_only"
        status: pass
    human_judgment: false
  - id: D6
    description: "Guest DTO leaks no identity (no 6-digit code token, no open_gap) and is JSON-safe in both modes"
    requirement: GUEST-01
    verification:
      - kind: unit
        ref: "backend/tests/test_guest_masking.py#test_guest_mode_vocabulary_and_no_identity_leak"
        status: pass
      - kind: unit
        ref: "backend/tests/test_guest_masking.py#test_guest_response_json_serializable_roundtrip"
        status: pass
    human_judgment: false

# Metrics
duration: ~55min
completed: 2026-08-04
status: complete
---

# Phase 19 Plan 1: Server-Authoritative Guest Masking (Backend) Summary

**Guest sessions now read GET /api/pool/hub as `mode: "guest"` with code/name/symbol masked to `******` and `open_gap` omitted, VIP sessions get 明文 rows via a server-declared `mode` field — masking is a copy-safe DTO transform that provably never touches the engine or persisted strategy results (GUEST-01/GUEST-02).**

## Performance

- **Duration:** ~55 min
- **Tasks:** 3
- **Files modified:** 6 (4 source, 2 test)
- **Commits:** 4 (3 task commits + final docs commit)

## API Contract for Executor1902 (frontend) — READ THIS FIRST

### `GET /api/pool/hub` — response now includes a top-level `mode` field

| Mode | Trigger | `mode` value | Row identity | `open_gap` | Strategy `id`/`name`/`total`, top-level `as_of`/`updated_at`/`resonance_count` |
|---|---|---|---|---|---|
| **guest** | No valid session (no cookie, or invalid/expired `tf_session`) | `"guest"` | `code`/`name`/`symbol` all the literal string `"******"` (6 asterisks) | Key **omitted entirely** (not null — not present) | Unchanged, intact |
| **vip** | Valid `tf_session` cookie resolves a server principal | `"vip"` | Real 明文 `code`/`name`/`symbol` | Present, real (may be `null` when missing) | Unchanged |

**Guest-visible fields per row (exact):** `change_pct`, `concept_board`, `hit_factors`, `cross_resonance` — plus the masked `code`/`name`/`symbol`. Nothing else.

**`name` is now projected on every pool-hub row** (`str(row.get("name") or "")`, never `None`, may be `""` when the persisted row has no name). VIP gets the real name; guest gets `"******"`.

### Frontend consumption rules

1. **Presentation mode MUST come from `response.mode`** — never derive it by inspecting row values (e.g. `code === '******'`). No client-side masking logic anywhere.
2. **Guest column set** (render when `mode === "guest"`): `代码 | 名称 | 涨跌幅 | 概念板块 | 关联因子` — the 开盘涨幅 column header AND cells are **not rendered**.
3. **VIP column set** (render when `mode === "vip"`): `代码 | 名称 | 开盘涨幅 | 涨跌幅 | 概念板块 | 关联因子`.
4. Render the server-masked `"******"` verbatim (mono, muted per 19-UI-SPEC). Rows keyed by strategy-scoped ordinal, never the masked symbol (many rows share `"******"`).
5. Guest banner: `游客模式：股票代码与名称已脱敏` + body `仅展示涨跌幅与概念板块。` (19-UI-SPEC copy), rendered only when `mode === "guest"`.
6. **Auth:** guests reach exactly `GET /api/pool/hub` and `GET /api/screener/strategies`; every other `/api/` path and any non-GET method on those two still `401`. The frontend pool page should already work cookie-less for guest; authenticated sessions get VIP automatically.
7. **TS type updates needed** (`frontend/src/lib/api.ts`):
   - `PoolHubResponse`: add `mode: 'guest' | 'vip'`
   - `PoolHubRow`: add `name: string`

## Accomplishments

- **Guest masking (GUEST-01):** `backend/app/services/guest_masking.py::mask_guest_hub` — copy-safe DTO transform that rebuilds each strategy row with `code`/`name`/`symbol` = `******`, omits `open_gap`, and preserves `change_pct`/`concept_board`/`hit_factors`/`cross_resonance` plus strategy `id`/`name`/`total` and top-level `as_of`/`updated_at`/`resonance_count`.
- **Server-declared mode:** `backend/app/api/pool.py::get_pool_hub` derives `mode` from `getattr(request.state, "reviewer_principal", None)` — never from client input or row values (T-19-02). Guests get `mask_guest_hub(hub)`, VIPs get the unchanged 明文 hub.
- **Minimal guest read surface:** `backend/app/main.py::auth_middleware` gains `_GUEST_READ_GET_PATHS = frozenset({"/api/pool/hub", "/api/screener/strategies"})` and a GET-only `_is_guest_readable` branch. Unauthenticated sessions reach exactly these two pool-page GETs; every other path/method still 401 (T-19-03).
- **name projection (GUEST-01, 19-UI-SPEC 名称 column):** `build_pool_hub` now projects `name` beside `code`; service layer stays unmasked in all modes (GUEST-02).
- **Display-only proof (GUEST-02):** tests prove `build_pool_hub` rows carry real identity, `mask_guest_hub` never mutates its input or the on-disk `strategy_cache.json`, and an AST guard bans engine/persistence/execution imports and any write path from `guest_masking.py` (mirrors POOL-03).

## Task Commits

1. **Task 1: Guest-session masking end-to-end (tracer)** - `04b0c2b` (feat)
2. **Task 2: name projection + GUEST-02 display-only proofs + masking isolation guard** - `5e5604d` (test)
3. **Task 3: Guest-surface security guards** - `fcf2a9e` (test)
4. **Final metadata commit** - `(docs)` — this SUMMARY + STATE.md/ROADMAP.md

**Plan baseline:** `780930d` (`docs(19): plan guest access masking`)

## Files Created/Modified

- `backend/app/services/guest_masking.py` (new) - `MASKED_IDENTITY = "******"`, `_GUEST_VISIBLE` whitelist, copy-safe `mask_guest_hub`.
- `backend/app/api/pool.py` - imports `mask_guest_hub`; `get_pool_hub` derives `mode` and applies the mask for guests.
- `backend/app/main.py` - `_GUEST_READ_GET_PATHS` + `_is_guest_readable`; `auth_middleware` guest branch (unauthenticated → guest-only GETs, else 401).
- `backend/app/services/pool_hub.py` - projects `name` (`str(row.get("name") or "")`) beside `code`; docstring updated to 六列.
- `backend/tests/test_guest_masking.py` (new) - 15 tests: mask unit tests, real-middleware guest/vip/invalid-cookie endpoint tests, GUEST-02 display-only proofs, AST import/write guard, guest-surface security guards.
- `backend/tests/test_pool_hub.py` - fixture rows carry `name`; `expected_keys` += `name`; `_make_client` binds a VIP principal (endpoint regressions expect 明文); empty-hub expectation includes `mode: "vip"`.

## Decisions Made

- Masking lives ONLY in `guest_masking.py` (imports no engine/persistence/execution module, no write path) and is invoked at the DTO boundary in `pool.py` — never in the service layer, never in the engine (GUEST-02, T-19-05).
- `mode` is `"vip"` iff a valid session resolves a `reviewer_principal`; `"guest"` otherwise. Never read from client input (T-19-02).
- Guest rows **omit** `open_gap` entirely (ROADMAP letter: guests see only 涨跌幅 + 概念板块; CONTEXT D-04) rather than nulling it.
- The guest surface is a `frozenset` of exactly two GET endpoints plus a GET-only guard so any future widening fails the suite (T-19-03).
- `name` projection returns `""` (never `None`) when a persisted row lacks `name`, keeping the DTO JSON-clean.

## Deviations from Plan

### Auto-fixed Issues

**1. [Plan file-boundary rebalancing] pool_hub name projection + test_pool_hub.py updates pulled into Task 1**
- **Found during:** Task 1 (tracer) — Task 1's own endpoint spec requires `name` present in the VIP response ("real code/name/open_gap present"), and the plan's fixture note says "so the projection has a name to mask".
- **Issue:** The plan lists `pool_hub.py` and `test_pool_hub.py` under Task 2, but Task 1's VIP/guest endpoint tests and the mask unit tests need the `name` projection to exist and the existing endpoint regressions need a VIP principal binding (unauthenticated is now guest-masked by default).
- **Fix:** Included the one-line `name` projection in `pool_hub.py` and the corresponding `test_pool_hub.py` fixture/expected_keys/VIP-binding/empty-hub-mode updates in the Task 1 commit. Task 2 then commits the GUEST-02 display-only proofs + AST guard; Task 3 commits the security guards.
- **Files modified:** pool_hub.py, test_pool_hub.py (in the Task 1 commit)
- **Verification:** `tests/test_guest_masking.py` + `tests/test_pool_hub.py` = 32 passed after Task 3.
- **Committed in:** `04b0c2b`

**2. [Rule 1 - Bug] Duplicated import lines after stale-anchor edit remap**
- **Found during:** Task 2 — two `_edit` remaps duplicated `import copy/json/ast` and the `MASKED_IDENTITY` import.
- **Issue:** Cosmetic duplication in `test_guest_masking.py` import block.
- **Fix:** Rewrote the import block to the canonical sorted set; no functional impact.
- **Files modified:** tests/test_guest_masking.py
- **Verification:** suite green.
- **Committed in:** `5e5604d`

---

**Total deviations:** 1 rebalance + 1 cosmetic fix
**Impact on plan:** No scope creep; both changes keep the plan's own Task 1 acceptance criteria satisfiable and the suite green.

## Issues Encountered

- Starlette `TestClient` per-request `cookies=` kwarg emits a DeprecationWarning; tests were switched to `client.cookies.set(...)` to keep the suite warning-clean.
- Cross-test module import (`from test_pool_hub import ...`) is unreliable under this project's `--import-mode=importlib`; `test_guest_masking.py` carries its own hermetic copies of the fixtures (same shape/values) instead.
- Full-suite run: `1414 passed, 2 skipped, 1 failed`. The single failure — `tests/advanced/test_production_host.py::test_spawned_governed_backtest_completes_split_evidence_within_budget` (`resource_limited` vs `completed`) — is an advanced-sandbox resource-budget test unrelated to guest masking; logged to `deferred-items.md` per the executor scope boundary.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **19-02 (frontend) can proceed**: the API contract is documented above (mode field, masked-fields list, guest vs VIP column sets, name projection). The frontend must consume `mode` server-side and render `******` verbatim, hiding 开盘涨幅 in guest mode. See 19-UI-SPEC for the exact column sets and copy.
- The guest surface is already reachable cookie-less in the browser for the pool page data (`/api/pool/hub`, `/api/screener/strategies`).
- **Known stub:** none — masking is fully wired; `name` may be `""` for rows whose persisted result lacks a name (frontend renders `—` per 19-UI-SPEC).

---
*Phase: 19-guest-access*
*Completed: 2026-08-04*

## Self-Check: PASSED

- All 6 plan source/test files + SUMMARY exist on disk (verified via `[ -f ]`).
- Task commits `04b0c2b`, `5e5604d`, `fcf2a9e` present in `git log`.
- Plan verify command green: `pytest tests/test_guest_masking.py tests/test_pool_hub.py -q` → **32 passed**.
