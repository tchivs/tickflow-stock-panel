---
phase: 05-optional-enhancements
fixed_at: 2026-07-26T18:30:19Z
review_path: .planning/phases/05-optional-enhancements/05-REVIEW.md
iteration: 2
findings_in_scope: 4
fixed: 4
skipped: 0
remaining_after_rereview: 5
status: partial
---

# Phase 05: Code Review Fix Report

**Fixed at:** 2026-07-26T18:30:19Z
**Source review:** `.planning/phases/05-optional-enhancements/05-REVIEW.md`
**Iteration:** 2

**Summary:**
- Findings in scope: 4
- Fixed: 4
- Skipped: 0
- Final iteration 3 re-review: 4 critical and 1 warning remain

## Fixed Issues

### CR-01: Sandbox 仍可经允许模块恢复任意导入和 `Popen`

**Files modified:** `backend/app/advanced/sandbox.py`, `backend/tests/advanced/test_sandbox.py`
**Commit:** 04e2de9
**Applied fix:** 拒绝 `getattr`/`vars` 等运行时反射入口及所有 dunder 名称和属性，阻断允许模块经 `__builtins__`、`__dict__` 或动态属性取回未声明模块和进程构造器；保留既有有界超时回收。新增 `json.__builtins__`、`getattr(..., "Popen")` 和 `vars(json)` 回归。

### CR-02: Retry 预验证失败会留下 queued lineage 和 artifact

**Files modified:** `backend/app/forecast/service.py`, `backend/app/forecast/input.py`, `backend/tests/forecast/test_runner.py`, `backend/tests/forecast/test_input.py`
**Commit:** 42a8fe6
**Applied fix:** `retry_job()` 先读取并校验 terminal source，再完成 catalog、governed input 和 fingerprint 预验证，只有成功后才创建 queued retry；不匹配及仓储创建失败会回收未绑定输入。freezer 在 artifact 提升后构造完整身份失败时也会删除该 invocation-owned namespace。新增 fingerprint、catalog、freezer 失败的无 orphan/无泄漏回归。
**Verification status:** fixed: requires human verification

### CR-03: Scanner 初始化失败遗失 dispatcher 所有权

**Files modified:** `backend/app/optional_modules.py`, `backend/tests/test_phase5_optional_host.py`
**Commit:** b86437b
**Applied fix:** `mark_unavailable()` 在移除 runtime bundle 时调用对应 factory close；Forecast dispatcher 延迟到 recovery、scanner 注册和 readiness 全部成功后启动。dispatcher 启动失败会移除 scanner job 并回收 bundle。新增 scanner 失败后线程不存活、queued job 未处理及重复 shutdown 不二次关闭的回归。
**Verification status:** fixed: requires human verification

### WR-01: Linux bootstrap 测试替身在 Windows 无法构造

**Files modified:** `backend/tests/advanced/test_sandbox.py`
**Commit:** 9cf5e73
**Applied fix:** 对 Windows 可能不存在的 `os.chroot` 和 `os.execve` 使用基于模块对象、`raising=False` 的 monkeypatch，同时保留原 mount/topology/execve 断言。

## Final Re-review

Iteration 3/3 did not converge to a clean review. The latest `05-REVIEW.md`
records four critical findings and one warning that require a new gap plan:

- indirect builtin aliasing can still cross the custom-strategy capability boundary;
- Forecast retry terminal-state definitions drift between service and repository;
- retry replay and post-create failures can still leave artifacts or queued lineage;
- dispatcher close timeout can relinquish ownership of a live worker;
- Forecast runner tests still contain unisolated POSIX assumptions on Windows.

These findings were not silently accepted or marked fixed. They are the input to
the next Phase 05 gap plan.

---

_Fixed: 2026-07-26T18:30:19Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 2_
