---
status: resolved
trigger: "G-05-97 — Current frontend TypeScript verification reports two TS2339 errors in ThesisPanel."
created: 2026-07-27T00:50:00.1319707+08:00
updated: 2026-07-27T08:38:06.9724045+08:00
---

## Current Focus

hypothesis: confirmed — `ChecksTable` narrows `ThesisCheck[]` to a duplicated inline element type that omits the canonical numeric `version` field; commit `6a69fbba` added `check.version` rendering without synchronizing that local annotation
test: complete
expecting: complete
next_action: complete — the component now consumes the canonical `ThesisCheck` contract and TypeScript plus browser verification passed
bug_class: Bohrbug
candidate_causes:
  - code: duplicated inline `ChecksTable` element type omitted `version` while render code accessed it
  - config/environment: stale TypeScript cache, compiler-version behavior, or uncommitted source divergence
and_gate: no — the committed source mismatch alone deterministically produces both diagnostics; config/environment alternatives were disproved

## Symptoms

expected: Stock Analysis 可完成带估值区间和类型化假设的不可变 Thesis 生命周期，显示每项检查结果、仅待审的人工确认、冲突恢复及完整历史。
actual: tsc --noEmit fails at frontend/src/components/analysis/ThesisPanel.tsx:570 because check.version does not exist on the inferred check type (two TS2339 occurrences at columns 1811 and 1846).
errors: TypeScript TS2339: Property 'version' does not exist on type ...
reproduction: Test 97 in .planning/phases/05-optional-enhancements/05-UAT.md; run frontend node_modules/.bin/tsc.cmd --noEmit --pretty false -p tsconfig.json.
started: Discovered during current UAT rerun.

## Eliminated

- hypothesis: the canonical `ThesisCheck` DTO or server page contract lacks `version`, so the UI render is ahead of the API.
  evidence: `ThesisCheck` requires `version: number` and `phase5Api.thesisChecks` returns `ResourcePage<ThesisCheck>`.
  timestamp: 2026-07-27T00:57:05+08:00

- hypothesis: a stale TypeScript cache, generated declaration, or local uncommitted edit creates an environment-only failure.
  evidence: `tsc --noEmit` deterministically reports the same two source errors; the source file is clean; blame and introducing commit contain the mismatch directly.
  timestamp: 2026-07-27T01:01:25+08:00

## Evidence

- timestamp: 2026-07-27T00:53:10+08:00
  checked: code graph and current `ThesisPanel.tsx`
  found: `ThesisPanel` stores checks as `ThesisCheck[]` and passes filtered checks to `ChecksTable`; `ChecksTable` redeclares an inline structural check type lacking `version`, while its row renderer accesses `check.version` in both `typeof check.version` and template interpolation.
  implication: the failure is localized to an inconsistent view-component prop contract, not to the state collection or runtime data filtering.

- timestamp: 2026-07-27T00:53:10+08:00
  checked: common bug-pattern map
  found: the symptom matches deterministic Data Shape / API Contract and Type categories.
  implication: classify as a Bohrbug and test contract drift before environment or asynchronous alternatives.

- timestamp: 2026-07-27T00:55:15+08:00
  checked: `.planning/debug/knowledge-base.md`
  found: no project debug knowledge base exists.
  implication: there is no prior known-pattern resolution to prioritize; proceed from direct evidence.

- timestamp: 2026-07-27T00:55:15+08:00
  checked: exact Test 97 command `frontend/node_modules/.bin/tsc.cmd --noEmit --pretty false -p tsconfig.json`
  found: deterministic exit 1 with exactly two TS2339 diagnostics at `ThesisPanel.tsx(570,1811)` and `(570,1846)`; both name `version` as absent from the inline structural check type.
  implication: this is a reproducible Bohrbug; no flaky/environmental behavior is involved, and SBFL is inapplicable because the failing signal is the compiler rather than a per-test coverage spectrum.

- timestamp: 2026-07-27T00:57:05+08:00
  checked: canonical `ThesisCheck` and `phase5Api.thesisChecks` contracts in `frontend/src/lib/phase5Api.ts`
  found: `ThesisCheck` declares required `version: number`; `thesisChecks` returns `ResourcePage<ThesisCheck>`.
  implication: the API/DTO contract supports the rendered field. The narrower inline `ChecksTable` type—not the canonical DTO—is the divergence point.

- timestamp: 2026-07-27T00:59:20+08:00
  checked: current numbered source, scoped git diff, and blame for lines 568–570
  found: line 568's inline prop type omits `version`; line 570 reads it twice. The file has no working-tree diff, and blame attributes line 570 to commit `6a69fbba`.
  implication: the error is present in committed source and is not caused by an uncommitted edit, stale compiler cache, or generated declaration mismatch.

- timestamp: 2026-07-27T00:59:20+08:00
  checked: UAT Test 97 and `.planning/STATE.md`
  found: Test 97 records this exact issue as major; project state still describes Phase 05 as complete after a 370/370 final gate.
  implication: the current rerun found a verification-coverage gap in the prior final gate; the Phase 05 completion claim is contradicted by the current authoritative compiler result.

- timestamp: 2026-07-27T01:01:25+08:00
  checked: introducing commit `6a69fbba` (`feat(05-36): render Thesis ledger rows from self-owned identity`)
  found: the same commit added required `version` identity to the canonical DTO and changed the checks-table rendering to `typeof check.version === 'number' ? ...`, but left the pre-existing duplicated inline `ChecksTable` element type unchanged.
  implication: the exact mechanism is an implementation-time contract synchronization omission at a local type boundary. It does not require a second config/data/environment condition (AND-gate: no).

- timestamp: 2026-07-27T01:03:10+08:00
  checked: `.planning/phases/05-optional-enhancements/05-36-SUMMARY.md`
  found: Phase 05-36 verified only four targeted backend tests and two targeted Playwright tests; its recorded verification evidence contains no `tsc --noEmit` or equivalent full frontend compile.
  implication: browser fixtures could exercise the runtime path while Vite transpiled TypeScript without enforcing this property check; the missing full typecheck gate allowed the committed TS2339 regression to survive.
## Resolution

root_cause: "Commit `6a69fbba` introduced self-owned numeric version rendering in `ChecksTable`, but `ChecksTable` retained a duplicated inline check element type that omits `version`. TypeScript therefore narrows each row away from the canonical `ThesisCheck` contract and rejects both `check.version` accesses, despite `ThesisCheck.version` being required and `phase5Api.thesisChecks` returning `ResourcePage<ThesisCheck>`."
fix: "Commit `b1b75e7` replaced the duplicated inline row type with the canonical `ThesisCheck` contract."
verification: "The repository TypeScript build passed, targeted Thesis Playwright coverage passed, and the final fixture-browser report passed all 33 tests in aggregate run `a8bc8b24-efde-403b-888a-8fb0058ebf18`."
files_changed: ["frontend/src/components/analysis/ThesisPanel.tsx"]
