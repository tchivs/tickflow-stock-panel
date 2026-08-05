---
phase: 22
slug: pool-date-navigation
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-05
---

# Phase 22 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Phase 22 = 股池日期导航 (POOL-04/05/06): 冻结式点快照 + 日期列表/as_of 取池 API + EOD 持久化 job。两计划 Wave 1 并行、文件零重叠（22-01 = 快照服务 + 投影抽取 + 只读端点 + run_all 核心共享；22-02 = EOD job + 游客白名单 + docs 对账）。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| Test runner | `backend/.venv/bin/python -m pytest <file> -x -q`（仓库约定，非 `uv run pytest`） |
| Hermetic fixtures | `tmp_path` + `_write_strategy_cache`/`_write_snapshot` helper；不碰真实 `data/` |
| Production imports | 测试函数内局部 import（与既有 `test_pool_hub.py`/`test_factor_hits.py` 风格一致） |
| FastAPI assembly | 最小 `app.state.repo` + `strategy_engine` + `TestClient`（沿 `test_factor_hits._FakeRepo` 形） |

---

## Nyquist Coverage Map

| Nyquist | Coverage | Evidence |
|---------|----------|----------|
| 8a (automated verify per task) | ✅ 7/7 tasks | 22-01 T1 `test_pool_snapshot.py`、T2/T3 `test_pool_hub.py`、T4 `test_pool_snapshot.py + test_factor_hits.py`；22-02 T1 `test_pool_eod_job.py`、T2 `test_guest_masking.py`、T3 grep 门禁 |
| 8b (no E2E/watch/delays) | ✅ | 全部单元级 hermetic 测试；EOD job 注册用源码 grep 断言，不启动真调度器 |
| 8c (wave coverage) | ✅ | Wave 1: 22-01 4/4 + 22-02 3/3 |
| 8d (no MISSING refs) | ✅ | 全部 `<verify>` 命令经 plan-checker 核验（round 2） |

---

## POOL-04 — 冻结式点快照

**诚实铁律**: 快照只落当次 `results` 行集，绝不落 `today_ever_rows`/`today_ever_matched` union；total=0 空策略保留；同 as_of 幂等重写无 `.tmp` 残留。

| Criterion | Automated Verify | Acceptance |
|-----------|------------------|------------|
| 快照 payload 无 union 键 | `test_snapshot_roundtrip_no_ever_rows` | 键集不含 ever 键 |
| 原子写 + 幂等 | `test_snapshot_atomic_and_idempotent` | 无 .tmp；二次覆盖最新 |
| 空策略保留 | `test_snapshot_preserves_empty_strategy` | total=0 sid 仍存在 |
| 策略指纹稳定/敏感 | `test_strategy_fingerprint_stability_and_sensitivity` | meta/源码变化 → 新指纹 |
| 日期列表 desc + 过滤 | `test_list_snapshot_dates_sorted_desc_and_filters` | ISO desc；无 part.json 排除 |
| as_of 严格校验 | `test_persist_rejects_invalid_as_of` | 非法 → ValueError / None |
| run_all 落快照（调用点 1） | `test_run_all_persists_point_snapshot` | API 路径后 part.json 含 point/指纹 |

## POOL-05 — 日期列表 + as_of 取池

**契约**: `GET /api/pool/hub` single-as_of 反漂移回显零改动（17 个既有测试零修改）；历史取池走独立 `GET /api/pool/history`。

| Criterion | Automated Verify | Acceptance |
|-----------|------------------|------------|
| dates 列表形状 | `test_pool_dates_api` | `{dates, count, latest}` desc |
| history 有快照 → hub 同形状 | `test_pool_history_snapshot` | total 权威；mode 存在 |
| 无快照 → 200 available:false | `test_pool_history_missing_available_false` | 非 404 |
| 非法 as_of → 400 | `test_pool_history_rejects_bad_as_of` | 400；缺失 as_of → 空态 |
| 投影共享 bit-identical | `test_build_pool_hub_snapshot_uses_snapshot_total` | total=2 rows=1 → total 权威 |
| 概念归属标注 | `test_build_pool_hub_snapshot_has_concept_attribution` | `concept_attribution:"current_snapshot"` |
| 17 回归零改动 | `pytest tests/test_pool_hub.py -x -q` | 全绿 |

## POOL-06 — EOD 持久化 job

| Criterion | Automated Verify | Acceptance |
|-----------|------------------|------------|
| job 写快照 + 刷新缓存 | `test_pool_eod_persist_writes_snapshot_and_cache` | part.json point + strategy_cache as_of==latest |
| 无数据日 skip | `test_pool_eod_persist_skips_no_data_date` | `{skipped: "no data date"}` 无文件 |
| 注册 gate | `test_pool_eod_job_registered_in_scheduler` | `id="pool_eod_persist"` + `_run_tracked` + mon-fri cron |
| 无首请求阻塞 | EOD 预生成设计 + `_run_tracked` 单飞 | history 请求只读快照 |

## POOL-03 — 零执行权守卫扩展

| Guard | Assertion |
|-------|-----------|
| E1 扩源 3 元组 | `_feature_sources()` 含 pool_snapshot.py；三处解包同步 |
| E2 快照只写 screener_results | 常量感知（`_SNAPSHOT_ROOT=="screener_results"`） |
| E3 运行时缓存隔离 | pool_snapshot 不 import/reference strategy_cache |
| E4 GET-only | pool.py 全 `@router.get` |
| E5 API 禁计算触发 | pool.py 无 run_all/write_cache/persist_point_snapshot |
| E6 响应词汇 | history+dates 键集无执行族词汇 |
| E7 游客白名单 | `/api/pool/dates` + `/api/pool/history` 加入 `_GUEST_READ_GET_PATHS` + guest 测试路径元组 |

---

## Manual / Post-Verify Items

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 历史股池日期导航的前端渲染（DateNavigator ‹ › 步进、空态、概念归属标注） | POOL-04/05 | UI rendering; e2e Playwright | Phase 23 owns the frontend surface; Phase 22 keeps backend DTO contract green (`/api/pool/dates` + `/api/pool/history` 形状 + `concept_attribution` 键由 API 测试锁定) |

*If none: "All phase behaviors have automated verification."*
