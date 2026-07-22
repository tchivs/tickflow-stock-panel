---
phase: 05-optional-enhancements
plan: "34"
subsystem: forecast-quantile-artifacts
tags: [forecast, parquet, sqlite, quantiles, calibration, provenance]
requires:
  - phase: 05-optional-enhancements
    plan: "23"
    provides: immutable 32-path Parquet artifacts, maturity scanning, append-only calibration
  - phase: 05-optional-enhancements
    plan: "25"
    provides: atomic forward-only operational SQLite migrations
provides:
  - atomic path-bound quantile artifact commit with bounded SQLite metadata
  - restart-safe shared loader for exact immutable quantile Parquet bytes
  - deny-by-default P10/P50/P90 projection and byte-derived maturity calibration
affects: [FORE-01, CR-02, forecast-projection, forecast-calibration]
tech-stack:
  added: []
  patterns:
    - canonical quantile series remain exclusively in immutable managed Parquet
    - SQLite stores only bounded descriptor, checksum, source binding, provenance digest, and shape metadata
    - projection and calibration share one strict verified-byte reload path
key-files:
  created:
    - .planning/phases/05-optional-enhancements/05-34-SUMMARY.md
  modified:
    - backend/app/operational/migrations.py
    - backend/app/forecast/service.py
    - backend/app/forecast/repository.py
    - backend/app/forecast/projections.py
    - backend/app/forecast/calibration.py
    - backend/tests/test_operational_migrations.py
    - backend/tests/forecast/test_runner.py
    - backend/tests/forecast/test_calibration.py
key-decisions:
  - "Canonical P10/P50/P90 session series stay only in immutable Parquet; SQLite receives no value array, JSON series, or per-quantile columns."
  - "The sole completed-forecast transaction independently verifies both managed Parquet payloads, recomputes quantiles over all 32 paths, and persists only bounded identity metadata."
  - "Public projection denies caller-supplied or legacy fixture quantiles unless the record carries verified available-artifact state; maturity calibration invokes the same repository loader."
patterns-established:
  - "Same-byte decode: read checksum-verified payload bytes into memory and decode that exact buffer rather than reopening a pathname."
  - "Legacy quantile state: pre-migration records are explicitly legacy_unavailable and produce unevaluable facts without fabricated metrics."
requirements-completed: [FORE-01]
coverage:
  - id: D1
    description: "A real 32-path plus quantile bundle commits atomically, survives restart, and rejects every malformed or divergent artifact without a completed transition."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "backend/tests/test_operational_migrations.py -k 'forecast_quantile or quantile_migration'"
        status: pass
      - kind: integration
        ref: "backend/tests/forecast/test_runner.py -k 'quantile_bundle_commit or quantile_artifact or strict_commit'"
        status: pass
    human_judgment: false
  - id: D2
    description: "Projection and calibration consume the same checksum-verified immutable quantile Parquet bytes after restart."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "backend/tests/forecast/test_calibration.py::test_cr02_projection_and_calibration_use_same_verified_parquet_bytes"
        status: pass
      - kind: integration
        ref: "backend/tests/forecast/test_calibration.py -k 'production_committed_quantiles or calibration_computes or immutable or parallel'"
        status: pass
    human_judgment: false
duration: 20m
completed: 2026-07-22
status: complete
---

# Phase 05 Plan 34: Immutable Quantile Artifact Commit and Calibration Summary

**32-path 绑定的 P10/P50/P90 Parquet 工件现在可经唯一事务提交、进程重启、公共投影和成熟度校准全链路复用同一组校验字节，同时 SQLite 仅保存有界身份元数据。**

## Performance

- **Duration:** 20m
- **Started:** 2026-07-22T05:17:40Z
- **Completed:** 2026-07-22T05:37:01Z
- **Tasks:** 2/2
- **Files modified:** 8 production/test files plus this summary

## Accomplishments

- 追加原子 forward migration：旧记录获得明确 `legacy_unavailable` 状态，新记录仅可写入 quantile descriptor、checksum、source-path checksum、provenance digest 与有界 shape/count 元数据；未新增 P10/P50/P90 值列、数组、blob 或第二时序存储。
- 将旧八字段单工件验证器替换为严格双 Parquet bundle 验证：检查 managed-root containment、descriptor/metadata/size/SHA-256、32×horizon×feature 完整 path 关系、3×horizon×feature quantile 关系、session/label/finite/order，并在提交时对完整 32-path axis 重算分位数。
- `ContextualForecastWorker` 仅把 adapter 的有界 `artifacts` manifest 和 warning codes 交回 parent；raw paths、raw quantiles 与不可信诊断不会跨越提交边界。
- 新仓储实例重启后通过共享 loader 重开 quantile artifact，校验同一 checksum/source binding/provenance/shape，并从已校验的 exact bytes 恢复有序 close P10/P50/P90。
- 公共 projection 对缺少 `available` 及完整验证元数据的 caller/fixture quantiles deny-by-default；maturity scanner 使用同一个 repository loader 计算 MAE、coverage 与三项 pinball loss。
- CR-02 主节点从生产形态 commit 开始，经过 restart、projection、calibration、tamper rejection 和原字节恢复；并发 scanner 仍只追加一个 canonical outcome/fact。

## Task Commits

| Gate | Task | Commit | Result |
|---|---|---|---|
| RED | Task 1: verified bundle commit/restart | `284cb5c` | migration columns与 strict bundle validator 缺失，测试按预期失败 |
| GREEN | Task 1: verified bundle commit/restart | `853a4a6` | migration 2 passed；runner bundle/failure paths 10 passed |
| RED | Task 2: same-byte projection/calibration | `2b157d4` | projection 仍接受缺少 verified availability 的 caller quantiles，测试按预期失败 |
| GREEN | Task 2: same-byte projection/calibration | `06471d9` | CR-02 primary 1 passed；focused calibration 4 passed |

**Plan metadata:** committed separately after self-check；shared tracking 依启动时保护约束保持不变。

## Files Created/Modified

- `backend/app/operational/migrations.py` — 仅追加 bounded quantile metadata columns、legacy state 与 all-or-none insert guard。
- `backend/app/forecast/service.py` — child bounded artifact bundle handoff及双 payload parent precheck。
- `backend/app/forecast/repository.py` — 双工件 exact-byte strict validator、atomic metadata insert、restart loader 与 canonical mapping。
- `backend/app/forecast/projections.py` — verified-availability-only quantile projection与完整有限/有序映射检查。
- `backend/app/forecast/calibration.py` — maturity metrics 改用 shared verified artifact loader。
- `backend/tests/test_operational_migrations.py` — existing-row preservation、无 canonical value columns、idempotency 与 rollback/user_version atomicity。
- `backend/tests/forecast/test_runner.py` — production-shaped real Parquet bundle、restart、worker handoff及 missing/tampered/shape/session/label/nonfinite/relabel/source divergence rejection。
- `backend/tests/forecast/test_calibration.py` — 精确 CR-02 主节点、production commit、projection、calibration、immutability、legacy/missing actual 与 parallel canonical append。

## Decisions Made

- Parquet 是 quantile series 的唯一权威；SQLite descriptor 的 `relative_path` 仅用于定位受管 immutable payload，任何公共 projection 都不暴露该受管路径。
- commit 阶段同时读取 path/quantile exact bytes 并重算 32-path quantiles；restart 阶段只需重开 canonical quantile bytes，但必须复验其 descriptor、scope 中的 source path checksum、shape 与 persisted provenance digest。
- `quantile_availability=legacy_unavailable` 是真实历史缺失状态，不回填、不卡零值；实际值到期时追加 `unevaluable/missing_quantiles` 且所有 metric 保持 `NULL`。
- Projection 只接受 repository 已物化且带完整 verified metadata 的 quantile mapping；caller 单独提供 mapping 不构成权威。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] 修复隔离 worktree 的 pytest launcher 来源漂移**
- **Found during:** Task 1 RED verification
- **Issue:** ignored `backend/.venv/bin/pytest` shebang 指向主 checkout，最初 traceback 并非当前 worktree source。
- **Fix:** 仅在当前隔离 worktree 内修正 ignored launcher；其后 literal `uv run pytest` 四段计划命令均从当前 source 执行。
- **Files modified:** `backend/.venv/bin/pytest`（ignored environment file，未提交）
- **Verification:** traceback 改为 `app/forecast/repository.py` 的当前 worktree 相对路径；最终 literal selector 全部通过。
- **Committed in:** Not applicable

**2. [Rule 1 - Bug] 修正 RED test 使用不存在的 transition helper**
- **Found during:** Task 1 GREEN verification
- **Issue:** 新 failure-path assertion 误调用 `job_transitions()`；仓储规范 API 为 bounded `job_transitions_after()`。
- **Fix:** 使用 `after_version=-1, limit=256` 的既有 bounded transition reader，继续证明失败事务无 `completed` transition。
- **Files modified:** `backend/tests/forecast/test_runner.py`
- **Verification:** runner selector 10 passed。
- **Committed in:** `853a4a6`

---

**Total deviations:** 2 auto-fixed（1 blocking environment、1 test bug）。
**Impact on plan:** 两项均仅保证隔离验证可信和测试调用正确；未扩展产品范围，也未改变 Parquet authority。

## Issues Encountered

- 初始 selector 在测试节点尚不存在时返回 pytest code 5；RED tests 写入后按预期在缺失 migration/validator/projection contract 上失败。
- Managed artifact verification API 首先校验 metadata/scope/path；仓储随后重新读取 payload、重新核对 size/SHA-256，并从该内存 buffer 解码，避免校验后按路径二次读取不同字节。

## Verification

```text
cd backend && uv run pytest tests/test_operational_migrations.py -k "forecast_quantile or quantile_migration" -x
PASS — 2 passed, 4 deselected.

cd backend && uv run pytest tests/forecast/test_runner.py -k "quantile_bundle_commit or quantile_artifact or strict_commit" -x
PASS — 10 passed, 29 deselected.

cd backend && uv run pytest tests/forecast/test_calibration.py::test_cr02_projection_and_calibration_use_same_verified_parquet_bytes -x
PASS — 1 passed.

cd backend && uv run pytest tests/forecast/test_calibration.py -k "production_committed_quantiles or calibration_computes or immutable or parallel" -x
PASS — 4 passed, 17 deselected.
```

## Acceptance Criteria

- **PASS — Parquet authority:** canonical per-session close P10/P50/P90 只存在于 immutable quantile Parquet；SQLite schema 不含 quantile value series。
- **PASS — atomic strict commit:** missing artifact、altered bytes、wrong shape/session/label、nonfinite、crossed relabel 与 source checksum divergence 全部在事务内拒绝，无 record、无 completed state、无 completed transition。
- **PASS — restart identity:** 新 repository instance 以 persisted descriptor/checksum/source/provenance metadata 重开同一 immutable payload，并恢复 exact ordered values。
- **PASS — same-byte consumers:** CR-02 primary selector证明 projection 与 calibration 均来自同一 verified Parquet bytes；tamper 后两者 fail closed。
- **PASS — append-only maturity:** mature actual 产生真实 MAE、coverage、P10/P50/P90 pinball；missing actual 保持 pending，legacy descriptor-less record 显式 unevaluable 且无零填 metric。
- **PASS — immutable concurrency:** calibration 前后 artifact bytes/descriptor/provenance/creation metadata 完全一致；两个 scanner 仅产生一个 outcome/fact。
- **PASS — no downstream authority:** calibration 仍不调用 thesis、strategy、decision plan、monitor、position 或 broker collaborators。

## Threat Mitigation Evidence

- **T-05-34-01:** commit 对两个 managed artifact 的 metadata、scope、regular-file containment、size、SHA-256 和 exact bytes 做独立校验，重建完整 path tensor，并按 label 对 32-path axis 分位数逐值比对。
- **T-05-34-02:** SQLite 的 bounded descriptor/checksum/source/provenance/shape metadata 唯一定位同一 quantile Parquet；restart projection 与 calibration 共享严格 loader。
- **T-05-34-03:** maturity scanner 只读取 actual evidence并追加 outcome/calibration facts；既有 negative-authority collaborators 保持零调用。

## TDD Gate Compliance

- Task 1 RED `284cb5c` 先于 GREEN `853a4a6`，分别证明 schema 与旧八字段 validator 无法满足 bundle contract。
- Task 2 RED `2b157d4` 先于 GREEN `06471d9`，证明旧 projection 会接受无 verified state 的 caller quantiles。
- 两个 mandatory RED 均真实失败，两个 GREEN 后 literal plan verification 全绿。

## Known Stubs

None. Changed production/test files未发现 `TODO`、`FIXME`、placeholder、skip 或 xfail；legacy unavailable 与 missing actual 均为显式业务状态而非 stub。

## User Setup Required

None. 本计划没有新增依赖、外部服务、checkpoint 下载或远端 artifact source。

## Next Phase Readiness

- CR-02 已具备端到端自动证据，可由 Phase 05 verifier 重新判定 FORE-01 quantile display/calibration 链路。
- 其他 Phase 05 review gaps 保持独立；本计划未触碰 principal ownership、input revalidation、worker process-group 或 UI outcome labeling。

## Self-Check: PASSED

- 8 个 scoped production/test files 与 `05-34-SUMMARY.md` 均存在。
- RED/GREEN commits `284cb5c`、`853a4a6`、`2b157d4`、`06471d9` 均可由 git history 解析。
- Literal plan verification 共通过 migration 2、runner 10、primary CR-02 1、calibration 4 个测试，无 required node skipped。
- Stub/skip 扫描为空，任务 commits 未删除 tracked file。
- `.planning/STATE.md` 与 `.planning/ROADMAP.md` 在 executor 启动前已有无关未提交 hunks；依 parent 指令为避免覆盖/混入用户工作，本计划未修改或提交这些 shared tracking files，仅提交本 summary metadata。

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-22*
