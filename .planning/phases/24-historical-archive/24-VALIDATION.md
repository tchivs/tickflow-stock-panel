---
phase: 24
slug: historical-archive
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-05
---

# Phase 24 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Phase 24 = 逐日全量存档 (HIST-01/02/03/04): 批量回填 job + snapshot_origin provenance + backfill_needed 缺口信号 + D6 cache 指针污染修复。两计划 Wave 1 并行、文件零重叠（24-01 = 回填核心：pool_snapshot origin + pool_backfill 服务 + POST /api/pipeline/backfill + D6 修复；24-02 = 缺口信号 + 读侧透传 + 守卫同步 + docs 对账）。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| Test runner | `backend/.venv/bin/python -m pytest <file> -x -q`（仓库约定，非 `uv run pytest`） |
| Hermetic fixtures | `tmp_path` + `_FakeRepo`/`_write_strategy_cache` helper；不碰真实 `data/` |
| Production imports | 测试函数内局部 import（与既有 `test_pool_hub.py`/`test_pool_snapshot.py` 风格一致） |
| FastAPI assembly | 最小 `app.state.repo` + `strategy_engine` + `TestClient`（沿 `test_pool_snapshot._FakeRepo` 形） |
| Backfill service | `run_pool_backfill` 直接调用（不启真调度器/不 HTTP）；端点测试走 TestClient |

---

## Nyquist Coverage Map

| Nyquist | Coverage | Evidence |
|---------|----------|----------|
| 8a (automated verify per task) | ✅ 6/6 tasks | 24-01 T1 `test_pool_snapshot.py`、T2 `test_pool_backfill.py`、T3 `test_pool_backfill.py + test_pool_snapshot.py`；24-02 T1 `test_pool_hub.py + test_pool_eod_job.py`、T2 `test_pool_hub.py`、T3 `test_pool_hub.py + grep 门禁` |
| 8b (no E2E/watch/delays) | ✅ | 全部单元级 hermetic；POST /api/pipeline/backfill 用 TestClient + mock job_store 断言，不跑真实 247 日回填 |
| 8c (wave coverage) | ✅ | Wave 1: 24-01 3/3；Wave 2: 24-02 3/3 |
| 8d (no MISSING refs) | ✅ | 全部 `<verify>` 命令经 plan-checker 核验（round 1：0 blockers, W-1/W-2 已在计划内修订） |

---

## HIST-01 — 批量回填 job

**诚实铁律**: 回填路径结构上不 import/调 `strategy_cache.write_cache`；回填前后 `strategy_cache.json` 逐字节相同（byte-identical 断言）；只写 `screener_results/date={as_of}/`；缺口升序摊销 warmup；限界（max_days/start/end）与协作取消。

| Criterion | Automated Verify | Acceptance |
|-----------|------------------|------------|
| 缺口集 = enriched 日期 − 已有快照 | `test_backfill_gaps` | list_backfill_gaps 返回缺失日升序 |
| 逐日回填 + 升序 | `test_backfill_runs_ascending` | 按升序逐日 persist，顺序可断言 |
| 绝不写 cache（byte-identical） | `test_backfill_never_writes_cache` | 回填前后 strategy_cache.json 字节相同 |
| 限界（max_days/start/end） | `test_backfill_bounds` | 超限跳过，参数生效 |
| 失败继续（单日失败不中断） | `test_backfill_continues_on_failure` | 单日异常 → 记录后继续 |
| 合作取消 | `test_backfill_cooperative_cancel` | 每日检查 job 状态，取消后停止 |
| 进度可观察 | `test_backfill_progress` | emit(stage,pct,msg) 调用序列 |

## HIST-02 — snapshot_origin provenance

| Criterion | Automated Verify | Acceptance |
|-----------|------------------|------------|
| persist 写 origin 字段 | `test_persist_snapshot_origin_backfill` | part.json 含 `snapshot_origin`（默认 eod） |
| 缺省 origin = eod | `test_snapshot_origin_defaults_eod` | persist 不带 origin → eod |
| 读侧透传 | `test_hub_snapshot_origin_passthrough` | build_pool_hub_snapshot 响应含 snapshot_origin |
| 旧快照缺字段 → eod | `test_hub_snapshot_origin_default_legacy` | 无 origin 键 → 读为 eod |
| EOD 快照 origin=eod | `test_pool_eod_persist_origin_eod` | EOD job 落盘 snapshot_origin=="eod" |

## HIST-03 — 存档完整性可见

| Criterion | Automated Verify | Acceptance |
|-----------|------------------|------------|
| dates 响应含缺口信号 | `test_pool_dates_backfill_needed` | `backfill_needed` 计数 + `backfill_examples` 前 5 升序 |
| 精确断言同步 | `test_pool_dates_api` 更新 | 原精确相等断言 + 新键，desc/过滤不变 |
| 无缺口 → 0 | `test_pool_dates_no_gap` | backfill_needed==0 |

## HIST-04 — 平台护栏 + D6 修复

**D6 铁律**: 手动 run_all 仅当 `as_of == svc.latest_date()` 才写 strategy_cache；历史 as_of 绝不写 cache 指针（/api/pool/hub 回显陈旧日）。快照总是落盘（origin eod/backfill）。

| Criterion | Automated Verify | Acceptance |
|-----------|------------------|------------|
| D6 source guard | `test_screener_run_all_cache_write_is_latest_gated` | run_all 段内 `is_latest`/`latest_date` 先于 `strategy_cache.write_cache`（W-1 修订作用域） |
| 历史 as_of 不写 cache | `test_run_all_historical_no_cache_write` | 手动 run_all(as_of<latest) → cache 不动，快照落盘 |
| E4 GET-only | `test_pool_api_is_get_only` | pool.py 全 GET；POST /backfill 在 api/pipeline.py |
| E5 API 禁计算触发 | `test_pool_api_no_compute_trigger` | pool.py 无 run_all/write_cache/persist_point_snapshot |
| E6 响应词汇 | `test_hub_response_has_no_execution_vocabulary` | dates/history 键集无执行族词汇 |
| E3 快照缓存隔离 | `test_pool_snapshot_does_not_import_strategy_cache` | pool_snapshot 不 import strategy_cache |
| 回填端点 guest 401 | guest whitelist 回归 | POST /api/pipeline/backfill 对 guest 401（/api/pool/dates+history 仍可读） |

---

## Manual / Post-Verify Items

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| DateNavigator 空态消费 `backfill_needed`（缺口提示/回填进度横幅） | HIST-03 | UI rendering; e2e Playwright; 前端 banner 范围经研究判定 defer（I-8） | Phase 25/27 前端面后续覆盖；本 phase 锁定 `/api/pool/dates` 的 `backfill_needed`/`backfill_examples` DTO 契约（API 测试锁定） |

*If none: "All phase behaviors have automated verification."*
