---
schema_version: 1
open_count: 0
waived_count: 0
fixed_count: 4
total_count: 4
last_updated: 2026-07-26T21:41:15.935Z
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
  }
]
````
