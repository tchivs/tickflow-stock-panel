---
schema_version: 1
open_count: 2
waived_count: 0
fixed_count: 5
total_count: 7
last_updated: 2026-08-04T15:37:14.752Z
---

# Broken Windows Ledger

> Cross-phase defect register. `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 05 | deviation | backend/app/optional_artifacts.py |  | Windows immutable artifact descriptors required binary writable file handles and POSIX-only directory fsync. | fixed |  | 2026-07-26T17:35:55.704Z | 2026-07-26T17:36:06.081Z |
| 2 | 05 | unrun-verify | backend/tests/forecast/test_runner.py |  | linux_process_group suite unrun because no usable WSL distribution is installed | fixed |  | 2026-07-26T20:01:02.152Z | 2026-07-26T21:41:15.418Z |
| 3 | 05 | unrun-verify | backend/scripts/verify_phase5_final_gate.py | 1200 | 05-44 unique final orchestration could not produce native Linux JUnit because wsl.exe has no installed distribution; scoped VALIDATION remains pending | fixed |  | 2026-07-26T20:13:12.349Z | 2026-07-26T21:41:15.935Z |
| 4 | 05 | deviation | backend/scripts/verify_phase5_final_gate.py | 1200 | 05-44 WSL preflight originally crashed while decoding native UTF-16LE help output; fix adb7a09 was committed but not rerun under the one-orchestration rule | fixed |  | 2026-07-26T20:13:12.851Z | 2026-07-26T20:22:53.282Z |
| 5 | 11 | stub | backend/tests/portfolio/test_repository.py | 1 | RED scaffold: append-only record/get/list methods land in 11-01 | fixed | resolved by 11-01 | 2026-08-01T16:43:05.110Z | 2026-08-01T17:29:00.000Z |
| 6 | 16 | unrun-verify | frontend/src/components/data/AuctionProbeCard.tsx |  | Data-page browser smoke of the 竞价数据 panel visuals/interaction not run in headless executor (covered by tsc + backend suites; tracked via SUMMARY coverage D5) | open |  | 2026-08-04T12:55:10.383Z |  |
| 7 | 19 | unrun-verify | frontend/e2e/pool-hub.spec.ts |  | Task 3 end-of-phase human check: visual confirmation of the 4 UI-SPEC backstop scalars (guest banner+grid coexistence, long-name truncation, many masked rows distinct, guest↔vip column shift) — screenshots captured, human sign-off pending | open |  | 2026-08-04T15:37:14.752Z |  |

````json
[
  {
    "id": 1,
    "kind": "deviation",
    "phase": "05",
    "file": "backend/app/optional_artifacts.py",
    "line": null,
    "description": "Windows immutable artifact descriptors required binary writable file handles and POSIX-only directory fsync.",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-07-26T17:35:55.704Z",
    "resolved_at": "2026-07-26T17:36:06.081Z"
  },
  {
    "id": 2,
    "kind": "unrun-verify",
    "phase": "05",
    "file": "backend/tests/forecast/test_runner.py",
    "line": null,
    "description": "linux_process_group suite unrun because no usable WSL distribution is installed",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-07-26T20:01:02.152Z",
    "resolved_at": "2026-07-26T21:41:15.418Z"
  },
  {
    "id": 3,
    "kind": "unrun-verify",
    "phase": "05",
    "file": "backend/scripts/verify_phase5_final_gate.py",
    "line": 1200,
    "description": "05-44 unique final orchestration could not produce native Linux JUnit because wsl.exe has no installed distribution; scoped VALIDATION remains pending",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-07-26T20:13:12.349Z",
    "resolved_at": "2026-07-26T21:41:15.935Z"
  },
  {
    "id": 4,
    "kind": "deviation",
    "phase": "05",
    "file": "backend/scripts/verify_phase5_final_gate.py",
    "line": 1200,
    "description": "05-44 WSL preflight originally crashed while decoding native UTF-16LE help output; fix adb7a09 was committed but not rerun under the one-orchestration rule",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-07-26T20:13:12.851Z",
    "resolved_at": "2026-07-26T20:22:53.282Z"
  },
  {
    "id": 5,
    "kind": "stub",
    "phase": "11",
    "file": "backend/tests/portfolio/test_repository.py",
    "line": 1,
    "description": "RED scaffold: append-only record/get/list methods land in 11-01",
    "status": "fixed",
    "reason": "resolved by 11-01",
    "recorded_at": "2026-08-01T16:43:05.110Z",
    "resolved_at": "2026-08-01T17:29:00.000Z"
  },
  {
    "id": 6,
    "kind": "unrun-verify",
    "phase": "16",
    "file": "frontend/src/components/data/AuctionProbeCard.tsx",
    "line": null,
    "description": "Data-page browser smoke of the 竞价数据 panel visuals/interaction not run in headless executor (covered by tsc + backend suites; tracked via SUMMARY coverage D5)",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-08-04T12:55:10.383Z",
    "resolved_at": null
  },
  {
    "id": 7,
    "kind": "unrun-verify",
    "phase": "19",
    "file": "frontend/e2e/pool-hub.spec.ts",
    "line": null,
    "description": "Task 3 end-of-phase human check: visual confirmation of the 4 UI-SPEC backstop scalars (guest banner+grid coexistence, long-name truncation, many masked rows distinct, guest↔vip column shift) — screenshots captured, human sign-off pending",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-08-04T15:37:14.752Z",
    "resolved_at": null
  }
]
````
