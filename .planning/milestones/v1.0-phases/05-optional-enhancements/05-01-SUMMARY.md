---
phase: 05-optional-enhancements
plan: "01"
subsystem: optional-dependency-supply-chain
tags: [supply-chain, pypi, kronos, huggingface, safetensors, human-gate]
requires:
  - phase: 05-optional-enhancements
    provides: reviewed Phase 05 package and checkpoint identities
provides:
  - explicit complete human approval for every optional package and pinned Kronos source/checkpoint policy
  - immutable source, model, tokenizer, license, and digest identities consumed by Plan 05-07
  - local-only runtime policy rejecting moving refs, pickle, and remote code
key-files:
  created:
    - .planning/phases/05-optional-enhancements/05-01-SUMMARY.md
  modified: []
key-decisions:
  - "approved: scikit-learn 1.8.0, torch >=2,<3 resolved to a Linux CPU wheel, einops 0.8.1, huggingface-hub 0.33.1, safetensors 0.6.2, and the compatible existing tqdm lock"
  - "approved: Kronos source commit 67b630e67f6a18c9e9be918d9b4337c960db1e9a with only reviewed inference files, MIT license, and upstream manifest"
  - "approved: pinned local safetensors model/tokenizer pairs and exact revisions/digests; routine startup, requests, workers, and tests remain offline"
requirements-completed: [SHDW-01, FORE-01]
coverage:
  - id: package-legitimacy
    description: "Every SUS optional package and Kronos source/checkpoint row received an explicit human decision after official-source review."
    requirement: SHDW-01, FORE-01
    verification:
      - kind: manual_procedural
        ref: "User selected 全部批准 after the exact package/source/checkpoint table was presented"
        status: pass
    human_judgment: true
    rationale: "Package and supply-chain approval is an independent human trust decision; the summary preserves the exact reviewed table and recorded user dispositions."
metrics:
  completed: 2026-07-16
status: complete
approval: approved
approved_at: 2026-07-16T03:41:52Z
---

# Phase 05 Plan 01: Optional Package And Kronos Supply-Chain Approval Summary

**Decision: `approved` for every listed package, source, model, tokenizer, digest, and local-only loading policy. Plan 05-07 may proceed only after validating this complete summary.**

## Approved Package Table

| Item | Approved identity | Official evidence | Decision |
|---|---|---|---|
| scikit-learn | `1.8.0`; BSD-3-Clause; Python >=3.11; Linux x86_64/aarch64 CPython 3.11 wheels | `https://pypi.org/pypi/scikit-learn/1.8.0/json`, `https://github.com/scikit-learn/scikit-learn` | approved |
| torch | official PyTorch package; resolve and lock a compatible `>=2,<3` Linux CPU wheel | `https://pypi.org/pypi/torch/json`, `https://github.com/pytorch/pytorch` | approved |
| einops | `0.8.1`; MIT; pure Python wheel; owner `alex.rogozhnikov` | `https://pypi.org/pypi/einops/0.8.1/json`, `https://github.com/arogozhnikov/einops` | approved |
| huggingface-hub | `0.33.1`; Hugging Face, Inc.; Apache; fixed-revision provisioning only | `https://pypi.org/pypi/huggingface-hub/0.33.1/json`, `https://github.com/huggingface/huggingface_hub` | approved |
| safetensors | `0.6.2`; Hugging Face source; Linux wheels; safetensors-only model files | `https://pypi.org/pypi/safetensors/0.6.2/json`, `https://github.com/huggingface/safetensors` | approved |
| tqdm | keep the compatible existing lock (`4.67.3` at review time); no separate forecast extra entry | `https://pypi.org/pypi/tqdm/4.67.3/json` | approved |

## Approved Kronos Source

- Repository: `https://github.com/shiyu-coder/Kronos`
- Commit: `67b630e67f6a18c9e9be918d9b4337c960db1e9a`
- License: MIT
- Vendored subset: `model/__init__.py`, `model/kronos.py`, `model/module.py`, plus `LICENSE` and `UPSTREAM.json`
- Policy: no runtime clone; the sync tool verifies the exact commit and file allowlist before updating reviewed source.

## Approved Checkpoint Catalog

| Catalog pair | Immutable revision | `model.safetensors` SHA-256 | Decision |
|---|---|---|---|
| Kronos-mini | `f4e68697d9d5aed55cef5c96aabc3376bcad9f81` | `a7d5f37e2e9fbd9891f7d7d4f72574512dd1f704fee14223e0a8cd0fbf54197c` | approved default CPU model |
| Kronos-Tokenizer-2k | `26966d0035065a0cae0ebad7af8ece35bc1fb51c` | `b97ec46b3b72160509e289183eaf7bdf5f0dac5bb9b49522f6d46638a99a8717` | approved only with Kronos-mini |
| Kronos-small | `901c26c1332695a2a8f243eb2f37243a37bea320` | `b082dfcbd8e8c142a725c8bbb99781802f38fec81210e13479effb32b3c3e020` | approved optional catalog model |
| Kronos-Tokenizer-base | `0e0117387f39004a9016484a186a908917e22426` | `59d85f6af76a2c3b8240ea06cb21db4213b4eeca053f246b23e29cf832fc6bee` | approved only with small/base family |
| Kronos-base | `2b554741eca47781b64468546e77fef3e85130e6` | `abff193acab6db1a0368e9773e75799d11403b6d054ee6d5f0a11aeabc5f4b83` | approved optional catalog model; explicit operator provisioning only |

Hugging Face metadata identifies all five assets as MIT-tagged safetensors repositories. Expanded tree metadata reports the exact LFS SHA-256 values above and safe/no-code-execution scanner results.

## Approved Runtime Policy

- Provisioning may access the network only through an explicit operator action.
- Routine application startup, API requests, worker execution, tests, and model loading are local-only.
- Model and tokenizer must match the approved catalog pair and immutable revisions/digests.
- `trust_remote_code` is forbidden.
- Pickle and moving `latest`/branch references are forbidden.
- Any missing, partial, rejected, stale, mismatched, or unverifiable identity keeps Forecast unavailable without breaking the completed v1 loop.
- Shadow retains only exported allowlisted JSON rules; no scikit-learn estimator or pickle is persisted.

## Human Gate Evidence

At `2026-07-16T03:41:52Z`, the initial exact table was presented after reading official PyPI, GitHub, and Hugging Face API metadata, and the user selected **“全部批准”**. At `2026-07-16T05:33:17Z`, the omitted `Kronos-base` optional catalog row was separately presented with its immutable revision, 409,264,008-byte safetensors digest, MIT tag, and safe/no-code-execution scan; the user selected **“批准为可选目录项”**. No row was inferred, omitted, or partially approved.

## Deviations From Plan

None. No dependencies, lockfiles, vendored source, checkpoints, images, or application files changed during this gate.

## Verification

Human verification passed. Executable precondition enforcement remains in Plan 05-07 and must validate this summary's `status: complete`, `approval: approved`, complete package rows, exact source commit, exact checkpoint revisions/digests, and local-only policy before mutation.

---

*Completed: 2026-07-16*
