---
status: testing
phase: 06-release-reproducibility
source: [06-VERIFICATION.md]
started: 2026-07-31T05:21:31Z
updated: 2026-07-31T05:21:31Z
---

## Current Test

number: 1
name: Clean Windows/WSL end-to-end evidence regeneration
expected: |
  From a detached clean real Windows checkout with WSL available, the documented
  `--evidence-only` command runs without `--github-run-id`, produces four labeled
  reports with adjacent provenance sidecars, and returns a passing parser verdict
  while leaving the closed v1.0 validation history unchanged.
awaiting: user response

## Tests

### 1. Clean Windows/WSL end-to-end evidence regeneration
expected: From a detached clean real Windows checkout with WSL available, the documented `--evidence-only` command produces the complete same-run evidence bundle, uses WSL for the Linux leg, returns a passing parser verdict, and reports `validationUpdated: false`.
result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
