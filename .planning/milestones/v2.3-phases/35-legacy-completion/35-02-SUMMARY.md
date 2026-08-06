# 35-02 SUMMARY — LG-04 WATCH-04 batch-add extension (e2e + snapshots)

Phase 35 (legacy completion) · Plan 35-02 · ExecutorP3502 · 2026-08-06
Status: **COMPLETE** — all acceptance criteria met, suite green, Watchlist.tsx zero-touch proven.

## Deliverables

| Artifact | Change |
|---|---|
| `frontend/src/components/pool-hub/StockListTable.tsx` | WATCH-04 checkbox column, **VIP-only**: header 全选 (`aria-checked` three-state true/mixed/false + indeterminate visual via ref/`el.indeterminate`), row checkbox `选择{code}` (join key = full-suffix symbol, same as star). Guest renders **zero controls** (游客零控件契约). Cross-resonance left border moved to checkbox cell on VIP rows so the row-edge marker keeps its visual position. `GUEST_COLUMNS`/`VIP_COLUMNS` untouched. New props `selection` / `onToggleSelection` / `onToggleSelectAll`. |
| `frontend/src/pages/PoolHubPage.tsx` | `selected: Set<string>` state + **clear-on-change** in every handler (strategy select / filter change / clear filter / date change / watchlistOnly toggle — no stale selection across views, T-35-02-05). `handleBatchAdd` scope = `[...selected]` **defensively intersected with filteredRows**; empty → early return (no request, no toast). Batch button `disabled={isPending || selected.size === 0}`, `aria-label="批量加自选"` stable, hidden under watchlistOnly (D6). Select-all toggle derives from visible rows. |
| `frontend/e2e/pool-hub.spec.ts` | 3 new WATCH-04 tests (勾选单行 body=选中行 保序 + toast / 全选可见行 + 空选禁用 + set-compare / 切换策略清空选中) + POOL-03 guard: `ALLOWED_RE` += `选择\d{6}|全选` + parallel checkbox-name loop + guest zero-checkbox assertion + watchlistOnly-hides-button assertion in existing WATCH-04 test + accessibility-test code-cell locator made text-based. |
| 3 VIP snapshots | Intentionally regenerated (checkbox column changed VIP table visuals): `pool-table-resonance`, `pool-table-filter-active`, `pool-vip-plaintext`. Guest/other snapshots untouched. |

## Commits (all 35-02 work, in order)

1. `0ccc61d` — `feat(35-02): WATCH-04 batch selection — VIP checkbox column + selection scope` (StockListTable + PoolHubPage)
2. `7f1636d` — `test(35-02): WATCH-04 selection e2e — 3 new tests + POOL-03 guard registration` (pool-hub.spec.ts)
3. `45e47bc` — `test(35-02): regenerate 3 VIP snapshots for WATCH-04 checkbox column` (3 PNGs)

Sibling commits interleaved in history (not ours): `f1bcaf2`, `ba5abe0` (35-01 backend/tests + SUMMARY).

## Verification record

- `npx tsc -b --pretty false` — exit 0 (after Tasks 1+2).
- `npm run build` (tsc -b + vite build) — **green** (chunk-size warning pre-existing, not from this change).
- `npx playwright test e2e/pool-hub.spec.ts --project=desktop-chromium` (CI=1, webServer fresh vite :4173) — **43/43 passed** (was 38 before this plan; +3 new WATCH-04 tests + 2 snapshot tests, all green, maxDiffPixelRatio 0.02).
- Snapshot regen run: `--update-snapshots -g "captures visual evidence"` — regenerated **exactly 3 VIP PNGs** (`git status` after run showed only those 3 modified; no guest/other rewrites, W-7 satisfied).
- Zero-touch proof — final `git status --short`:
  ```
  M frontend/src/pages/Watchlist.tsx
  ```
  Exactly **one** unstaged change, the pre-existing user edit; `frontend/src/pages/Watchlist.tsx` was never read or modified by this executor. All 35-02 files are committed.

## Snapshot review record (T-35-02-02)

Vision-capable model unavailable (`inspect_image` rejected: no vision role), so the review was performed **programmatically** on the 3 regenerated PNGs vs their `HEAD` predecessors:

- New dimensions ≈ old (resonance/vip-plaintext 583×1142 vs 582×1142; filter-active 154×1142 vs 153×1142) — width stable, no reflow.
- Left 56px strip: bright-pixel density rose ~3× (0.034→0.113 resonance/vip; 0.068→0.108 filter-active) — checkbox outlines added.
- Checkbox-band detection (contiguous bright rows in left strip): NEW resonance = 14 bands (header + 12 visual rows + 1), NEW filter-active = 3 bands, NEW vip-plaintext = 14 bands — regular ~38px intervals matching header + row height; OLD snapshots had **0** checkbox bands. → header 全选 + per-row 选择{code} checkboxes confirmed present.
- Body right of the checkbox column: bright density unchanged (0.0206 vs 0.0195; 0.0254 vs 0.0259) — table content columns intact, no clipping/overlap.

Verdict: checkbox column present, narrow (≈56px), body layout intact → snapshots intentionally committed.

## Deviations from plan (all within plan intent)

1. **Existing WATCH-04 e2e test updated** to select-all before clicking 批量加自选 — inherent to the new `scope=selected` + empty-selection-disabled semantics (old test clicked an initially-disabled button and timed out). Plan anticipated this test's update (watchlistOnly assertion added in the same edit).
2. **Accessibility test code-cell locator** changed from `getByRole('cell', { name: /688981/ }).first()` to text-content filter — the new checkbox cell's accessible name (选择688981) matched the old locator first.
3. **Header select-all toggled via `.click()`** in tests instead of `.check()`/`.uncheck()` — `check()` is a no-op when already checked (no change event), so toggle-off would never fire.
4. **Cross-resonance left border** moved from the code `<td>` to the checkbox `<td>` on VIP rows — keeps the accent row-edge marker at the row's left edge (guest unchanged).
5. **Snapshot commit split** from the e2e commit (e2e committed before regen; plan suggested same-change). Both landed before the full-suite run — no CI-red window.
6. **Visual review done via pixel analysis** instead of an image model (W-7's "人工审查" adapted; evidence above).

## Warnings applied

- **W-6**: `useWatchlistBatchAdd` consumed from `frontend/src/lib/useSharedMutations.ts` (already imported by PoolHubPage; no change needed — its double-key invalidation QK.watchlist + QK.watchlistEnriched() covers the batch flow).
- **W-7**: `-g "captures visual evidence"` matched both backstop tests → post-regen `git status` verified **exactly 3 VIP PNGs** modified; none reverted because none were non-VIP rewrites.
- **W-8**: full runs executed with `CI=1` (fresh webServer, `reuseExistingServer` disabled; port 4173 verified free before first run).

## Threat model closure

- T-35-02-01 (guard bypass): mitigated — ALLOWED_RE + checkbox-name loop committed with the new controls.
- T-35-02-02 (unreviewed snapshot regen): mitigated — review record above, intentional commit.
- T-35-02-03 (guest gets controls): mitigated — checkbox column `mode === 'vip'` only; guest e2e asserts table checkbox count == 0.
- T-35-02-04 (Watchlist.tsx touched): mitigated — git status proof above.
- T-35-02-05 (stale selection): mitigated — clear-in-handler + defensive intersect; e2e 切换策略清空选中 locks it.
- T-35-02-06 (CI unreproducible): mitigated — installShell full-mock + webServer auto vite :4173, CI=1 runs.

## Files touched by this plan

`frontend/src/components/pool-hub/StockListTable.tsx`, `frontend/src/pages/PoolHubPage.tsx`, `frontend/e2e/pool-hub.spec.ts`, `frontend/e2e/pool-hub.spec.ts-snapshots/pool-table-resonance-desktop-chromium-linux.png`, `frontend/e2e/pool-hub.spec.ts-snapshots/pool-table-filter-active-desktop-chromium-linux.png`, `frontend/e2e/pool-hub.spec.ts-snapshots/pool-vip-plaintext-desktop-chromium-linux.png` — all committed; no overlap with 35-01 (backend/tests) or 35-03 (docs/).
