---
status: resolved
trigger: "G-05-96 — Phase 5 Playwright scenario 1 cannot see the Shadow heading."
created: 2026-07-27T00:49:57.9429745+08:00
updated: 2026-07-27T08:38:06.9724045+08:00
---

## Current Focus

bug_class: bohrbug
hypothesis: confirmed — scenario 1 exhausts one 30-second test budget by serializing five availability cases and ten full navigations; Windows Vite cold navigation latency moves a later loop iteration's first assertion past the deadline, so requireSurface reports the Shadow heading as the timeout site even though the heading renders correctly
test: source inspection, default-timeout reproduction with trace timing, and a timeout-only 120-second counterfactual
expecting: satisfied — the first iteration visibly renders the heading, and the longer-budget trace advances through all five correct availability payloads instead of failing because the heading is absent
next_action: complete — availability cases were split into independent Playwright tests and the final 33-test fixture suite passed
reasoning_checkpoint:
  hypothesis: five serialized two-page navigation cycles share the default 30-second test timeout; observed Windows Vite cold navigation latency pushes a later loop iteration beyond that shared deadline and surfaces a misleading timeout at the otherwise-present Shadow heading
  confirming_evidence:
    - the first iteration trace visibly contains the exact production heading
    - the trace spends about 12 seconds reaching the first Backtest assertion and about 11 seconds reaching the second
    - with only the timeout raised, the trace reaches distinct correct availability payloads for all five matrix cases, including the fifth all-unavailable Backtest navigation
  falsification_test: a missing heading during a single isolated Backtest iteration or under the longer budget would disprove the shared-timeout explanation; neither occurs
  fix_rationale: generate one Playwright test per availability case so each case receives a fresh Page and timeout budget; alternatively set a justified per-test timeout, but splitting preserves failure locality and avoids masking slowness
  blind_spots: the original UAT trace is unavailable, so line-number attribution is compared against a fresh current-state reproduction; production-host behavior is not implicated by this fixture-only mechanism
  candidate_causes:
    - code/test: scenario 1 places five independent availability cases and ten full navigations inside one test callback
    - config/environment: one default 30-second Playwright timeout covers five Windows Vite availability cases and ten full navigations, while observed cold navigations take roughly 11-12 seconds
    - data: availability payloads are well formed and differ correctly across the longer-budget trace
  and_gate: yes — the reported line-670 failure requires the serialized matrix to share one 30-second budget and the Windows Vite navigation latency to consume that budget; neither the heading source nor availability data is defective

## Symptoms

expected: Backtest 页面完整呈现不可变的导入、证据、候选、IS/OOS 评估和保留流程，并且没有任何实盘或激活权限入口。
actual: Phase 5 Playwright scenario 1 timed out after 30 seconds because the exact heading 'Shadow 成交证据与策略候选' never became visible.
errors: Playwright spec frontend/e2e/phase5-optional-enhancements.spec.ts:670 via requireSurface at :544; 25 tests total, 24 passed, 1 failed.
reproduction: Test 96 in .planning/phases/05-optional-enhancements/05-UAT.md
started: Discovered during UAT on Windows with Vite at 127.0.0.1:4173.

## Eliminated

- hypothesis: the production Shadow heading is absent, renamed, or conditionally hidden by module availability
  evidence: the exact h2 exists in ShadowAccount, is outside the capability gate, and is visible in the first iteration's page snapshot
  timestamp: 2026-07-27T00:56:34.2168047+08:00
- hypothesis: repeated page.route registration leaves the first all-available handler active for later matrix cases
  evidence: the 120-second counterfactual trace records distinct correct response hashes for all-available, shadow-unavailable, thesis-unavailable, forecast-unavailable, and all-unavailable payloads
  timestamp: 2026-07-27T00:56:34.2168047+08:00
- hypothesis: malformed availability fixture data prevents ShadowAccount from rendering
  evidence: all five longer-budget /api/optional-modules payloads are valid and the Shadow heading is rendered before capability-dependent content
  timestamp: 2026-07-27T00:56:34.2168047+08:00

## Evidence

- timestamp: 2026-07-27T00:50:59.4559240+08:00
  checked: .planning/debug/knowledge-base.md
  found: no project debug knowledge base exists
  implication: there is no known-pattern candidate to test first
- timestamp: 2026-07-27T00:50:59.4559240+08:00
  checked: literal search for the exact heading
  found: the exact string exists in frontend/src/pages/backtest/ShadowAccount.tsx:406 and in the Playwright contracts; it is not absent or text-mismatched in production source
  implication: a simple copy drift hypothesis is contradicted
- timestamp: 2026-07-27T00:50:59.4559240+08:00
  checked: Backtest and ShadowAccount render path
  found: Backtest initializes activeTab to strategy and unconditionally mounts ShadowAccount in that tab; ShadowAccount renders its h2 before capability availability gates
  implication: API availability or Shadow data-query failure cannot by itself hide the heading once Backtest renders
- timestamp: 2026-07-27T00:50:59.4559240+08:00
  checked: Playwright scenario 1
  found: the failure assertion is the first post-navigation DOM assertion in a loop over five availability combinations
  implication: the reproduction can distinguish a page-render failure from later optional-module behavior
- timestamp: 2026-07-27T00:51:30.5535964+08:00
  checked: SBFL preconditions
  found: the Playwright suite has passing and failing tests but no configured per-test coverage artifact
  implication: SBFL is skipped because an Ochiai spectrum cannot be computed
- timestamp: 2026-07-27T00:51:30.5535964+08:00
  checked: first isolated reproduction command through pnpm exec
  found: pnpm aborted before Playwright because the local policy rejects ignored esbuild build scripts
  implication: this run neither confirms nor refutes the product bug; the already-installed direct Playwright shim is required to remove the package-manager confounder
- timestamp: 2026-07-27T00:52:15.0000000+08:00
  checked: direct Playwright invocation
  found: Playwright itself starts, but its configured webServer command still calls pnpm exec vite and exits before the test; direct Vite invocation remains alive until the bounded shell timeout
  implication: the product scenario must be run with PHASE1_BASE_URL against a manually launched Vite process to isolate the application from the local pnpm hook
- timestamp: 2026-07-27T00:53:38.3539157+08:00
  checked: isolated current-state scenario 1 reproduction and Playwright trace
  found: the first Backtest iteration renders region and heading "Shadow 成交证据与策略候选"; the run later times out, and the final screenshot is blank during a subsequent full navigation
  implication: the production heading is present and visible; the reported locator is where the shared scenario budget expires, not the missing implementation surface
- timestamp: 2026-07-27T00:53:38.3539157+08:00
  checked: trace action timing
  found: first page.goto('/backtest') starts at monotonic 2246 and the heading assertion begins at 14207 (about 12 seconds); the second Backtest navigation starts at 25516 and its heading assertion begins at 36214 (about 11 seconds), already beyond one 30-second test budget
  implication: five serialized availability iterations cannot reliably fit the configured test timeout on this Windows Vite path
- timestamp: 2026-07-27T00:53:38.3539157+08:00
  checked: /api/optional-modules network responses across the first two loop iterations
  found: both responses use the same SHA and all modules are available, even though the second iteration passes shadow=false
  implication: superseded by the longer trace — these are the Backtest and Stock Analysis requests from the first all-available iteration, not two different matrix iterations
- timestamp: 2026-07-27T00:56:34.2168047+08:00
  checked: 120-second timeout-only counterfactual trace
  found: the run progresses through correct response hashes for all five availability configurations; the fifth all-unavailable Backtest request occurs around monotonic 68 seconds
  implication: raising only the budget removes the apparent heading blockage and disproves stale fixture state; the matrix intrinsically exceeds the default 30-second budget on this path
- timestamp: 2026-07-27T00:56:34.2168047+08:00
  checked: workspace diff and local server cleanup
  found: only the specified debug session file is new; production and test files are unchanged, and no diagnostic Vite listener remains on port 4173
  implication: the diagnosis is based on observation only and leaves the project implementation untouched

## Resolution

root_cause: frontend/e2e/phase5-optional-enhancements.spec.ts scenario 1 serializes five availability configurations and ten full Vite navigations inside one Playwright test while inheriting the global 30-second timeout. On Windows, observed cold navigations consume about 11-12 seconds each, so a later iteration begins its Shadow heading assertion only after the shared deadline; line 670 is the timeout location, not a missing production heading.
fix: commit `9b7c75c` parameterized the five availability cases into independent Playwright tests so each case receives an isolated page and timeout budget.
verification: the final fixture-browser report in run `a8bc8b24-efde-403b-888a-8fb0058ebf18` passed all 33 tests, including the split availability matrix, and the aggregate Phase 05 gate passed 652/652.
files_changed: ["frontend/e2e/phase5-optional-enhancements.spec.ts"]
