---
status: resolved
trigger: "G-05-99 — Windows optional-host lifespan cannot import the Linux-only resource module."
created: 2026-07-27T00:00:00+08:00
updated: 2026-07-27T08:38:06.9724045+08:00
---

## Current Focus

bug_class: bohrbug
hypothesis: confirmed — Windows CPython lacks resource, and sandbox.py imports it before its Linux-only code is gated; this single import aborts all real-host startups before optional-module isolation
test: completed exact reproduction, differential imports, and a one-variable sentinel-resource counterfactual
expecting: observed — bypassing only module resolution lets sandbox import and makes the existing Windows platform guard return all ten isolation proof fields false
next_action: complete — resource loading is guarded at the Linux boundary and Windows plus Linux regressions passed

reasoning_checkpoint:
  hypothesis: "The module-level import resource in sandbox.py causes the Windows lifespan failure because Python for Windows does not provide that POSIX module, and the import is reached before platform gating or optional-host installation."
  confirming_evidence:
    - "sandbox.py:7 imports resource unconditionally, while the only platform guard is later inside LinuxIsolationLauncher.capability_probe at lines 66-69."
    - "main.py:196 imports both sandbox classes unconditionally inside lifespan, whereas the optional-module host is not built until lines 619-628."
  falsification_test: "If resource or app.advanced.sandbox imports successfully on this Windows interpreter, or if the prescribed host failures reach assertions without this traceback, the hypothesis is false."
  fix_rationale: "Diagnosis-only; any eventual fix must move platform-specific resource access behind a Linux boundary while preserving a fail-closed unavailable launcher on Windows, rather than weakening isolation."
  blind_spots: "No production fix was applied in diagnose-only mode, so the complete lifespan has not been exercised past this boundary; the sentinel probe rules in this cause but does not exclude a later independent Windows portability defect."
  candidate_causes:
    - "code: unconditional top-level import of a platform-specific module precedes the existing sys.platform gate and optional-host isolation."
    - "environment: Windows CPython intentionally lacks the POSIX resource module, exposing the code's portability assumption."
    - "config/data: optional-module enablement and Thesis records cannot affect Python module resolution at this earlier startup point."
  and_gate: "yes — the observed failure requires both the unconditional code import and a Windows runtime without resource; neither optional-host configuration nor data contributes."

## Symptoms

expected: 股票 Analysis 固定提供 Thesis 和 Forecast 页签；Portfolio、原有页签顺序与内容、对象授权及各可选模块的局部故障隔离保持不变。
actual: On Windows the complete optional-host lifespan cannot start: backend/app/advanced/sandbox.py imports 'resource' unconditionally, causing ModuleNotFoundError before 20 host assertions execute.
errors: "ModuleNotFoundError: No module named 'resource'; backend/app/main.py:196 imports app.advanced.sandbox."
reproduction: "Test 99 in .planning/phases/05-optional-enhancements/05-UAT.md; uv run --isolated --frozen --extra dev pytest -p no:cacheprovider tests/theses/test_api.py tests/test_phase5_optional_host.py -q."
started: Discovered during current UAT rerun on Windows; 8 standalone Thesis tests pass and 20 host tests fail at shared startup.

## Eliminated

- hypothesis: Thesis route, paging, authorization, or persisted data causes Test 99
  evidence: all 8 tests in tests/theses/test_api.py pass in the same isolated run, and app.theses.api imports successfully in a fresh Windows interpreter.
  timestamp: 2026-07-27T00:20:00+08:00
- hypothesis: a particular Shadow/Thesis/Forecast enablement combination or module-local readiness failure causes the host failures
  evidence: all eight combinations, including the `none` combination, fail at the identical main.py:196 -> sandbox.py:7 import boundary before build_and_install_optional_module_host runs.
  timestamp: 2026-07-27T00:20:00+08:00
- hypothesis: missing dependency installation or uv extra selection omitted a third-party package named resource
  evidence: the interpreter reports sys.platform=win32; Python's resource API is POSIX-specific, the project uses it as a standard-library module, and a fresh isolated environment reproduces the same absence.
  timestamp: 2026-07-27T00:21:00+08:00
## Evidence

- timestamp: 2026-07-27T00:04:00+08:00
  checked: prior debug knowledge
  found: MemPalace debug recall was unavailable and .planning/debug/knowledge-base.md does not exist.
  implication: there is no known-pattern resolution to assume; diagnosis must rest on current repository and runtime evidence.
- timestamp: 2026-07-27T00:05:00+08:00
  checked: codebase knowledge graph for sandbox and optional-host startup
  found: the graph locates app.main.lifespan at backend/app/main.py:93-652, LinuxIsolationLauncher and sandbox service in backend/app/advanced/sandbox.py, and the real host fixture in backend/tests/test_phase5_optional_host.py:269-339.
  implication: the relevant startup, platform-specific launcher, and reproduction boundary are identified without relying on filename inference.
- timestamp: 2026-07-27T00:09:00+08:00
  checked: backend/app/advanced/sandbox.py in full
  found: line 7 executes `import resource` at module load; resource is used only by LinuxIsolationLauncher._limits at lines 199-205 and its embedded Linux probe script. The launcher's platform guard at lines 66-69 is unreachable until module import succeeds.
  implication: platform denial exists at runtime but is placed after the platform-specific import, so it cannot protect Windows startup.
- timestamp: 2026-07-27T00:10:00+08:00
  checked: backend/app/main.py lifespan and optional-host ordering
  found: lifespan unconditionally imports CustomStrategySandboxService and LinuxIsolationLauncher at line 196 and instantiates them at lines 325-329; independently isolated Phase 05 optional-host construction occurs later at lines 619-628.
  implication: a sandbox import exception escapes before Shadow/Thesis/Forecast readiness isolation is entered, making every real-host combination fail together.
- timestamp: 2026-07-27T00:11:00+08:00
  checked: GSD common patterns and fault-localization prerequisites
  found: the symptom matches Import/Module plus Environment/Config; the failure is deterministic under one OS/runtime. Per-test execution coverage is not available for this suite, so SBFL/Ochiai is skipped.
  implication: classify as a Bohrbug and use deterministic reproduction plus differential import probes.
- timestamp: 2026-07-27T00:19:00+08:00
  checked: exact Test 99 command on Windows
  found: pytest reports `8 passed, 20 failed`; every failing real-host test terminates at app/main.py:196 importing app.advanced.sandbox, then sandbox.py:7 raises `ModuleNotFoundError: No module named 'resource'`.
  implication: the failure is deterministic, shared startup infrastructure; no optional-host assertion is reached.
- timestamp: 2026-07-27T00:20:00+08:00
  checked: fresh isolated direct import probes
  found: sys.platform is `win32`; importing `resource` and `app.advanced.sandbox` fails with the same ModuleNotFoundError, while importing `app.theses.api` succeeds.
  implication: the causal boundary is the sandbox module's platform import, not Thesis or test fixture data.
- timestamp: 2026-07-27T00:21:00+08:00
  checked: existing cross-platform resource-limit pattern in backend/app/advanced/governed_runner.py
  found: lines 18-21 already guard `import resource` with ImportError and assign None; its runtime path explicitly fails closed when resource is unavailable.
  implication: the repository already has a proven design convention for making POSIX resource limits import-safe without enabling unsupported execution.
- timestamp: 2026-07-27T00:24:00+08:00
  checked: counterfactual with only `sys.modules['resource']` replaced by a nonfunctional sentinel
  found: app.advanced.sandbox imports successfully, and LinuxIsolationLauncher.capability_probe on win32 returns all ten proof fields false without accessing the sentinel.
  implication: the missing module is causal rather than merely correlated; the existing platform guard already supplies the intended fail-closed Windows behavior once import-time access no longer preempts it.
## Resolution

root_cause: "AND-gated platform/import defect: backend/app/advanced/sandbox.py unconditionally imports the POSIX-only `resource` module at module load, and backend/app/main.py unconditionally imports that sandbox module during every lifespan on Windows. This occurs before LinuxIsolationLauncher.sys.platform gating and before the Phase 05 optional-host isolation boundary, so Windows startup aborts globally instead of leaving Linux sandbox execution unavailable locally."
fix: "Commit `383a843` guarded the platform-specific resource import and preserves fail-closed capability evidence when the module is unavailable."
verification: "The final Phase 05 run passed 169 Windows tests and 449 native-Linux tests, including optional-host startup and Linux process/resource contracts, within aggregate run `a8bc8b24-efde-403b-888a-8fb0058ebf18`."
files_changed: ["backend/app/advanced/sandbox.py"]
