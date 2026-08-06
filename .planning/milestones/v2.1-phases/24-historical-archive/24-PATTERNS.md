# Phase 24: 逐日全量存档 (Historical Archive) - Pattern Map

**Mapped:** 2026-08-06
**Files analyzed:** 10（4 新增 / 6 修改，含 1 测试模块）
**Analogs found:** 13 / 13（exact 12 / role-match 1 / partial 0；另有 2 处「无既有 analog 的新形态」见 No Analog Found）

> 本文件把 Phase 24（HIST-01..04）的每个新建/修改文件映射到仓库内最接近的既有实现，并给出可直接复制/镜像的具体代码段（带文件路径与行号，全部在本 session 逐行读取确认）。
>
> **一句话总结:** 回填 job 是「`_pool_eod_persist`（daily_pipeline.py:966-1008）的逐日循环版 + `extend_history`（services/extend_history.py）的用户触发后台形 + `extend_history` API（api/kline.py:633-700）的异步端点形」三者缝合；写路径逐行复用 `pool_snapshot.persist_point_snapshot`（L50-97），**唯一且最关键的差别是回填绝不调 `strategy_cache.write_cache`**（strategy_cache.py:121-170 是 single-as_of 指针，`_write_cache_locked` 的 union 合并分支 L138-142 是历史写入污染的根源，v2.0 实测先例 as_of=2026-07-31）。
>
> **给 planner 的第一优先级决策点:** 既有锁死守卫 `test_pool_api_is_get_only`（tests/test_pool_hub.py:836-841）要求 `api/pool.py` 全部路由必须为 GET。研究草案的 `POST /api/pool/backfill` 若落在 `api/pool.py` 会直接红掉该守卫。两条出路见「Divergence 3」——推荐放 `api/pipeline.py`（镜像 `extend_history`），或有意扩展守卫。

## 关键约束与危险区（先读）

Phase 24 是**研究数据写路径**（写 `screener_results/date=*/part.json` 快照分区），不是实盘执行，也不是运行时缓存刷新。仓库里已有四条锁死边界，本阶段的所有新写路径必须绕开或有意扩展：

| 边界 | 位置 | 本阶段影响 |
|---|---|---|
| **POOL-03 AST 守卫 E4: pool.py 只能 GET** | `tests/test_pool_hub.py:836-841`（`assert methods and set(methods) == {"get"}`） | `POST /api/pool/backfill` **不能**放进 pool.py，否则红。见 Divergence 3 |
| **POOL-03 AST 守卫 E5: pool.py 禁计算触发 token** | `tests/test_pool_hub.py:891-895`（`run_all`/`run_preset`/`write_cache`/`persist_point_snapshot` 不得出现在 pool.py 源码） | pool.py 只做只读 `/dates`/`/history`；`backfill_needed` 是 GET-only 零执行权 |
| **POOL-03 AST 守卫 E3: pool_snapshot 禁 import strategy_cache** | `tests/test_pool_hub.py:880-888`（`"strategy_cache" not in module`） | 快照/回填服务**不得** import 运行时缓存；回填服务把 `write_cache` 从调用序列里剔除即可满足 |
| **write_cache 指针污染（ARCHIVE R1，高）** | `strategy_cache.py:121-170` `_write_cache_locked`；污染点 `api/screener.py:445` | 回填对每历史日**只** `run_all_with_hits` + `persist_point_snapshot(origin="backfill")`，**绝不** `write_cache`；既有手动 `run_all` 历史 as_of 写 cache（L445）是潜在 bug，建议一并修「非最新日不写 cache」 |

## File Classification（目标文件 → analogs）

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality | 关键差异 |
|---|---|---|---|---|---|
| `backend/app/services/pool_backfill.py` (new) | service | batch (用户触发后台回填) | `services/extend_history.py::run_extend_history` (102-225) + `jobs/daily_pipeline.py::_pool_eod_persist` (966-1008) | exact | 逐日循环 + `snapshot_origin="backfill"` + **绝无 write_cache**；日期集 = enriched 分区 − 快照分区（幂等） |
| `backend/app/api/pool.py` (modified) | controller | request-response (GET-only) | 模块内 `get_pool_dates` (55-65) — 追加 `backfill_needed` 缺口计数 | exact (in-file) | `/dates` 响应加 `backfill_needed`；保持 GET-only（守卫 E4/E5） |
| `backend/app/api/pipeline.py` (modified) 或 `api/backfill.py` (new) | controller | request-response (POST 触发) | `api/kline.py::extend_history` (633-700) — 异步触发 + job_store 单飞 | exact | `POST /api/pipeline/backfill`（镜像 `extend_history`）；不碰 pool.py GET-only 守卫 |
| `backend/app/services/pool_snapshot.py` (modified) | service | file-I/O (原子 JSON 写 + hive glob) | 模块内 `persist_point_snapshot` (50-97) + `list_snapshot_dates` (120-133) | exact (in-file) | payload 增 `snapshot_origin`；`load_point_snapshot` 容错缺字段；可能新增 `list_enriched_dates` helper |
| `backend/app/jobs/daily_pipeline.py` (modified) | job/scheduler | batch (cron 单飞) | 模块内 `_pool_eod_persist` (966-1008) — 唯一改动是 `persist` 传 `origin="eod"` | exact (in-file) | 加 `origin="eod"`；其余零改动（EOD 仍先 write_cache 再 persist，语义不变） |
| `backend/app/api/screener.py` (modified) | controller | request-response | 模块内 `run_all` (408-465) — write_cache (445) 与 persist (448-457) 调用点 | exact (in-file) | 指针污染修复点：历史 as_of 跳过 write_cache；persist 传 `origin="manual"` |
| `backend/tests/test_pool_backfill.py` (new) | test | transform | `test_pool_eod_job.py` `_make_app_state` (51-96) + `test_pool_snapshot.py` `_FakeRepo`/`_write_canned_strategy` (129-190) | role-match | 追加「回填后 strategy_cache.json 不被改动」断言 + 缺口集 fixture |
| `backend/tests/test_pool_snapshot.py` (modified) | test | transform | 模块内 hermetic 夹具 `_write_snapshot_payload` (46-67) + `test_snapshot_roundtrip_no_ever_rows` (191-221) | exact (in-file) | 增 `snapshot_origin` round-trip / 容错测试 |
| `backend/tests/test_pool_eod_job.py` (modified) | test | transform | 模块内 `test_pool_eod_persist_writes_snapshot_and_cache` (98-128) + grep 门禁 `test_pool_eod_job_registered_in_scheduler` (160-173) | exact (in-file) | 增 `snap["snapshot_origin"] == "eod"` 断言；新 grep 门禁锁「回填禁 write_cache」 |
| `backend/tests/test_pool_hub.py` (modified) | test | transform | 模块内 AST 守卫 (788-895) + `_write_snapshot` 夹具 (148-159) | exact (in-file) | `backfill_needed` GET-only 回归；若 backfill 端点进 pool.py 则扩展守卫（Divergence 3） |

## Pattern Assignments

### 1. `backend/app/services/pool_backfill.py` (new, service / batch)

**Analogs:** `services/extend_history.py::run_extend_history`（用户触发后台服务的骨架 + 进度协议）+ `jobs/daily_pipeline.py::_pool_eod_persist`（单日 run_all→persist 序列）+ `api/data.py::_safe_aggregate_enriched`（enriched 分区 glob 枚举）。

**Imports 模式（复制 extend_history.py:10-19 的 stdlib 集合 + 既有服务依赖）:**
```python
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime

from app.services import pool_snapshot
from app.services.pipeline_jobs import job_store, release_run_slot, try_acquire_run_slot
from app.services.screener import ScreenerService

logger = logging.getLogger(__name__)

def _noop(stage: str, pct: int, msg: str, **kwargs) -> None:  # noqa: ARG001
    pass
```

**缺口集计算（幂等核心 — 复用 pool_snapshot.py:120-133 的 `list_snapshot_dates` + data.py:170-190 的分区 glob 形）:**
```python
# enriched 侧 (复制 data.py:172-179 的 date=* 目录枚举; 无 list_enriched_dates helper, 需 glob)
def _list_enriched_dates(data_dir: Path) -> list[str]:
    enriched_dir = data_dir / "kline_daily_enriched"
    if not enriched_dir.exists():
        return []
    return sorted(d.name[5:] for d in enriched_dir.iterdir()
                  if d.is_dir() and d.name.startswith("date="))

# 缺口 = enriched − 已快照 (list_snapshot_dates 已含 part.json 过滤, pool_snapshot.py:120-133)
def _gap_dates(data_dir: Path) -> list[str]:
    enriched = set(_list_enriched_dates(data_dir))
    snapshotted = set(pool_snapshot.list_snapshot_dates(data_dir))
    return sorted(enriched - snapshotted)  # 升序 (HIST-04: 摊销 150 天 warmup)
```

**主函数（逐日循环 — 复制 _pool_eod_persist 的单日序列 daily_pipeline.py:995-1007，但删掉 write_cache）:**
```python
def run_pool_backfill(
    repo, *, max_days: int | None = None, start: str | None = None,
    end: str | None = None, on_progress: Callable | None = None,
) -> dict:
    """用户触发的批量回填: 对每个缺口日 run_all_with_hits + persist_point_snapshot。

    - 日期集 = enriched 分区 − 含 part.json 的快照分区 (幂等跳过已快照日, HIST-01.2)。
    - 对每目标日: svc.run_all_with_hits(d) + persist_point_snapshot(d, origin="backfill")。
    - 铁律 (ARCHIVE R1): 绝不调 strategy_cache.write_cache — 防污染 single-as_of 最新指针。
    - 升序处理 (HIST-04): 相邻日共享 150 天 warmup (screener.py:354-385 慢路径)。
    - 返回 {backfilled: N, failed: N, failed_dates: [...], dates: [...]} 终态如实反映部分失败。
    """
    emit = on_progress or _noop
    svc = ScreenerService(repo)
    data_dir = repo.store.data_dir
    engine = None  # 调用方传入 app_state.strategy_engine 时经 kwargs 注入

    dates = _gap_dates(data_dir)
    if start:
        dates = [d for d in dates if d >= start]
    if end:
        dates = [d for d in dates if d <= end]
    if max_days:
        dates = dates[:max_days]
    if not dates:
        return {"backfilled": 0, "failed": 0, "failed_dates": [], "dates": []}

    fingerprint = pool_snapshot.strategy_fingerprint(engine) if engine else "unknown"
    backfilled, failed, failed_dates = 0, 0, []
    emit("pool_backfill", 0, f"回填缺口 {len(dates)} 日…")
    for i, ds in enumerate(dates):
        as_of = date.fromisoformat(ds)  # _gap_dates 来自 date=* 分区名, 已合法
        try:
            results = svc.run_all_with_hits(as_of, engine=engine)
            if results:
                # 只落冻结快照, origin="backfill"; 绝不 write_cache (HIST-01.3)
                pool_snapshot.persist_point_snapshot(
                    data_dir, ds, results,
                    strategy_version=fingerprint,
                    computed_at=datetime.now().isoformat(timespec="seconds"),
                    origin="backfill",
                )
                backfilled += 1
        except Exception as e:  # noqa: BLE001 — 失败日记录并继续 (HIST-04.3)
            logger.exception("backfill %s failed: %s", ds, e)
            failed += 1
            failed_dates.append(ds)
        emit("pool_backfill", int(100 * (i + 1) / len(dates)),
             f"回填 {ds} ({i + 1}/{len(dates)}, 成功 {backfilled}, 失败 {failed})")
    emit("done", 100, f"回填完成: {backfilled} 成功, {failed} 失败")
    return {"backfilled": backfilled, "failed": failed,
            "failed_dates": failed_dates, "dates": dates}
```

**Deltas（新形态，无既有单文件 analog）:**
- `engine` 经 kwargs 注入（`run_all_with_hits` 同形，services/screener.py:727；EOD job 从 `app_state.strategy_engine` 拿，daily_pipeline.py:997）。
- 单飞/执行槽**不在 service 内**做——service 只收 `on_progress`，由调用方（API 端点）按 `extend_history` 端点形包 `job_store.create` + `try_acquire_run_slot`（见 #3）。
- `_gap_dates` 每次调用重算（回填中若与手动 run_all 并发写同分区，`persist_point_snapshot` 幂等覆盖保证最终一致，pool_snapshot.py:50-97 同 as_of 原子覆盖）。

---

### 2. `backend/app/services/pool_snapshot.py` (modified, service / file-I/O)

**Analog:** 模块内 `persist_point_snapshot` (50-97) + `load_point_snapshot` (102-117) + `_SCHEMA_VERSION` (34)。

**payload 增 `snapshot_origin`（HIST-02 — 诚实字段先例 `snapshot_type` L78-87 同形）:**
```python
    payload = {
        "as_of": as_of,
        "computed_at": computed_at,
        "strategy_version": strategy_version,
        "snapshot_type": "point",
        "schema_version": _SCHEMA_VERSION,
        "snapshot_origin": origin,          # ← 新增: "eod" | "backfill" | "manual"
        "results": results,
    }
```

**签名扩展 + 向后兼容容错（HIST-02.1 — 复制 load_point_snapshot 的防御返回 None 形 L102-117）:**
```python
def persist_point_snapshot(
    data_dir: Path, as_of: str, results: dict,
    strategy_version: str, computed_at: str,
    origin: str = "eod",                    # ← 新增, 默认 eod 保证旧调用点零改动
) -> Path:
    if origin not in ("eod", "backfill", "manual"):
        raise ValueError(f"invalid snapshot_origin: {origin!r}")

# load 侧容错: 旧文件缺 snapshot_origin → 默认 "eod" (schema_version 保持 1, 向后兼容)
def _origin_of(payload: dict) -> str:
    return payload.get("snapshot_origin") or "eod"
```

**Deltas:**
- **schema 演进决策点（HIST-02.1）:** 建议 `_SCHEMA_VERSION` 保持 1 + 读侧容错缺字段（旧文件默认 `"eod"`），避免强制迁移历史 part.json；若决定递增 schema_version，需同步 `load_point_snapshot` 分版本解析。
- 新增 `_list_enriched_dates`/`list_snapshot_dates` 之外是否需要 `list_enriched_dates` helper 放本模块，由 planner 定——放本模块可让 `pool_backfill` 与未来 `backfill_needed` 计算共用（`_gap_dates` 单点）。
- **注意 E3 守卫（test_pool_hub.py:880-888）:** 本模块继续**不 import** strategy_cache——snapshot_origin 只在 persist/load 层加，不触碰 cache。

---

### 3. `backend/app/api/pipeline.py`（推荐）或 `api/backfill.py`（new, POST 触发端点）

**Analog:** `api/kline.py::extend_history` (633-700) — 异步触发 + job_store 单飞 + 执行槽互斥。**这是回填触发端点的逐行模板。**

**端点形（复制 api/kline.py:633-700 — `extend_history` 的完整骨架，替换调用目标）:**
```python
@router.post("/backfill")
async def pool_backfill(request: Request) -> dict:
    """批量回填历史缺口 — 用户触发, 后台 job, 返回 job_id 可轮询 /jobs/{id}。

    body: { "max_days": int|None, "start": "YYYY-MM-DD"|None, "end": "YYYY-MM-DD"|None }
    """
    import asyncio
    body = await request.json()
    repo = request.app.state.repo
    engine = getattr(request.app.state, "strategy_engine", None)

    from app.services.pool_backfill import run_pool_backfill
    from app.services.pipeline_jobs import job_store, release_run_slot, try_acquire_run_slot

    job_id, is_new = job_store.create()
    if not is_new:
        return {"status": "reused", "job_id": job_id}   # 单飞: 复用活跃任务

    async def task() -> None:
        if not try_acquire_run_slot():                  # 与 EOD/手动 run_all 互斥
            job_store.fail(job_id, "已有数据任务在运行(或上一次任务卡死未结束),请稍后再试")
            return
        loop = asyncio.get_event_loop()
        def progress(stage, pct, msg, stage_pct=None, skip_log=False):
            job_store.progress(job_id, stage, pct, msg, stage_pct=stage_pct, skip_log=skip_log)
        try:
            job_store.start(job_id)
            result = await loop.run_in_executor(
                _long_task_executor,                       # api/kline.py 顶部线程池 (L17-18)
                lambda: run_pool_backfill(repo, max_days=body.get("max_days"),
                                          start=body.get("start"), end=body.get("end"),
                                          on_progress=progress),
            )
            job_store.succeed(job_id, result)
        except Exception as e:  # noqa: BLE001
            logger.exception("pool backfill failed: job_id=%s", job_id)
            job_store.fail(job_id, str(e))
        finally:
            release_run_slot()

    asyncio.create_task(task())
    return {"status": "started", "job_id": job_id}
```

**Deltas / 决策点（Divergence 3，必须 planner 定）:**
- 研究草案写 `POST /api/pool/backfill`（ARCHIVE.md 触发方式），但 **pool.py 的 GET-only AST 守卫（test_pool_hub.py:836-841）锁死**。两条出路：
  - **出路 A（推荐，零守卫改动）:** 端点放 `api/pipeline.py` → `POST /api/pipeline/backfill`。`api/pipeline.py` 已有 `POST /run` + `POST /jobs/{id}/cancel`（api/pipeline.py:37-110），完全同构，不触碰 pool 守卫。前端消费路径需在 `frontend` 改 URL（本 phase 前端零改动目标下,仅后端契约变更）。
  - **出路 B（保留 /api/pool/backfill 路径）:** 有意扩展 `test_pool_api_is_get_only`（test_pool_hub.py:836-841）允许「仅 `/backfill` 一个 POST，其余全 GET」，并同步检查 E5 `test_pool_api_no_compute_trigger`（891-895）——pool.py 源码出现 `run_all`/`persist_point_snapshot` token 即红，故端点体**必须**只调 `pool_backfill.run_pool_backfill(...)` 间接层（该 token 不在 E5 黑名单）。
- 端点体**不** import 执行族（broker/order/trade），`pool_backfill.py` 只 import pool_snapshot/screener/pipeline_jobs——即使走出路 B 也过 E1/E6 守卫。

---

### 4. `backend/app/api/pool.py` (modified, controller / GET-only)

**Analog:** 模块内 `get_pool_dates` (55-65) — 追加 `backfill_needed` 缺口信号（HIST-03.1）。

**`/dates` 增补（复制 get_pool_dates 的零执行 GET-only 形 + data.py:172-179 的 enriched glob）:**
```python
@router.get("/dates")
def get_pool_dates(request: Request):
    """列出含冻结式点快照的可用日期 (ISO desc) + 存档缺口信号 (HIST-03)。

    backfill_needed = enriched 分区 − 含 part.json 的快照分区; GET-only 零执行权 (POOL-03)。
    """
    data_dir = request.app.state.repo.store.data_dir
    dates = list_snapshot_dates(data_dir)
    enriched_dates = {...}  # 复用 pool_snapshot.list_enriched_dates (或 pool_backfill._list_enriched_dates)
    backfill_needed = sorted(set(enriched_dates) - set(dates))
    return {
        "dates": dates, "count": len(dates), "latest": dates[0] if dates else None,
        "backfill_needed": backfill_needed,        # ← 新增 (HIST-03)
        "backfill_needed_count": len(backfill_needed),
    }
```

**Deltas:**
- **保持 GET-only 与零执行（守卫 E4/E5 天然覆盖，test_pool_hub.py:836-841/891-895）。** 本改动只加只读字段，不碰任何写路径。
- 读侧如需按 origin 过滤历史视图（HIST-02.3），在 `build_pool_hub_snapshot`（pool_hub.py:225-256）透传 `snapshot_origin` 即可——响应加 `snapshot_origin` 键，既有 `available:False` 空态与形状不破坏（回归锁，test_pool_hub.py:760-770）。

---

### 5. `backend/app/jobs/daily_pipeline.py` (modified, job/scheduler)

**Analog:** 模块内 `_pool_eod_persist` (966-1008) — 唯一改动是 `persist_point_snapshot` 传 `origin="eod"`。

**EOD 写 origin（复制 daily_pipeline.py:1001-1007 的 persist 调用块，加一个参数）:**
```python
        pool_snapshot.persist_point_snapshot(
            data_dir,
            str(as_of),
            results,
            strategy_version=pool_snapshot.strategy_fingerprint(app_state.strategy_engine),
            computed_at=datetime.now().isoformat(timespec="seconds"),
            origin="eod",                              # ← 新增 (HIST-02.2)
        )
```

**Deltas:**
- `_run_tracked`（L722-760）与 `start_scheduler` 注册块（L1081-1088）**零改动**——回填不注册 cron（用户触发，HIST-01.1）。
- EOD 语义不变：仍「先 write_cache 再 persist」（L1000-1007）——EOD 是**最新日**，写 cache 正确；回填才是历史日禁写 cache。**不要把 EOD 的顺序照搬给回填（ARCHIVE R1）。**

---

### 6. `backend/app/api/screener.py` (modified, controller)

**Analog:** 模块内 `run_all` (408-465) — 指针污染修复点 + manual origin。

**修复「历史 as_of 写 cache 污染」（ARCHIVE R1 附带 + HIST-02.2 — 复制 L443-457 调用块，改条件）:**
```python
    # 写入策略缓存 (供页面秒加载) — 仅最新日写, 历史 as_of 写会污染 single-as_of 指针
    if results:
        latest = svc.latest_date()
        if latest is not None and str(latest) == str(as_of):
            try:
                strategy_cache.write_cache(data_dir, str(as_of), results)
            except Exception:  # noqa: BLE001
                pass
        # POOL-04 调用点 1: 落冻结式点快照 (只落当次 results, 无 union 键); origin="manual"
        try:
            pool_snapshot.persist_point_snapshot(
                data_dir,
                str(as_of),
                results,
                strategy_version=pool_snapshot.strategy_fingerprint(engine),
                computed_at=datetime.now().isoformat(timespec="seconds"),
                origin="manual",                       # ← 新增 (HIST-02.2)
            )
        except Exception:  # noqa: BLE001
            pass
```

**Deltas / 决策点:**
- **「历史 as_of 跳过 write_cache」是否本 phase 一并修**是 ARCHIVE R1 的开放问题（SUMMARY.md「Gaps to Address」）。修复是向后兼容的行为收紧（最新日行为不变），建议修；planner 需在 PLAN 里锁一条回归：`GET /api/pool/hub` 在手动跑历史 run_all 后仍回显最新日。
- 另一处单策略 `_update_cache_strategy`（api/screener.py:209-210 的 `write_cache`）不受影响（单跑只更新当日前缀），**不要**动。

---

### 7. `backend/tests/test_pool_backfill.py` (new, test)

**Analog:** `test_pool_eod_job.py` `_make_app_state` (51-96) + `test_pool_snapshot.py` `_FakeRepo`/`_write_canned_strategy` (129-190)。**回填测试的核心断言是「跑完回填后 strategy_cache.json 不存在/未变」**——这是 HIST-01.3 与 ARCHIVE R1 的锁。

**hermetic 装配（复制 test_pool_eod_job.py:51-96 `_make_app_state` — fake repo + canned 策略 + StrategyEngine）:**
```python
class _FakeRepo:
    """最小 repo 桩 (复制 test_pool_eod_job.py:61-75, 追加 enriched 分区 glob 需要的 store.data_dir)。"""
    def __init__(self, data_dir, enriched, latest, instruments=None):
        self.store = SimpleNamespace(data_dir=data_dir)
        self._enriched = enriched
        self._latest = latest
        self._instruments = instruments if instruments is not None else pl.DataFrame()

    def get_enriched_latest_asset(self, asset_type): return self._enriched, self._latest
    def get_instruments_asset(self, asset_type):     return self._instruments
    def get_enriched_history(self, target_date, lookback_days): return None
    def enriched_latest_date(self):                  return self._latest
```

**零指针污染断言（新 guard — HIST-01.3/ARCHIVE R1 锁死）:**
```python
def test_backfill_never_writes_strategy_cache(tmp_path, monkeypatch):
    """回填写冻结快照, 但 strategy_cache.json 不被创建/改动 (铁律)。"""
    # ... 造多个 enriched 分区 (date=2026-08-01/02/03 的 part.parquet 桩) + 已有 1 个快照 ...
    result = run_pool_backfill(_FakeRepo(tmp_path, ...))
    assert result["backfilled"] == 2                      # 缺口补齐, 已快照日跳过
    for d in ("2026-08-01", "2026-08-02"):
        assert (tmp_path / "screener_results" / f"date={d}" / "part.json").exists()
    assert not (tmp_path / "user_data" / "strategy_cache.json").exists()   # ← 铁律
```

---

### 8. 其余测试文件 (modified)

- **`test_pool_snapshot.py`:** 在 `test_snapshot_roundtrip_no_ever_rows`（191-221）旁新增 `test_snapshot_origin_roundtrip_and_tolerance`——persist(origin="backfill") → payload 含 `snapshot_origin=="backfill"`；手写旧 payload（无 origin 键）→ `_origin_of` 默认 `"eod"`。夹具直接复用 `_write_snapshot_payload`（46-67）。
- **`test_pool_eod_job.py`:** `test_pool_eod_persist_writes_snapshot_and_cache`（98-128）加 `assert snap["snapshot_origin"] == "eod"`；`test_pool_eod_job_registered_in_scheduler`（160-173）的 grep 门禁旁新增「回填 job 源码不含 `write_cache`」grep 守卫。
- **`test_pool_hub.py`:** 在 `test_pool_dates_api`（704-724）旁加 `backfill_needed` 断言；若走 Divergence 3 出路 B，改 `test_pool_api_is_get_only`（836-841）与 E5（891-895）。

---

## Shared Patterns

### 原子 JSON 写 + as_of 严格校验（复制 pool_snapshot.py:33,50-97 — 所有新写路径）
```python
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")          # 防路径穿越, 拼路径前 fullmatch
# persist 内: part_dir.mkdir(parents=True, exist_ok=True) → temp + os.replace 原子替换
tmp = path.with_name(path.name + ".tmp")
tmp.write_text(json.dumps(payload, ensure_ascii=False, default=_json_default), encoding="utf-8")
os.replace(tmp, path)
```

### 进度协议（复制 extend_history.py:47-48 `_noop` + 各阶段 `emit(stage, pct, msg)` — 所有后台 job）
```python
def _noop(stage: str, pct: int, msg: str, **kwargs) -> None:  # noqa: ARG001
    pass
emit = on_progress or _noop
emit("pool_backfill", 0, "回填缺口 N 日…")
emit("pool_backfill", int(100 * (i + 1) / len(dates)), f"回填 {ds}…")
emit("done", 100, "回填完成…")
```

### 单飞 + 执行槽互斥（复制 api/kline.py:633-700 + pipeline_jobs.py:299-325 — 回填端点与 EOD/手动 run_all 并发防护）
```python
job_id, is_new = job_store.create()        # pending∨running 去重 (pipeline_jobs.py:99-120)
if not is_new: return {"status": "reused", "job_id": job_id}
# 开跑前 try_acquire_run_slot(); finally release_run_slot() (pipeline_jobs.py:313-325)
```

### 诚实字段 / 空态（Phase 24 全部写路径的 provenance 义务 — 复制既有先例）
| 先例 | 位置 | Phase 24 沿用 |
|---|---|---|
| `snapshot_type:"point"` + `schema_version` + `as_of`/`computed_at`/`strategy_version` | pool_snapshot.py:78-87 | + `snapshot_origin`（HIST-02） |
| `available:False` 诚实空态（200 非 404） | pool_hub.py:246-252 | 快照缺失语义不变 |
| `concept_attribution:"current_snapshot"` 诚实标注 | pool_hub.py:182 / 251 | origin 透传同族 |
| `skipped:"no data date"` 诚实 skip | daily_pipeline.py:970-975 | 回填无缺口返回 `{backfilled:0,...}` |

### hive 分区日期枚举（复制 daily_pipeline.py:386-390 / data.py:172-179 — 回填缺口集与 backfill_needed 的 source of truth）
```python
dates = sorted(d.stem.split("=")[1] for d in enriched_dir.glob("date=*"))   # daily_pipeline.py:387
# data.py:172-179 等价: d.is_dir() and d.name.startswith("date=") → d.name[5:]
```

## No Analog Found

| File | 缺什么 | 建议来源 |
|---|---|---|
| `pool_backfill.py` 的「缺口集 = enriched − 快照」计算 | 无既有 `list_enriched_dates` helper，也无 backfill 类 job（grep 证实） | 用 daily_pipeline.py:386-390 + pool_snapshot.py:120-133 两个既有 glob 组合；HIST-03 的 `backfill_needed` 与回填共用同一 `_gap_dates` 单点 |
| `snapshot_origin` 字段本身 | 快照 payload 目前无「来源」维（只有 `snapshot_type` 形态维） | 镜像 `snapshot_type`（pool_snapshot.py:82）的枚举字段写法；读侧默认 `"eod"` 容错 |

## 命名与约定（与现有风格一致）

| 维度 | 约定 | 先例 |
|---|---|---|
| 服务模块 | 小写下划线：`pool_snapshot.py` / `strategy_cache.py` / `pool_backfill.py` | 现有 services/ |
| 用户触发服务函数 | `run_<动词>`：`run_extend_history` → **`run_pool_backfill`** | extend_history.py:102 |
| 进度回调签名 | `emit(stage, pct, msg, stage_pct=None, skip_log=False)`；默认 `_noop` | daily_pipeline.py:48, extend_history.py:47 |
| 诚实 skip 返回 | `{"as_of": None, "skipped": "no data date"}` 形；回填用 `{"backfilled": 0, "failed": 0, ...}` | daily_pipeline.py:970-975 |
| as_of 校验 | 模块级 `_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")` | pool_snapshot.py:33, api/pool.py:22 |
| 端点前缀 | `api/pipeline.py` 已有 `POST /run` + `/jobs/{id}` + `/jobs/{id}/cancel`；backfill 触发端点镜像 | api/kline.py:633 |
| 测试文件 | `test_<module>.py`；hermetic fixture（不 import 其他测试模块） | test_pool_eod_job.py, test_pool_snapshot.py |
| 守卫测试 | 读源码文本断言（AST/grep），不启动真调度器 | test_pool_hub.py:788-895, test_pool_eod_job.py:160-173 |

## Metadata

**Analog search scope:** `backend/app/services/`（pool_snapshot / strategy_cache / screener / pool_hub / pipeline_jobs / extend_history）、`backend/app/api/`（pool / screener / pipeline / kline / data）、`backend/app/jobs/daily_pipeline.py`、`backend/tests/`（test_pool_snapshot / test_pool_eod_job / test_pool_hub）
**Files scanned:** 12（源码 8 + 测试 4）
**Pattern extraction date:** 2026-08-06
**Line numbers verified against live code:** 全部 excerpt 行号在本 session 逐行读取确认（pool_snapshot.py:31-149、strategy_cache.py:121-170、services/screener.py:245-811、daily_pipeline.py:722-1167、api/pool.py:22-102、api/screener.py:209-465、api/kline.py:633-700、api/pipeline.py:1-110、api/data.py:86-215、pipeline_jobs.py:99-325、extend_history.py:102-225、pool_hub.py:83-256、test_pool_hub.py:788-895、test_pool_eod_job.py:51-173）
