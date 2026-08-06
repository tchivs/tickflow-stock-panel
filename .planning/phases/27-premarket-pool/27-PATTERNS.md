# Phase 27 模式映射:盘前股池 (Premarket Pool)

**Mapped:** 2026-08-06
**Files analyzed:** 15(后端 app 7 / 前端 src 6 / 测试 2:后端 1 + e2e 1)
**Analogs found:** 16 / 16(in-file exact 8 / 外部 exact 7 / 外部 role-match 1)

> 本文件把 Phase 27(PM-01..04)的每个新建/修改文件映射到仓库内最接近的既有实现,并给出可直接复制/镜像的具体代码段(带文件路径与行号,全部在本 session 逐行读取确认)。Research 依据:`.planning/research/v2.1-depth/PREMARKET.md`(盘前方案 B:09:26 预览 + 独立存储 + open_gap 补算 + probe 诚实缺席)。
>
> **一句话总结:** PM-01 是后端新 job——镜像 `_pool_eod_persist`(`daily_pipeline.py:966-1008`)的「service 级共享核心 + `_run_tracked` 单飞 + mon-fri cron 注册」骨架,但**只写独立 `premarket_results/date={T}/part.json`、绝不调 `strategy_cache.write_cache`**(镜像 `pool_backfill.py:1-11` 的「绝不写缓存」铁律);PM-02 是 `compute_enriched_today`(`pipeline.py:1250-1540`)补 `open_gap`——单一实现复制 Pass 4 公式(`pipeline.py:499-507`,绝不双源漂移);PM-03 复用 `resolve_auction_probe` injectable 判定(`auction_probe.py:139-181`)做今日窗口探测,读时注入沿用 `attach_auction_columns` 双闸门(`auction_columns.py:89-150`);PM-04 是前端——预览池独立端点 `GET /api/pool/premarket`(镜像 `pool.py:79-113 get_pool_history` 的 available:false + 严格 as_of 校验),窗口标注复用 `AuctionColumnStatusBadge` 盘前分支(`StockListTable.tsx:72-122`),DateNavigator 继续只列 EOD dates(`pool/dates` 白名单,PM-04 禁喂盘前日)。
>
> **给 planner 的第一优先级决策点:**
> 1. **盘前 job 绝不写 `strategy_cache`**:`pool_backfill.py:1-11` 的模块 docstring 就是先例——「历史日写入即污染 single-as_of 最新指针」。盘前预览同样如此(PM-01 验收 3)。新存储常量 `_PREMARKET_ROOT = "premarket_results"` 必须与 `_SNAPSHOT_ROOT = "screener_results"`(`pool_snapshot.py:31`)物理分离。
> 2. **open_gap 补算只放一个 seam**:Pass 4(`pipeline.py:499-507`)与 `compute_enriched_today` 是两套独立实现,盘前补算必须**复制 Pass 4 的公式与守卫**(`pl.when(prev_close > 0).then(open / prev_close - 1).otherwise(None)`),做成单一 helper 或逐字复制,否则 EOD/盘前口径漂移(除权日口径由 fixture 锁死)。
> 3. **盘前 `vol_ratio_5d` 失真禁用**:`compute_enriched_today` 中 `elapsed_minutes=0` → `time_factor=1.0`(`pipeline.py:1423-1429`),把竞价量当全天量。盘前预览不展示 `vol_ratio_5d`,优先 `auction_volume_ratio`(PIT-safe,`auction_columns.py:54-87`)。
> 4. **新端点必须进 guest 白名单**:`main.py:779-785 _GUEST_READ_GET_PATHS` 加 `/api/pool/premarket`,否则游客访问盘前页 401(镜像 `tests/test_guest_masking.py` 守卫)。
> 5. **e2e 必须注册新 mock**:`pool-hub.spec.ts:268-309 installShell` 把 `**/api/**` 全 mock 成 500,新路由不注册会大声失败。

## 关键约束与危险区(先读)

| 边界 | 位置 | 本阶段影响 |
|---|---|---|
| **strategy_cache 单 as_of 指针,盘前绝不污染** | `strategy_cache.py:25-31`(锁)、`:98-173 write_cache`;`pool_backfill.py:1-11`(先例:历史日写即污染) | 盘前预览**绝不调 `strategy_cache.write_cache`**;独立存储 `premarket_results/date=*` |
| **EOD 快照语义不动** | `pool_snapshot.py:31 _SNAPSHOT_ROOT="screener_results"`、`:52-104 persist_point_snapshot`(只落当次 results,POOL-04) | 盘前预览不写 `screener_results/date=*`,不把 `today_ever_rows` union 混入 |
| **POOL-03 零执行权(GET-only AST 守卫)** | `api/pool.py:1-7` 模块 docstring;`tests/test_pool_hub.py`(T-18-01 E4/E5) | 新 `GET /api/pool/premarket` 只读;预览生成只在 job 内,端点绝不触发计算/写盘 |
| **`available:false` 诚实空态(200 非 404)** | `api/pool.py:88` + `:100-107` as_of 双重校验;`pool_hub.py:243-250` 空态形状 | 盘前预览无数据/非工作时段 → 200 `{available:false}`;绝不 404、绝不伪装零池 |
| **probe×分区双闸门(诚实缺列)** | `auction_columns.py:89-150 attach_auction_columns`;`auction_probe.py:139-181` | 盘前竞价列仅在「今日 probe available 且源有窗口行」时注入;否则缺席 + `degraded:true` |
| **open_gap 单一实现,勿双源漂移** | Pass 4 `pipeline.py:499-507`;`compute_enriched_today` `pipeline.py:1250-1540` 当前**不算** open_gap | 补算复制 Pass 4 公式与 `prev_close > 0` 守卫;除权日口径 fixture 锁死 |
| **盘前 vol_ratio_5d 失真** | `market_time.py:31-48`(开盘前=0)→ `pipeline.py:1423-1429 time_factor=1.0` | 盘前帧禁用 `vol_ratio_5d`;用 `auction_volume_ratio`(PIT-safe)或明确不展示 |
| **DateNavigator 只列 EOD 快照日** | `DateNavigator.tsx:5-8`(dates prop = `/api/pool/dates` 白名单);`pool.py:36-58 get_pool_dates` | 盘前预览日**不进** dates 白名单;盘前视图独立入口,不冒充归档日 |
| **`Watchlist.tsx` 用户未提交改动** | `frontend/src/pages/Watchlist.tsx`(1346 行,未提交) | **绝不修改/提交/read 内容**;前端改动只在 pool-hub 面 + lib |
| **零新 npm/pip 依赖** | 项目约束 | 后端全用既有 seam(`run_all_with_hits`/`_run_tracked`/`pool_snapshot`/`attach_auction_columns`);前端零新包 |
| **前端验证 = build + e2e,无 vitest** | 项目约束 | PM-04 验收 = `npm run build` 全绿 + Playwright e2e(mock 预览/空态/降级) |
| **guest 掩码只属股池 Hub 面** | `pool.py:24-26,33-34,110-113 mask_guest_hub`;`services/guest_masking.py` | 盘前预览若展示行集,沿用 `mask_guest_hub` + `mode` 声明;新端点进 guest 白名单 |
| **当前环境湖 0 分区 / 无内置 auction 源** | PREMARKET.md §3(所有内置 provider `auction=False`) | PM-02/03 验收用 fixture/mock;UI 必须诚实空态 |

## 目标文件 → analogs 表

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality | 关键差异 |
|---|---|---|---|---|---|
| `backend/app/jobs/daily_pipeline.py` (modified) | job/scheduler | batch (调度→生成) | `_pool_eod_persist` `daily_pipeline.py:966-1008` + `_run_tracked` `:722-770` + cron 注册块 `:1076-1088` | exact | 新 `_PREMARKET_JOB_ID` + `_premarket_pool_preview`;cron 09:26 mon-fri;只写独立存储、**不 write_cache** |
| `backend/app/services/premarket_pool.py` (new) | service | batch (run_all + 独立落盘) | `pool_backfill.run_pool_backfill` `pool_backfill.py:22-75`(job service 骨架)+ `_pool_eod_persist` `:966-1008`(orchestration) | role-match | 单日 as_of=today;加 open_gap 补算 + probe verdict + `window:"pre_open"` payload;独立 root |
| `backend/app/services/pool_snapshot.py` (modified) | service | file-I/O (原子写/读) | `persist_point_snapshot` `pool_snapshot.py:52-104` + `_snapshot_path` `:48-49` + `load_point_snapshot` `:111-127` + `list_snapshot_dates` `:129-142` | exact (in-file) | 新增 `_PREMARKET_ROOT="premarket_results"` + `persist_premarket_snapshot`/`load_premarket_snapshot`/`list_premarket_dates`(payload 含 window/provisional/degraded) |
| `backend/app/indicators/pipeline.py` (modified) | indicator | transform | Pass 4 open_gap `pipeline.py:499-507`(单一公式源);`compute_enriched_today` change_pct 块 `:1325-1340`(补算插入点) | exact (in-file) | `compute_enriched_today` 追加 open_gap 列(now `pl.when(prev_close>0).then(open/prev_close-1)`);不碰 Pass 4 |
| `backend/app/api/pool.py` (modified) | controller | request-response (GET-only) | `get_pool_history` `pool.py:79-113`(available:false + as_of 双重校验)+ `get_pool_dates` `:36-58` | exact | 新 `GET /api/pool/premarket`;读 `premarket_results` 而非 `screener_results`;无 as_of 参数(固定今日) |
| `backend/app/main.py` (modified) | config/middleware | n/a | `_GUEST_READ_GET_PATHS` `main.py:779-785` | exact (in-file) | 加 `/api/pool/premarket` 一行;守卫 `tests/test_guest_masking.py` |
| `backend/app/services/auction_probe.py` (modified) | service | request-response (判定) | `resolve_auction_probe` `auction_probe.py:139-181` + `_last_trade_date` `:71-84`(探测日语义) | exact (in-file) | 盘前调用时探测目标日 = 今日(而非最新日线分区);新增 premarket 入口或参数,判定词汇不变 |
| `backend/tests/test_premarket_pool.py` (new) | test | hermetic | `test_pool_eod_job.py:24-133`(注册 grep 门禁 + `_FakeRepo` + `_make_app_state`)+ `test_auction_probe.py`(injectable FakeAuctionProvider 强制四态) | exact | 新增:独立存储不污染断言 + open_gap 数值/除权日 fixture + probe degraded 三态 + 09:30 行永不注入 |
| `frontend/src/lib/api.ts` (modified) | utility/client | request-response | `poolHistory` `api.ts:2144-2147` + `poolDates` `:2141-2142` + `AuctionProbeVerdict` `:67-77` | exact (in-file) | 新 `poolPremarket()` + `PremarketPoolResponse`(含 window/degraded/probe 字段) |
| `frontend/src/lib/queryKeys.ts` (modified) | config | n/a | `QK.poolDates`/`QK.poolHistory` `queryKeys.ts:41-45` | exact (in-file) | 新 `QK.poolPremarket`(今日预览易变 → 中等 staleTime) |
| `frontend/src/lib/useSharedQueries.ts` (modified) | hook | request-response | `useAuctionHistory` `useSharedQueries.ts:94-100` + `useAuctionProbe` `:85-91` | exact (in-file) | 新 `usePremarketPool(enabled)`;盘前时段轮询/重取策略 |
| `frontend/src/pages/PoolHubPage.tsx` (modified) | page/component | render | 页内 hub/history 双源切换 `PoolHubPage.tsx:27-41`(selectedDate → 数据源路由)+ `AuctionColumnStatusBadge` 挂载 | exact (in-file) | 新增「查看今日 + 盘前预览存在 → 预览池」分支;独立 window 标注 + 空态;DateNavigator 不动 |
| `frontend/src/components/pool-hub/StockListTable.tsx` (modified) | component | render | `AuctionColumnStatusBadge` `StockListTable.tsx:72-122`(盘前分支已预留) | exact (in-file) | 徽标消费 `degraded`/`window` 字段;预览行集沿用既有列投影 |
| `frontend/src/components/pool-hub/DateNavigator.tsx` (modified or unchanged) | component | render | `DateNavigator.tsx:5-8`(dates prop 白名单)+ `:14-22`(idx===-1 双禁用) | exact (in-file) | **PM-04:dates 只含 EOD 快照日,不喂盘前日**;盘前时 selectedDate 逻辑不变 |
| `frontend/e2e/premarket-pool.spec.ts` (new) | test | e2e mock + assert | `pool-hub.spec.ts:268-309 installShell` + `:261-262 unhandled` + fixture payloads | exact | 新 spec:mock `/api/pool/premarket` 三态(有预览 / available:false / degraded)+ 15:35 后回落 EOD hub |

## Pattern Assignments

### 1. `backend/app/jobs/daily_pipeline.py` (modified, job / scheduler)

**Analog:** `_pool_eod_persist`(`:966-1008`)+ `_run_tracked`(`:722-770`)+ 注册块(`:1076-1088`)。

**Job 常量 + 函数骨架(复制 `_pool_eod_persist` 的 service 级共享核心纪律, 换独立存储):**
```python
# daily_pipeline.py:962-963 既有 EOD 常量 → 新增盘前常量
_PREMARKET_JOB_ID = "premarket_pool_preview"
_PREMARKET_HOUR, _PREMARKET_MINUTE = 9, 26   # 09:25 撮合定盘后 (Asia/Shanghai)

def _premarket_pool_preview(on_progress=None) -> dict:
    """盘前预览 job: run_all_with_hits(as_of=today) → premarket_results/date={T}/part.json。

    - 绝不调 strategy_cache.write_cache (single-as_of 指针, 盘前写入即污染; 镜像
      pool_backfill.py:1-11 铁律)。
    - 无 app state / 无今日 live enriched → 诚实 skip, 不写任何文件。
    - 复用 _run_tracked 单飞 (与手动 run_all / EOD 并发写防护)。
    """
    from app.services import pool_snapshot
    from app.services.premarket_pool import build_premarket_preview   # 新服务
    from app.services.screener import ScreenerService

    app_state = _get_app_state()
    if app_state is None:
        return {"as_of": None, "skipped": "no app state"}
    repo = app_state.repo
    svc = ScreenerService(repo)
    today = cn_today()  # market_time.py:25-28
    if svc.latest_date() is None:   # 无任何 enriched → 无 prev_close 基准, 诚实 skip
        return {"as_of": None, "skipped": "no data date"}
    emit = on_progress or _noop
    emit(_PREMARKET_JOB_ID, 0, f"盘前预览 {today}: 运行全部策略…")
    data_dir = repo.store.data_dir
    payload = build_premarket_preview(repo, engine=getattr(app_state, "strategy_engine", None))
    if payload.get("available"):
        pool_snapshot.persist_premarket_snapshot(data_dir, str(today), payload)  # 独立 root
    emit("done", 100, f"盘前预览完成, {len(payload.get('results', {}))} 个策略")
    return {"as_of": str(today), "strategies": len(payload.get("results", {})), "degraded": payload.get("degraded")}
```

**`_run_tracked` 单飞包裹(复制 `:722-770` 原样, 不改):** `job_store.create()` 去重 + `try_acquire_run_slot()` 重任务槽 + `job_store.start/succeed/fail` + `finally: release_run_slot()`。

**cron 注册(镜像 `:1076-1088` EOD 注册块, 固定 09:26):**
```python
scheduler.add_job(
    lambda: _run_tracked(_premarket_pool_preview, "premarket_pool_preview"),
    trigger=CronTrigger(day_of_week="mon-fri",
                        hour=_PREMARKET_HOUR, minute=_PREMARKET_MINUTE,
                        timezone="Asia/Shanghai"),
    id=_PREMARKET_JOB_ID,
    misfire_grace_time=1800,     # 盘前窗口窄 (09:26 后), 短于 EOD 的 3600
    replace_existing=True,
)
```

### 2. `backend/app/services/premarket_pool.py` (new, service / batch)

**Analog:** `pool_backfill.run_pool_backfill`(`pool_backfill.py:22-75`)+ `_pool_eod_persist`(`daily_pipeline.py:966-1008`)。

**模块 docstring 纪律(镜像 `pool_backfill.py:1-11`: 声明写边界 + 绝不 import 执行族/strategy_cache):**
```python
"""盘前股池预览服务 (PM-01/02/03)。

复用与 EOD/回填完全相同的 ``ScreenerService.run_all_with_hits`` 单条代码路径,
as_of = 今日 T;预览写入独立分区 ``premarket_results/date={T}/part.json``
(payload 含 ``window:"pre_open"`` / ``computed_at`` / ``provisional:true`` /
``degraded`` / probe 判定), **绝不调 strategy_cache.write_cache / 绝不写
screener_results** (EOD 语义不动; single-as_of 指针不污染)。

本模块不 import 执行族模块与 strategy_cache (镜像 pool_backfill 铁律)。
"""
```

**核心编排(镜像 `_pool_eod_persist` 的 service 级共享核心, 换独立存储 + open_gap + probe):**
```python
def build_premarket_preview(repo, engine=None) -> dict:
    from datetime import datetime
    from app.market_time import cn_today
    from app.services.auction_probe import resolve_auction_probe
    from app.services.screener import ScreenerService

    svc = ScreenerService(repo)
    as_of = cn_today()
    # 今日帧来源: quote_service 盘前轮询已 flush 今日 live enriched 到 repo 内存缓存
    # (_load_enriched_for_date 优先级 1, screener.py:252-270); 无缓存 → 慢路径读分区 (盘前 T 分区不存在 → 空帧)
    results = svc.run_all_with_hits(as_of, engine=engine)
    if not results:
        return {"as_of": str(as_of), "available": False, "degraded": True,
                "probe": resolve_auction_probe().to_dict(), "results": {}}
    # PM-02: 帧缺 open_gap → 盘前补算 (compute_enriched_today 已补; 或此处兜底自算, 单一公式复制 pipeline.py:499-507)
    # PM-03: probe verdict + 竞价列读时注入 (attach_auction_columns 双闸门) → real 列或诚实缺席
    return {
        "as_of": str(as_of),
        "available": True,
        "window": "pre_open",
        "computed_at": datetime.now().isoformat(timespec="seconds"),
        "provisional": True,            # close = 开盘/定盘价, 非收盘
        "degraded": probe.status != "available",
        "probe": probe.to_dict(),
        "strategy_version": pool_snapshot.strategy_fingerprint(engine),
        "results": results,
    }
```

### 3. `backend/app/services/pool_snapshot.py` (modified, service / file-I/O)

**Analog（in-file）:** `persist_point_snapshot`(`:52-104`)+ `_snapshot_path`(`:48-49`)+ `load_point_snapshot`(`:111-127`)+ `list_snapshot_dates`(`:129-142`)。

**新 root 常量(复制 `:31` 写法, 与 EOD root 物理分离):**
```python
_SNAPSHOT_ROOT = "screener_results"        # 既有 :31 — EOD 语义, 盘前绝不写
_PREMARKET_ROOT = "premarket_results"      # 新增 — 盘前预览独立存储 (PM-01)
```

**`persist_premarket_snapshot`(镜像 `persist_point_snapshot` 的原子写, 换 root + payload 字段):**
```python
def persist_premarket_snapshot(data_dir: Path, as_of: str, payload: dict) -> Path:
    """原子写盘前预览到 ``premarket_results/date={as_of}/part.json``。

    与 persist_point_snapshot 同形 (temp + os.replace 原子替换, :70-79);
    差异: root 换 _PREMARKET_ROOT, payload 为调用方构造 (含 window/provisional/degraded),
    不在此处重包 results。同 as_of 幂等重写。
    """
    if not isinstance(as_of, str) or not _DATE_RE.fullmatch(as_of):
        raise ValueError(f"invalid as_of: {as_of!r}")
    part_dir = data_dir / _PREMARKET_ROOT / f"date={as_of}"
    part_dir.mkdir(parents=True, exist_ok=True)
    path = part_dir / "part.json"
    try:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, default=_json_default), encoding="utf-8")
        os.replace(tmp, path)
    except Exception as e:  # noqa: BLE001
        logger.warning("写入盘前预览失败: %s", e)
    return path

def load_premarket_snapshot(data_dir: Path, as_of: str) -> dict | None:
    """读盘前预览; 非法 as_of → None (镜像 load_point_snapshot :111-127)。"""
    ...

def list_premarket_dates(data_dir: Path) -> list[str]:
    """列出含 part.json 的盘前预览日期, ISO desc (镜像 list_snapshot_dates :129-142)。"""
    root = data_dir / _PREMARKET_ROOT
    if not root.exists():
        return []
    return sorted((d.name[5:] for d in root.glob("date=*") if (d / "part.json").exists()), reverse=True)
```

**不变的部分(直接复用):** `_DATE_RE`(`:35`)、`_json_default`(`:39-46`)、temp + `os.replace` 原子写(`:70-79`)。

### 4. `backend/app/indicators/pipeline.py` (modified, indicator / transform)

**Analog（in-file）:** Pass 4 `open_gap`(`:499-507`)——单一公式源;`compute_enriched_today` 的 change_pct/change_amount/amplitude 块(`:1325-1340`)——补算插入点。

**现状缺口(已确认):** `compute_enriched_today`(`:1250-1540`)算 change_pct/change_amount/amplitude,但**不算 open_gap**。盘前 live 帧缺此列 → 竞价策略族(`auction_alpha.py:34` 等)盘前空池。

**补算(复制 Pass 4 公式与守卫, 插在 amplitude 块后, 与 `:1325-1340` 同风格):**
```python
# pipeline.py:499-507 (Pass 4 单一公式源) — 盘前补算必须逐字一致, 避免双源漂移
#   开盘涨幅 = 同天 open / 前日 close − 1 (prev_close 来自 live_agg/quote_extra);
#   绝不 shift open —— 那会跨天并引入 lookahead。
# compute_enriched_today 内新增 (镜像 :1325-1340 的 when/otherwise 守卫):
if "open_gap" not in df.columns:
    df = df.with_columns(
        pl.when(pl.col("prev_close") > 0)
          .then(pl.col("open") / pl.col("prev_close") - 1)
          .otherwise(None)
          .alias("open_gap"),
    )
```

**前置条件(在补算前必须已就位, 均在 compute_enriched_today 上游已有):** `prev_close`(API quote_extra, `:1315-1322` 处理)、`open`(今日 OHLCV, `:1260-1275` 已 JOIN)。

**除权日口径:** Pass 4 的 prev_close 来自 `close.shift(1).over("symbol")`(前复权对齐);盘前 quote 原始 prev_close 乘 `_adj_factor` 已对齐(`:1318-1322`)。fixture 断言 `open_gap == open / prev_close - 1` 数值,并覆盖除权日(prev_close 复权 vs 原始)。

### 5. `backend/app/api/pool.py` (modified, controller / GET-only)

**Analog:** `get_pool_history`(`:79-113`)+ `get_pool_dates`(`:36-58`)。

**新端点骨架(复制 `get_pool_history` 的校验与空态, 换数据源):**
```python
@router.get("/premarket")
def get_premarket_pool(request: Request):
    """盘前预览股池 (PM-01/04) — 只读, POOL-03 零执行。

    - 读 ``premarket_results/date={today}/part.json`` (独立 root, 非 screener_results)。
    - 预览缺失/非工作时段 → 200 {available:false, degraded:true} 诚实空态 (非 404)。
    - 与 /hub 同形状投影 (total 权威) + window:"pre_open" + provisional:true +
      probe 判定 + degraded 标志;mode + guest 脱敏与 /hub 一致。
    """
    from app.market_time import cn_today
    from app.services import pool_snapshot
    from app.services.guest_masking import mask_guest_hub

    data_dir = request.app.state.repo.store.data_dir
    snap = pool_snapshot.load_premarket_snapshot(data_dir, cn_today().isoformat())
    if snap is None or not snap.get("available"):
        return {
            "as_of": cn_today().isoformat(), "available": False,
            "degraded": True, "window": "pre_open", "strategies": [],
            "resonance_count": 0, "updated_at": None, "probe": None,
        }
    # 复用 pool_hub._project_hub 投影 (results → 同形状), 再附 window/provisional/degraded/probe
    is_vip = getattr(request.state, "reviewer_principal", None) is not None
    hub = pool_hub.project_premarket(snap)            # 或复用 _project_hub + 附加字段
    hub["mode"] = "vip" if is_vip else "guest"
    if not is_vip:
        hub = mask_guest_hub(hub)
    return hub
```

**空态/校验纪律(复制 `:88` `available:false` 语义; 本端点无 as_of 参数 → 不需要 `:100-107` 双重校验, 但**任何扩展参数**都必须先过 `_AS_OF_RE` + `date.fromisoformat`)。**

### 6. `backend/app/main.py` (modified, config / middleware)

**Analog（in-file）:** `_GUEST_READ_GET_PATHS`(`:779-785`)。

```python
_GUEST_READ_GET_PATHS = frozenset({
    "/api/pool/hub",
    "/api/screener/strategies",
    "/api/pool/dates",
    "/api/pool/history",
    "/api/kline/auction/history",
    "/api/pool/premarket",   # PM-04: 盘前预览对游客只读 (与 hub 同语义)
})
```
**注意:** 任何扩宽都会触发 `tests/test_guest_masking.py` 守卫(T-19-03)——新增测试用例显式断言游客可 GET `/api/pool/premarket` 且不可 POST。

### 7. `backend/app/services/auction_probe.py` (modified, service / 判定)

**Analog（in-file）:** `resolve_auction_probe`(`:139-181`)+ `_last_trade_date`(`:71-84`)+ `_has_in_window_rows`(`:120-137`)。

**盘前探测日语义(PM-03):** `_last_trade_date()` 优先「最新日线分区」(`:71-84`)——盘前首次行情轮询后今日日线分区已存在 → 探测日自动变 T;无需改 `_last_trade_date` 本体,新增一个盘前入口或参数显式传 `trade_date=cn_today()`:

```python
def resolve_auction_probe_premarket(
    *,
    source_resolver: SourceResolver | None = None,
    fetcher: Fetcher | None = None,
) -> AuctionProbeVerdict:
    """盘前探测: 目标日 = 今日 (09:26 撮合定盘后), 判定词汇与 resolve_auction_probe 完全一致。"""
    from app.market_time import cn_today
    _orig = _last_trade_date
    try:
        # 注入 today 作为探测日: 复用同一 fetcher + _has_in_window_rows 窗口规则 (T-16-01 不变)
        ...
    finally:
        ...
```

**判定词汇不变(复制 `AuctionProbeVerdict.to_dict` `:38-46`):** `status/source/probed_at/window:"09:15-09:25"/fallback:"open_gap"/detail`。PM-03 验收 1 要求盘前预览响应携带同词汇判定字段。

**injectable 模式(复制 `:139-181` 签名):** `source_resolver` + `fetcher` 两个注入点,测试用假 provider 强制 `not_configured`/`available`/`fail_closed`/`error` 四态(镜像 `test_auction_probe.py`)。

### 8. `backend/tests/test_premarket_pool.py` (new, test / hermetic)

**Analog:** `test_pool_eod_job.py:24-133`(`_write_canned_strategy` + `_FakeRepo` + `_make_app_state` + 注册 grep 门禁)+ `test_auction_probe.py`(`FakeAuctionProvider` + `_rows` + `_probe`)。

**注册形锁死(grep 门禁, 镜像 `test_pool_eod_job.py` 末尾的 `test_pool_eod_job_registered_in_scheduler`):**
```python
def test_premarket_job_registered_in_scheduler():
    """PM-01 注册形锁死: 常量 + _run_tracked 单飞 + mon-fri cron 09:26 (不启动真调度器)。"""
    import inspect
    from app.jobs import daily_pipeline
    src = inspect.getsource(daily_pipeline)
    assert '_PREMARKET_JOB_ID = "premarket_pool_preview"' in src
    assert "_run_tracked(_premarket_pool_preview" in src
    assert 'hour=9, minute=26' in src
    assert 'timezone="Asia/Shanghai"' in src
```

**独立存储不污染(核心验收 PM-01 #3):**
```python
def test_premarket_preview_never_touches_eod_store(tmp_path, monkeypatch):
    """盘前 job 只写 premarket_results; strategy_cache.json 与 screener_results/date=* 不被改动。"""
    app_state = _make_app_state(tmp_path, latest=date(2026, 8, 6))
    monkeypatch.setattr(daily_pipeline, "_get_app_state", lambda: app_state)
    daily_pipeline._premarket_pool_preview()
    assert (tmp_path / "premarket_results" / "date=2026-08-06" / "part.json").exists()
    assert not (tmp_path / "user_data" / "strategy_cache.json").exists()          # 绝不写缓存
    assert not (tmp_path / "screener_results").exists()                            # 绝不写 EOD 湖
```

**open_gap 数值 + 除权日 fixture(PM-02):** 构造 live 帧(open/prev_close)→ 断言 `open_gap == open/prev_close - 1`;除权日(prev_close 复权 vs 原始)fixture 断言口径一致。

**probe degraded 三态(PM-03):** 注入假 fetcher(镜像 `test_auction_probe.py` 的 `_rows` + `FakeAuctionProvider`):
- 无源 → `not_configured` + derived-only 预览(无 auction 列)
- 仅 09:30+ 行 → `fail_closed` + derived-only
- 有 09:15-09:25 窗口行 → `available` + real 列注入

### 9. `frontend/src/lib/api.ts` (modified, utility/client)

**Analog（in-file）:** `poolHistory`(`:2144-2147`)+ `poolDates`(`:2141-2142`)+ `AuctionProbeVerdict`(`:67-77`)。

```typescript
// 新响应类型 (镜像 AuctionProbeVerdict :67-77 + PoolHubResponse :752-...)
export interface PremarketPoolResponse {
  as_of: string | null
  available: boolean
  window: 'pre_open'
  provisional?: boolean
  degraded?: boolean
  probe?: AuctionProbeVerdict | null
  updated_at: string | null
  strategies: PoolHubStrategy[]
  resonance_count: number
  auction_columns?: AuctionColumnsDecl | null
  mode?: 'guest' | 'vip'
}

// 新方法 (镜像 poolHistory :2144-2147 — 只读 GET, 无参数固定今日)
poolPremarket: () => request<PremarketPoolResponse>('/api/pool/premarket'),
```

### 10. `frontend/src/lib/queryKeys.ts` (modified, config)

**Analog（in-file）:** `QK.poolDates`/`QK.poolHistory`(`:41-45`)。

```typescript
poolDates:          ['pool-dates'] as const,
poolHistory:        (asOf: string) => ['pool-history', asOf] as const,
// PM-04: 盘前预览 (今日固定键; 盘前时段易变 → 中等 staleTime, 15:35 后失效)
poolPremarket:      ['pool-premarket'] as const,
```

### 11. `frontend/src/lib/useSharedQueries.ts` (modified, hook)

**Analog（in-file）:** `useAuctionHistory`(`:94-100`)+ `useAuctionProbe`(`:85-91`)。

```typescript
/** 盘前预览股池 — 只在盘前时段/查看今日时启用 (PM-04); probe 字段驱动 degraded 徽标。 */
export function usePremarketPool(opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: QK.poolPremarket,
    queryFn: api.poolPremarket,
    enabled: opts?.enabled ?? true,
    staleTime: 30_000,          // 盘前值会变 (open 定盘后更新), 与服务端 30s probe TTL 对齐
  })
}
```

### 12. `frontend/src/pages/PoolHubPage.tsx` (modified, page)

**Analog（in-file）:** hub/history 双源切换(`:27-41`)+ `AuctionColumnStatusBadge` 挂载。

**集成点(在既有 selectedDate 数据源路由旁加第三分支):**
```tsx
// 现状: selectedDate ? poolHistory : poolHub (PIT-1 历史必走 /history)
// PM-04: 查看日 == 今日 且 盘前预览存在 → 显示预览池 (独立 payload, 不混入 dates 白名单)
const viewingToday = selectedDate == null && data?.as_of != null && isToday(data.as_of)
const premarket = usePremarketPool({ enabled: viewingToday })
const showPremarket = premarket.data?.available && premarket.data.window === 'pre_open'
// 标注: 盘前预览 · 竞价窗口 09:15-09:25 · 非收盘定稿 (复用 AuctionColumnStatusBadge 盘前分支)
```

**诚实空态(镜像 PIT-2 无快照空态):** `premarket.data?.available === false` → 渲染「今日盘前预览尚未生成 · 09:26 后自动生成」,非 404 非零池伪装。

### 13. `frontend/src/components/pool-hub/StockListTable.tsx` (modified, component)

**Analog（in-file）:** `AuctionColumnStatusBadge`(`:72-122`)。

**复用点(几乎零改动):** 徽标已消费 `auctionColumns.real` + `probe` + `quoteStatus.is_trading_hours`;盘前分支(`:118-122`)「盘前/休市 · 竞价窗口 09:15-09:25 未开始」已预留。PM-04 新增:消费 `degraded` 字段,在 `available:false` 徽标旁加「盘前预览 · 非收盘定稿」标注;行集沿用 `PoolHubStrategy`/`PoolHubRow` 投影,零新列。

### 14. `frontend/src/components/pool-hub/DateNavigator.tsx` (modified or unchanged, component)

**Analog（in-file）:** `:5-8`(dates prop 契约)+ `:14-22`(idx===-1 双禁用)。

**PM-04 边界:** dates 白名单仍来自 `/api/pool/dates`(EOD 快照日,`pool.py:36-58`),盘前日**绝不加入**;`idx === -1` 双禁用逻辑天然保证盘前日不可达(PIT-5)。本文件大概率**零改动**——若需盘前「回到预览」按钮,应放在页面层而非 DateNavigator。

### 15. `frontend/e2e/premarket-pool.spec.ts` (new, e2e mock + assert)

**Analog:** `pool-hub.spec.ts:268-309 installShell` + `:261-262 unhandled`。

**安装外壳(复制 `installShell`, 加盘前 mock):**
```typescript
// 在 installShell 的 `**/api/**` unhandled 之后注册 (后注册优先):
await page.route('**/api/pool/premarket**', route => json(route, premarketPayload))
await page.route('**/api/pool/dates**', route => json(route, DATES_PAYLOAD))   // EOD 白名单不变
await page.route('**/api/data/auction-probe**', route => json(route, probePayloadFailClosed))
```

**用例:** ① 盘前时段 → 预览池 + 「盘前预览 · 非收盘定稿」标注;② `available:false` → 诚实空态;③ `degraded:true` → 徽标不渲染「竞价数据可用」;④ 15:35 后 → 回落 EOD hub(`/api/pool/hub` 语义不变)。

## 复用什么 / 避开什么

### 复用(直接复制/调用, 零新增依赖)

| 复用点 | 位置 | 用途 |
|---|---|---|
| `ScreenerService.run_all_with_hits` | `screener.py:723-812` | 盘前生成共享核心;`as_of=today` 时今日帧走 `_load_enriched_for_date` 优先级 1(repo live enriched 缓存,`screener.py:252-270`) |
| `_load_enriched_for_date` 缓存优先级 | `screener.py:245-297` | 盘前今日帧来源 = quote_service 已 flush 的 live enriched;慢路径(T 分区不存在)→ 空帧 → 诚实 skip |
| `_run_tracked` 单飞 + 重任务槽 | `daily_pipeline.py:722-770` | 盘前 job 与手动 run_all/EOD 并发互斥;`try_acquire_run_slot` 防僵尸并发 |
| `pool_snapshot` 原子写(temp + os.replace) | `pool_snapshot.py:70-79` | 独立 root 的 `persist_premarket_snapshot` 沿用同一原子写 |
| `persist_point_snapshot` payload 纪律 | `pool_snapshot.py:52-104` | 只落当次 results;`_json_default` 处理 date/datetime |
| `pool_backfill` 不写缓存的铁律 | `pool_backfill.py:1-11` | 盘前绝不调 `strategy_cache.write_cache` 的注释先例 |
| `_project_hub` 共享投影 | `pool_hub.py:83-186` | 盘前预览与 EOD 同形状投影(total 权威 + auction_columns 声明) |
| `resolve_auction_probe` injectable | `auction_probe.py:139-181` | 盘前探测判定,source_resolver/fetcher 两注入点;`_has_in_window_rows` 窗口规则(T-16-01) |
| `attach_auction_columns` 双闸门 | `auction_columns.py:89-150` | 竞价列读时注入(probe available + 分区/源有窗口行);`_attach_auction_volume_ratio` PIT-safe(`:54-87`) |
| `available:false` 诚实空态 | `pool.py:88,100-107`;`pool_hub.py:243-250` | 盘前预览缺失 → 200 空态非 404;as_of 双重校验(扩展参数时) |
| `mask_guest_hub` + `mode` 声明 | `pool.py:24-26,33-34,110-113`;`main.py:779-785` | 盘前端点 guest 脱敏 + 白名单 |
| `AuctionColumnStatusBadge` 盘前分支 | `StockListTable.tsx:72-122` | 窗口标注/诚实徽标,已预留「盘前/休市」secondary 行 |
| `DateNavigator` dates 白名单 | `DateNavigator.tsx:5-8`;`pool.py:36-58` | EOD 快照日白名单;盘前日不喂入 |
| `market_time.cn_now/cn_today` | `market_time.py:22-28` | 09:26 判定、as_of=today、时区语义 |
| `CronTrigger(... timezone="Asia/Shanghai")` 注册形 | `daily_pipeline.py:948-950,1033-1038,1067-1069,1083-1085` | 盘前 job 注册;`misfire_grace_time` 取窄值(盘前窗口短) |
| `preferences` 调度 getter 形 | `preferences.py:329-347` | 若盘前时间做偏好(可选),镜像 `get_instruments_schedule`;固定 09:26 则不需要 |

### 避开(绝不复制/绝不触碰)

| 危险模式 | 位置 | 本阶段纪律 |
|---|---|---|
| **`strategy_cache.write_cache`(盘前写即污染 single-as_of 指针)** | `strategy_cache.py:98-173` | 盘前 job/服务绝不调用;`test_premarket_pool.py` 锁死 |
| **写 `screener_results/date=*`(EOD 语义)** | `pool_snapshot.py:31` | 盘前只写 `premarket_results/date=*`;与 `today_ever_rows` union 永不混入(POOL-04) |
| **`kline.get_daily` 空库 live-fetch 兜底** | `kline.py:159-181` | 盘前端点 POOL-03 零执行;空预览 → available:false,绝不触发同步/回填 |
| **`vol_ratio_5d` 盘前失真** | `pipeline.py:1423-1429`(time_factor=1.0) | 盘前帧不展示 vol_ratio_5d;用 `auction_volume_ratio`(PIT-safe)或明确不展示 |
| **open_gap 双源漂移** | `pipeline.py:499-507` vs `:1250-1540` | 补算逐字复制 Pass 4 公式;回归确认不改变 EOD 路径 |
| **`_last_trade_date` 语义误用** | `auction_probe.py:71-84` | 盘前探测目标日 = 今日(显式传参),不靠「最新日线分区」隐式漂移 |
| **DateNavigator 喂盘前日** | `DateNavigator.tsx:5-8` | PM-04:盘前预览独立入口,绝不冒充归档日 |
| **`Watchlist.tsx` 用户未提交改动** | `frontend/src/pages/Watchlist.tsx` | 绝不修改/提交/read 内容 |
| **guest 面逻辑复制进非股池端点** | `pool.py:110-113`;`services/guest_masking.py` | 盘前端点属股池面 → 沿用;但不要扩散到其他非池端点 |
| **零新增依赖** | 项目约束 | 后端零新 pip;前端零新 npm(ECharts 已满足图表需求,盘前无需图) |

## 命名与约定

| 项 | 约定 | 依据 |
|---|---|---|
| 调度 job 常量 | `_PREMARKET_JOB_ID = "premarket_pool_preview"` | 镜像 `_POOL_EOD_JOB_ID = "pool_eod_persist"`(`daily_pipeline.py:962`) |
| job 函数 | `_premarket_pool_preview(on_progress=None) -> dict` | 镜像 `_pool_eod_persist` 签名与 skip 语义(`:966-970`) |
| 存储 root | `_PREMARKET_ROOT = "premarket_results"`(模块级常量) | 镜像 `_SNAPSHOT_ROOT = "screener_results"`(`pool_snapshot.py:31`);hive 分区 `date={as_of}/part.json` |
| payload 字段 | `window:"pre_open"` / `computed_at` / `provisional:true` / `degraded` / `probe` / `results` | PM-01/03 验收;probe 判定词汇 = `AuctionProbeVerdict.to_dict`(`auction_probe.py:38-46`) |
| 服务模块 | `backend/app/services/premarket_pool.py` | 镜像 `pool_backfill.py` 命名;docstring 声明写边界与不 import 约束 |
| API 端点 | `GET /api/pool/premarket`(无参数, 固定今日) | 镜像 `/api/pool/history`(`pool.py:79-113`);进 `_GUEST_READ_GET_PATHS`(`main.py:779-785`) |
| 投影复用 | 盘前预览复用 `_project_hub` 形状 + 附加字段 | `pool_hub.py:83-186`;total 权威,auction_columns 服务端声明 |
| 前端 api | `poolPremarket()` → `PremarketPoolResponse` | 镜像 `poolHistory`(`api.ts:2144-2147`)+ `AuctionProbeVerdict`(`:67-77`) |
| 前端 query key | `QK.poolPremarket = ['pool-premarket']` | 镜像 `QK.poolDates`(`queryKeys.ts:44`) |
| 前端 hook | `usePremarketPool(opts)` | 镜像 `useAuctionHistory`(`useSharedQueries.ts:94-100`);staleTime 30s(对齐 probe TTL) |
| e2e | `frontend/e2e/premarket-pool.spec.ts` | 镜像 `pool-hub.spec.ts` `installShell`(`:268-309`) |
| 测试 | `backend/tests/test_premarket_pool.py` | 镜像 `test_pool_eod_job.py` 注册门禁 + `test_auction_probe.py` injectable |
| 诚实词汇 | 「盘前预览 · 竞价窗口 09:15-09:25 · 非收盘定稿」;绝不把预览标为收盘定稿、不把 09:30 bar 标为竞价数据 | PM-04 验收 3;镜像 UI-SPEC 诚实词汇回归 |

## Metadata

**Analog search scope:** `backend/app/{jobs,services,indicators,api}` + `backend/tests` + `frontend/src/{pages,components/pool-hub,lib}` + `frontend/e2e`
**Files scanned:** 15 目标文件映射;另有 `strategy_cache.py`/`pool_hub.py`/`auction_sync.py`/`preferences.py`/`quote_service.py`/`market_time.py`/`main.py` 作为复用/避开边界逐一核对
**Pattern extraction date:** 2026-08-06
**约束遵守:** 只读研究;未修改任何源码(仅产出本 PATTERNS.md);`Watchlist.tsx` 未 read/修改(仅从既有契约引用)。
