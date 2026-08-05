# Phase 22: 股池日期导航 (Pool Hub Date Navigation) - Pattern Map

**Mapped:** 2026-08-05
**Files analyzed:** 10（3 新增 / 7 修改，含 1 数据 artifact）
**Analogs found:** 10 / 10（exact 9 / role-match 1 / partial 0；另有 4 处子功能级无既有 analog 的缺口，见 No Analog Found）

> 本文件把 Phase 22 的每个新建/修改文件映射到仓库内最接近的既有实现，并给出可直接复制/镜像的具体代码段（带文件路径与行号）。Phase 22 的核心是**冻结式点快照**（POOL-04：只落当次 `results`、绝不落 `today_ever_rows` union）+ **独立只读日期导航**（POOL-05：`GET /api/pool/dates` + `GET /api/pool/history`，`GET /api/pool/hub` single-as_of 契约回归锁死）+ **盘后 EOD 持久化 job**（POOL-06）。原子写与 JSON 序列化逐行复制 `strategy_cache.py`（L169-172 / L26-34）；hive 分区日期 glob 复制 `daily_pipeline.py`（L376-409）；Hub 投影核心从 `pool_hub.py:104-126` 抽 `_project_hub` 纯函数（历史/最新双路径共用）；run_all 核心从 `api/screener.py:414-524` 抽 `ScreenerService.run_all_with_hits`；EOD job 复用 `_run_tracked` 单飞（daily_pipeline.py:722-760）+ `start_scheduler` add_job 注册形。**真正无类比的是 4 个服务/API 级子功能**（strategy 指纹、as_of 严格校验、空态 `available:false` 响应、`build_pool_hub_snapshot`），planner 需以 22-RESEARCH.md RQ1/RQ2 Code Examples 兜底。

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/app/services/pool_snapshot.py` (new) | service | file-I/O (原子 JSON 写 + hive glob) | `strategy_cache.py` `_write_cache_locked` 原子写 (169-172) + `_json_default` (26-34) + `daily_pipeline.py` 分区 glob (376-409) | exact |
| `backend/app/services/pool_hub.py` (modified) | service | request-response | 模块内 `build_pool_hub` 投影循环 (104-126) + `resolved_as_of` (93) + `_build_concept_map` (46-66) | exact (in-file) |
| `backend/app/api/pool.py` (modified) | controller | request-response (GET-only) | 模块内 `get_pool_hub` (20-47) — GET-only + name_for + mask_guest_hub | exact (in-file) |
| `backend/app/api/screener.py` (modified) | controller | request-response | 模块内 `run_all` (414-524) — 核心循环 + hit_factors attach (513-514) + write_cache (522) | exact (in-file) |
| `backend/app/services/screener.py` (modified) | service | request-response | 模块内 `_load_enriched_for_date` (217) + `_load_enriched_history` (377-438) + `latest_date` (676-694) | exact (in-file) |
| `backend/app/jobs/daily_pipeline.py` (modified) | job/scheduler | batch (cron 单飞) | 模块内 `_pipeline_then_refresh` (988-1009) + `_run_tracked` (722-760) + `start_scheduler` add_job (977-1075) | exact (in-file) |
| `backend/tests/test_pool_snapshot.py` (new) | test | transform | `test_pool_hub.py` `_write_strategy_cache` hermetic fixture (43-112) + `test_factor_hits.py::test_run_all_rows_carry_hit_factors` (152-201) 最小 FastAPI 装配 | role-match |
| `backend/tests/test_pool_hub.py` (modified) | test | transform | 模块内 Task 3 AST 守卫 (468-546) — `_EXECUTION_TOKEN`/`_WRITE_PATTERNS`/`_feature_sources`/4 守卫测试 | exact (in-file) |
| `backend/tests/test_guest_masking.py` (modified) | test | transform | 模块内游客白名单测试 (405-427) — `test_guest_cannot_read_authed_surfaces` + `test_guest_read_paths_are_get_only` | exact (in-file) |
| `data/screener_results/date={as_of}/part.json` (new data) | data artifact | file-I/O | `kline_daily_enriched/date=*/part.parquet` hive 分区布局 + `strategy_cache.json` payload 形状 (results 键) | exact (layout) |

## Pattern Assignments

### 1. `backend/app/services/pool_snapshot.py` (new, service / file-I/O)

**Analog:** `strategy_cache.py` `_write_cache_locked` 原子写 (169-172) + `_json_default` (26-34)；`daily_pipeline.py` hive 分区 glob (376-409)。

**Imports 模式（复制 strategy_cache.py:10-20 的 stdlib 集合，追加 `hashlib`）:**
```python
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any
```

**原子写核心（复制 strategy_cache.py:169-172 — temp + os.replace，进程被杀不留下半写文件）:**
```python
    try:
        # 原子写: 先写临时文件再 os.replace, 避免读侧读到半写的 JSON
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, default=_json_default), encoding="utf-8")
        os.replace(tmp, path)
    except Exception as e:  # noqa: BLE001
        logger.warning("写入策略缓存失败: %s", e)
```

**JSON 序列化（复制 strategy_cache.py:26-34 — date/datetime → isoformat）:**
```python
def _json_default(obj: Any) -> Any:
    """处理 date/datetime 等 JSON 不认识的类型。"""
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
```

**hive 分区日期 glob（复制 daily_pipeline.py:387 的 dir.stem.split("=")[1] + sorted 模式）:**
```python
# daily_pipeline.py:387 — enriched_dates = sorted(d.stem.split("=")[1] for d in enriched_dir.glob("date=*"))
def list_snapshot_dates(data_dir: Path) -> list[str]:
    root = data_dir / "screener_results"
    if not root.exists():
        return []
    return sorted(
        (d.name[5:] for d in root.glob("date=*") if (d / "part.json").exists()),
        reverse=True,   # 新日期在前 (daily_pipeline.py:389 取 enriched_dates[-1] 最新语义)
    )
```

**Deltas（新形态，无既有单文件 analog）:**
- `_SNAPSHOT_ROOT = "screener_results"` 常量 + `_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")`（**as_of 严格校验防路径穿越** — 新增模式，见 No Analog Found）。
- payload 形状 `{"as_of", "computed_at", "strategy_version", "snapshot_type": "point", "schema_version": 1, "results"}` — **只接收 `results`，绝不落 `today_ever_rows`**（strategy_cache.py:118-151 的 union 分支**不可复制**到快照）。
- `persist_point_snapshot` 需 `part_dir.mkdir(parents=True, exist_ok=True)`（strategy_cache.py:156 `path.parent.mkdir(parents=True, exist_ok=True)` 同构）——`screener_results/` 当前是空占位目录（repository.py 建目录、无写入方），首次写自动建 `date={as_of}`。
- `strategy_fingerprint` 全新函数（见 No Analog Found / Shared Patterns 8）。

---

### 2. `backend/app/services/pool_hub.py` (modified, service / request-response)

**Analog:** 模块内 `build_pool_hub` (69-126) — 投影循环 (104-126) + 单一数据源回显 (93) + 概念 map (46-66)。

**单一数据源回显（复制 pool_hub.py:93 — 新端点**不得**复用此逻辑，`build_pool_hub` 保留）:**
```python
    # 单一数据源: 始终回显缓存日期; 调用方日期仅在完全一致时被采纳 (等价于回显)。
    resolved_as_of = as_of if (as_of and as_of == cache_as_of) else cache_as_of
```

**投影核心循环（pool_hub.py:104-126 抽出为 `_project_hub(results, resolved_as_of, updated_at, concept, name_for, data_dir)` 纯函数）:**
```python
    for sid, result in results.items():
        rows = result.get("rows", []) if isinstance(result, dict) else []
        if not isinstance(rows, list):
            rows = []
        total = len(rows)              # ← Δ: 抽函数后改为 result.get("total", len(rows)) (见 Divergence 1)
        projected_rows: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict) or not row.get("symbol"):
                continue
            symbol = str(row["symbol"])
            hit_factors = list(row.get("hit_factors") or [])
            cross_resonance = len(hit_factors) >= 2
            if cross_resonance:
                resonance_symbols.add(symbol)
            projected = {
                "symbol": symbol,
                "code": symbol.split(".", 1)[0],
                "name": str(row.get("name") or ""),
                "open_gap": _safe_num(row.get("open_gap")),
                "change_pct": _safe_num(row.get("change_pct")),
                "concept_board": concept_map.get(symbol.upper(), []),
                "hit_factors": hit_factors,
                "cross_resonance": cross_resonance,
            }
            # 概念筛选: 大小写不敏感子串匹配概念板块; 只收窄 rows (total 不变)
            if needle and not any(needle in c.lower() for c in projected["concept_board"]):
                continue
            projected_rows.append(projected)
        strategies.append({"id": sid, "name": resolver(sid), "total": total, "rows": projected_rows})
    return {"as_of": str(resolved_as_of), "updated_at": updated_at,
            "strategies": strategies, "resonance_count": len(resonance_symbols)}
```

**概念 map（复制 pool_hub.py:46-66 — `_build_concept_map` 实时 join 当前 ext，快照路径共用）:**
```python
def _build_concept_map(data_dir: Path) -> dict[str, list[str]]:
    concept_map: dict[str, set[str]] = {}
    for config in ExtConfigStore(data_dir).load_all():
        field = _dimension_field(config, _CONCEPT_DIMENSION)
        if field is None:
            continue
        rows = _read_ext_rows(data_dir, config, field)
        for row in rows:
            for key in _symbol_keys(row, config):
                concept_map.setdefault(key, set()).update(...)
    return {symbol: sorted(names) for symbol, names in concept_map.items()}
```

**Deltas:**
- 把 L104-126 投影循环抽为 `_project_hub(...)` 纯函数；`build_pool_hub` 改为 `cache = strategy_cache.read_cache(data_dir)` → 空缓存早退 (L87-90 保留) → `return _project_hub(cache.get("results", {}), resolved, cache.get("updated_at"), concept, name_for, data_dir)`。签名与行为零改动。
- 新增 `build_pool_hub_snapshot(data_dir, as_of, concept, name_for)`：`load_point_snapshot` → None 时返回空态 `{"as_of": None, "available": False, "strategies": [], "resonance_count": 0, "updated_at": None}`；否则 `return _project_hub(snap["results"], snap["as_of"], snap["computed_at"], ...)`。
- 返回 dict 追加 `"concept_attribution": "current_snapshot"`（RQ4 诚实标注；**注意** `_project_hub` 被 hub 复用后 `/pool/hub` 响应也会带此键——见 Divergence 2）。
- **导入加 `from app.services import pool_snapshot`（快照服务只读导入，不触发写路径；AST 守卫 E3 同时锁定 pool_snapshot 不得反向 import strategy_cache）**。

---

### 3. `backend/app/api/pool.py` (modified, controller / request-response, GET-only)

**Analog:** 模块内 `get_pool_hub` (20-47) — GET-only 路由 + 服务端 name_for + guest masking。

**GET-only + 服务端显示名 + 游客掩码（复制 pool.py:20-47 形，新端点同构）:**
```python
@router.get("/hub")
def get_pool_hub(request: Request, as_of: Optional[str] = Query(None), concept: Optional[str] = Query(None)):
    repo = request.app.state.repo
    data_dir = repo.store.data_dir
    engine = getattr(request.app.state, "strategy_engine", None)

    def name_for(sid: str) -> str:
        return _strategy_display_name(engine, sid)

    hub = build_pool_hub(data_dir, as_of=as_of, concept=concept, name_for=name_for)

    is_vip = getattr(request.state, "reviewer_principal", None) is not None
    hub["mode"] = "vip" if is_vip else "guest"
    if not is_vip:
        hub = mask_guest_hub(hub)
    return hub
```

**Deltas（新端点，沿用同文件 GET-only 形）:**
- `GET /api/pool/dates` → `{"dates": list_snapshot_dates(data_dir), "count": N, "latest": dates[0] if dates else None}`；GET-only、零写。
- `GET /api/pool/history` → `as_of` 严格 `^\d{4}-\d{2}-\d{2}$` + `date.fromisoformat` 双重校验后再拼路径（防路径穿越，新模式见 No Analog Found）；`concept` 子串沿用 hub 语义；调用 `build_pool_hub_snapshot`；同加 `mode` + `mask_guest_hub`（pool.py:43-46 复制）。
- 两个新路由都必须保持 `@router.get`（AST 守卫 `test_pool_api_is_get_only` 的 `@router.(get|post|put|delete|patch)` 断言天然覆盖，RQ5 E4）。

---

### 4. `backend/app/api/screener.py` (modified, controller / request-response)

**Analog:** 模块内 `run_all` (414-524) — 核心循环是 EOD job 要复用的共享核心。

**run_all 核心循环（api/screener.py:414-524 — 抽为 `ScreenerService.run_all_with_hits(as_of, strategy_ids=None)`）:**
```python
# 日期解析 (L420): as_of = date_type.fromisoformat(str(raw_date)) if isinstance(raw_date, str) else raw_date
# 单次读目标日全量 (L439): precomputed = svc._load_enriched_for_date(as_of)
# 逐策略跑 (L480-505):
    for sid in all_ids:
        try:
            overrides = all_overrides.get(sid, {})
            if sid in PRESET_STRATEGIES:
                r = svc.run_preset(sid, as_of=as_of, precomputed=precomputed, basic_filter=bf, display_limit=dl)
            else:
                r = engine.run(sid, as_of, overrides=overrides or None,
                               precomputed=precomputed, precomputed_history=shared_history)
                if dl is not None and dl > 0:
                    r.rows = r.rows[:dl]          # display_limit 截断 (L490-491)
                    r.total = min(r.total, dl)
            safe_rows = _safe(asdict(r)).get("rows", [])
            results[sid] = {"total": r.total, "as_of": str(as_of), "rows": safe_rows}
        except (ValueError, Exception):
            continue
# hit_factors attach (L513-514): 纯服务端聚合, 不改 total/as_of
    for sid, r in results.items():
        r["rows"] = attach_factor_hits(r.get("rows", []), hits)
# write_cache (L522): 刷新最新指针
    strategy_cache.write_cache(data_dir, str(as_of), results)
```

**Deltas:**
- `run_all` 路由保留 POST 形，核心体改为 `results = svc.run_all_with_hits(as_of, body.get("strategy_ids"))`。
- 在 `write_cache`（L522）**之后**追加 `persist_point_snapshot(data_dir, str(as_of), results, strategy_version=..., computed_at=...)`（手动 run_all 也落快照，POOL-04 调用点 1）。
- `engine` / `PRESET_STRATEGIES` / `build_factor_hits` 依赖注入进 service（`engine` 经 `request.app.state.strategy_engine` 传入；PRESET 与 factor_hits 已在 `app.services.screener` / `app.strategy.factor_hits` import 面）。
- **注意** L215 也有一处 `strategy_cache.write_cache`（另一单策略路由）——EOD job 复用 `run_all_with_hits` 即可，不动该调用点。

---

### 5. `backend/app/services/screener.py` (modified, service / request-response)

**Analog:** 模块内 `_load_enriched_for_date` (217) + `_load_enriched_history` (377-438) + `latest_date` (676-694) — run_all_with_hits 的宿主。

**PIT 语义 loader（复制 services/screener.py:377-438 的 `date <= target_date` 过滤 — EOD job 历史回放诚实性由既有 loader 保证，无需新写）:**
```python
    def _load_enriched_history(self, target_date: date, lookback_days: int) -> pl.DataFrame:
        ...
        lf = (scan_enriched_parquet(str(enriched_dir / "**" / "*.parquet"))
              .filter((pl.col("date") >= start) & (pl.col("date") <= target_date))  # PIT: 只含 <= target_date
              .sort(["symbol", "date"]))
```

**最新交易日（复制 services/screener.py:676-694 — EOD job 的 as_of 来源）:**
```python
    def latest_date(self) -> date | None:
        if self.asset_type != "stock":
            _, d = self.repo.get_enriched_latest_asset(self.asset_type)
            return d
        d = self.repo.enriched_latest_date()
        if d:
            return d
        try:
            res = self.repo.execute_one("SELECT max(date) FROM kline_enriched")
            ...
        except Exception:  # noqa: BLE001
            return None
        return None
```

**Deltas:**
- 新增 `run_all_with_hits(self, as_of, strategy_ids=None) -> dict`，把 api/screener.py:414-524 的核心体搬入（`data_dir = self.repo.store.data_dir`），路由与 EOD job 共用一条代码路径。
- service 需能拿到 `engine`（构造参数或显式传参）——当前 `ScreenerService.__init__(repo, asset_type="stock")` 只有 repo；EOD job 把 `app_state.strategy_engine` 传入。

---

### 6. `backend/app/jobs/daily_pipeline.py` (modified, job/scheduler / batch)

**Analog:** 模块内 `_pipeline_then_refresh` (988-1009) + `_run_tracked` (722-760) + `start_scheduler` add_job 块 (977-1075)。

**单飞包装（复制 daily_pipeline.py:722-760 — EOD job 与手动 run_all 并发写防护，Pitfall 6）:**
```python
def _run_tracked(fn, job_label: str) -> None:
    """调度触发时包装 JobStore 跟踪...
    单飞: 若已有活跃(pending∨running)任务(手动同步中), 本次调度直接跳过, 不并发。"""
    job_id, is_new = job_store.create()
    if not is_new:
        logger.info("scheduled %s 跳过: 已有活跃任务在运行", job_label); return
    if not try_acquire_run_slot():
        logger.warning("scheduled %s 跳过: 重任务执行槽被占用"); job_store.fail(...); return
    try:
        job_store.start(job_id)
        result = fn(on_progress=progress)
        job_store.succeed(job_id, result)
    except Exception:
        logger.exception("scheduled %s failed", job_label); job_store.fail(...)
    finally:
        release_run_slot()
```

**job 注册形（复制 daily_pipeline.py:1011-1017 的 daily_pipeline job — CronTrigger mon-fri + misfire + replace_existing）:**
```python
    scheduler.add_job(
        lambda: _run_tracked(_pipeline_then_refresh, "daily_pipeline"),
        trigger=CronTrigger(day_of_week="mon-fri",
                            hour=sched["hour"], minute=sched["minute"],
                            timezone="Asia/Shanghai"),
        id="daily_pipeline", misfire_grace_time=3600, replace_existing=True,
    )
```

**app_state 延迟取用（复制 daily_pipeline.py:990-996 的 `_get_app_state()` 形 — EOD job 拿 repo/engine）:**
```python
    app_state = _get_app_state()
    capset_live = getattr(app_state, "capabilities", None) or capset
```

**Deltas:**
- 新增 `_pool_eod_persist(on_progress=None)`：`app_state = _get_app_state()` → `repo = app_state.repo` → `svc = ScreenerService(repo)` → `as_of = svc.latest_date()`（None → 返回 `{"as_of": None, "skipped": "no data date"}`）→ `results = svc.run_all_with_hits(as_of)` → `strategy_cache.write_cache(data_dir, str(as_of), results)`（顺带修复实测陈旧 as_of=2026-07-31）→ `pool_snapshot.persist_point_snapshot(data_dir, str(as_of), results, strategy_version=pool_snapshot.strategy_fingerprint(app_state.strategy_engine), computed_at=datetime.now().isoformat(timespec="seconds"))`。
- 在 `start_scheduler` 中（`daily_pipeline` job 之后，L1017 附近）注册 `id="pool_eod_persist"`，时刻 = `preferences.get_pipeline_schedule()`（L974-977）时间 + 固定偏移（如 +5min 常量或新偏好函数）；包裹 `lambda: _run_tracked(_pool_eod_persist, "pool_eod_persist")`。
- **EOD job 不得经 HTTP 自调**——`api/strategy.py:228` 的 `run_all` 也走 POST，只有 service 级 `run_all_with_hits` 可被 job 直调（RQ3）。

---

### 7. `backend/tests/test_pool_snapshot.py` (new, test / transform)

**Analog:** `test_pool_hub.py` `_write_strategy_cache` hermetic fixture (43-112) + `test_factor_hits.py::test_run_all_rows_carry_hit_factors` (152-201) 最小 FastAPI + `_FakeRepo` 装配。

**hermetic fixture 形（复制 test_pool_hub.py:43-112 — 不碰真实数据目录，直接写 payload 到 tmp_path）:**
```python
def _write_snapshot(data_dir: Path, as_of: str = _AS_OF) -> Path:
    """写入 hermetic 点快照 — 只落当次 results, 无 today_ever_rows。"""
    payload = {
        "as_of": as_of, "computed_at": "2026-08-04T15:35:00",
        "strategy_version": "a1b2c3d4e5f60718",
        "snapshot_type": "point", "schema_version": 1,
        "results": {
            "auction_bullish": {"total": 2, "as_of": as_of, "rows": [
                {"symbol": _SYMBOLS["X"], "name": _NAMES["X"], "open_gap": 3.21,
                 "change_pct": 5.1, "hit_factors": ["竞价多头"]},
                # … total=2 但 display_limit 截断示例可加 rows 少于 total …
            ]},
            "auction_early_star": {"total": 0, "as_of": as_of, "rows": []},  # 空策略保留
        },
    }
    out = data_dir / "screener_results" / f"date={as_of}" / "part.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return out
```

**最小 API 装配（复制 test_factor_hits.py:152-201 — TestClient + app.state.repo/strategy_engine）:**
```python
    app = FastAPI()
    app.include_router(screener_api.router)
    app.state.repo = repo
    app.state.strategy_engine = engine
    resp = TestClient(app).post("/api/screener/run_all", json={"as_of": "2026-08-04", "strategy_ids": [...]})
    assert resp.status_code == 200
```

**Deltas（无既有快照 service 测试 — role-match，fixtures 复用）:**
- 新增断言：round-trip（`persist` → `load` 精确往返，**无 `today_ever_rows`** 键）、原子写（无 `.tmp` 残留）、同 as_of 幂等重写、`total=0` 空策略保留（Pitfall 2）、`list_snapshot_dates` 排序 desc、`strategy_fingerprint` 稳定/敏感（meta 变化 → 指纹变）。
- EOD persist 测试：`_pool_eod_persist` 写快照 + 刷新 `strategy_cache.json`（`run_all_with_hits` 可用 `_FakeRepo` + canned 策略，仿 test_factor_hits `_write_canned_strategy` L19-26）。

---

### 8. `backend/tests/test_pool_hub.py` (modified, test / transform)

**Analog:** 模块内 Task 3 AST 守卫 (468-546) — `_EXECUTION_TOKEN`/`_WRITE_PATTERNS`/`_feature_sources`/`_imported_module_names`/4 守卫测试。

**AST 守卫基建（复制 test_pool_hub.py:469-503 — 分拆与扩源的基础）:**
```python
_EXECUTION_TOKEN = re.compile(
    r"broker|order|execution|trade|portfolio|watchlist|position|account|transaction|下单|委托",
    re.IGNORECASE,
)
_WRITE_PATTERNS = (
    re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']w"), re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']wb"),
    re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']a"), re.compile(r"write_parquet"),
    re.compile(r"os\.replace"), re.compile(r"unlink\s*\("), re.compile(r"mkdir\s*\("),
)
_ROUTE_METHODS = ("get", "post", "put", "delete", "patch")

def _feature_sources() -> tuple[str, str]:
    backend = Path(__file__).resolve().parents[1]
    service_src = (backend / "app" / "services" / "pool_hub.py").read_text(encoding="utf-8")
    api_src = (backend / "app" / "api" / "pool.py").read_text(encoding="utf-8")
    return service_src, api_src
```

**Deltas（RQ5 E1-E6，守卫分拆 — 投影无写断言保持严格，快照服务改断言"只写 screener_results"）:**
- **E1** `_feature_sources()` 扩源：追加读 `app/services/pool_snapshot.py`。
- **E2** `test_build_pool_hub_has_no_write_path` (522) 对 `pool_hub.py` 保持严格；新增 `test_pool_snapshot_writes_only_screener_results`：对 `pool_snapshot.py` 每个 `os.replace`/`mkdir`/`open(w)` 断言路径含 `screener_results`（**不能**沿用投影无写断言 — Pitfall 7）。
- **E3** 新增 `test_pool_snapshot_never_writes_runtime_cache`：`pool_snapshot.py` 不得 import `strategy_cache` / 出现 `strategy_cache.json` / `write_cache`。
- **E4** `test_pool_api_is_get_only` (515) 的 `@router.(get|post|...)` 断言天然覆盖 `pool.py` 新路由。
- **E5** 新增 `test_pool_api_no_compute_trigger`：`pool.py` 不得出现 `run_all`/`run_preset`/`write_cache`/`persist_point_snapshot`（API 层只读）。
- **E6** `test_hub_response_has_no_execution_vocabulary` (539) 的 `_all_keys` 遍历扩展到 `/api/pool/history` + `/api/pool/dates` 响应。

---

### 9. `backend/tests/test_guest_masking.py` (modified, test / transform)

**Analog:** 模块内游客白名单测试 (405-427)。

**白名单路径元组（复制 test_guest_masking.py:405-427 的形 — 两个测试的路径元组加新端点）:**
```python
def test_guest_cannot_read_authed_surfaces(tmp_path, monkeypatch):
    """游客面恰好是股池页的两个只读 GET; 其余 /api/ 面一律 401 (T-19-03)。"""
    _write_strategy_cache(tmp_path)
    client = _make_guest_client(tmp_path, monkeypatch)
    for path in ("/api/settings", "/api/portfolio", "/api/watchlist"):
        assert client.get(path).status_code == 401, f"游客应无法读取 {path}"
    assert client.get("/api/pool/hub").status_code == 200
    assert client.get("/api/screener/strategies").status_code == 200

def test_guest_read_paths_are_get_only(tmp_path, monkeypatch):
    _write_strategy_cache(tmp_path)
    client = _make_guest_client(tmp_path, monkeypatch)
    for path in ("/api/pool/hub", "/api/screener/strategies"):
        for method in ("post", "put", "delete", "patch"):
            resp = getattr(client, method)(path)
            assert resp.status_code != 200, f"游客 {method.upper()} {path} 不应成功"
        assert client.get(path).status_code == 200
```

**Deltas（RQ5 E7）:**
- `test_guest_cannot_read_authed_surfaces`：`assert client.get("/api/pool/hub").status_code == 200` 后追加 `assert client.get("/api/pool/dates").status_code == 200` + `assert client.get("/api/pool/history").status_code == 200`（游客日期导航与游客 hub 读一致）。
- `test_guest_read_paths_are_get_only`：路径元组 `("/api/pool/hub", "/api/screener/strategies")` 追加 `"/api/pool/dates"` + `"/api/pool/history"`。
- 新端点返回 `mode` 键（guest 时 `mask_guest_hub` 脱敏）——`test_guest_mode_vocabulary_and_no_identity_leak` (L434-437) 的词汇断言扩展到新端点响应。

---

### 10. `data/screener_results/date={as_of}/part.json` (new data artifact)

**Analog:** `data/kline_daily_enriched/date=*/part.parquet` hive 分区布局（磁盘实测 247 分区至 2026-08-04）+ `strategy_cache.json` payload 形状（`results` 键即当次行集）。

**Layout 模式（镜像 daily_pipeline.py:376-409 消费的 hive 目录 — 分区名 `date={YYYY-MM-DD}`，目录内单文件）:**
```
data/kline_daily_enriched/date=2026-08-04/part.parquet   # 既有 247 分区之一
data/screener_results/date=2026-08-04/part.json          # [NEW] 点快照 (每交易日一目录)
```

**Deltas:**
- 文件格式 **JSON 而非 Parquet**（OQ-2/A1 设计决策）：`results` 是嵌套 dict-of-dicts，JSON 精确往返、保留 `total=0` 空策略；Parquet 宽表化会丢空策略（Pitfall 2）。
- 写侧需 `mkdir(parents=True, exist_ok=True)` 建 `date={as_of}`（`screener_results/` 当前为空占位目录）。

---

## Shared Patterns

### 1. 原子文件写（temp + os.replace）
**Source:** `strategy_cache.py:169-172`
**Apply to:** `pool_snapshot.persist_point_snapshot`、EOD job（经 service）
```python
tmp = path.with_name(path.name + ".tmp")
tmp.write_text(json.dumps(payload, ensure_ascii=False, default=_json_default), encoding="utf-8")
os.replace(tmp, path)
```

### 2. JSON 序列化（date/datetime → isoformat）
**Source:** `strategy_cache.py:26-34`（`_json_default`）
**Apply to:** `pool_snapshot.py` 全部序列化路径
```python
if isinstance(obj, date): return obj.isoformat()
if isinstance(obj, datetime): return obj.isoformat()
raise TypeError(...)
```

### 3. hive 分区日期 glob（日期列表 source of truth）
**Source:** `daily_pipeline.py:376-409`（`enriched_dir.glob("date=*")` + `d.stem.split("=")[1]` + `sorted`）
**Apply to:** `pool_snapshot.list_snapshot_dates` → `GET /api/pool/dates`
```python
sorted((d.name[5:] for d in root.glob("date=*") if (d / "part.json").exists()), reverse=True)
```
> 分区数小（每交易日 1 目录）glob 即 source of truth；DuckDB 冷 SQL 仅 1k-10k 用户缩放路径（RQ2）。

### 4. Hub 投影核心（`_project_hub` 共享纯函数）
**Source:** `pool_hub.py:104-126`（投影循环）+ `:46-66`（`_build_concept_map`）+ `:93`（单一数据源回显，仅 hub 用）
**Apply to:** `build_pool_hub`（运行时缓存）与 `build_pool_hub_snapshot`（点快照）双路径 — total/rows/共振/概念筛选语义 bit-identical（D-02/D-03/D-04 不破）。

### 5. run_all 共享核心（`ScreenerService.run_all_with_hits`）
**Source:** `api/screener.py:414-524`（核心循环 + `_safe(asdict(r))` + `build_factor_hits`/`attach_factor_hits` L513-514）
**Apply to:** `api/screener.py` run_all 路由 + `daily_pipeline.py` EOD job（一条代码路径，PIT loader 既有 services/screener.py:377-438）
```python
results[sid] = {"total": r.total, "as_of": str(as_of), "rows": safe_rows}   # L503
for sid, r in results.items(): r["rows"] = attach_factor_hits(r.get("rows", []), hits)   # L513-514
```

### 6. EOD job 单飞（`_run_tracked` 重任务执行槽）
**Source:** `daily_pipeline.py:722-760`（job_store create / try_acquire_run_slot / start / succeed / fail / release）+ `:1011-1017`（add_job CronTrigger 形）
**Apply to:** `pool_eod_persist` job 注册 — 防与手动 run_all 并发写（Pitfall 6）
```python
scheduler.add_job(lambda: _run_tracked(_pool_eod_persist, "pool_eod_persist"),
                  trigger=CronTrigger(day_of_week="mon-fri", hour=..., minute=..., timezone="Asia/Shanghai"),
                  id="pool_eod_persist", misfire_grace_time=3600, replace_existing=True)
```

### 7. API GET-only + 服务端 name_for + 游客掩码
**Source:** `api/pool.py:20-47`
**Apply to:** `GET /api/pool/dates` + `GET /api/pool/history`（POOL-03：仅 GET、零执行权）
```python
is_vip = getattr(request.state, "reviewer_principal", None) is not None
hub["mode"] = "vip" if is_vip else "guest"
if not is_vip: hub = mask_guest_hub(hub)
```

### 8. strategy 版本指纹（`strategy_fingerprint`）
**Source（输入面）:** `engine.py:263`（`StrategyDef.file_path`）+ `engine.py:285-291`（`list_strategies()` 返回 `{**meta, "source"}`）
**Apply to:** `pool_snapshot.strategy_fingerprint(engine)` — 指纹函数本身无既有实现（见 No Analog Found），输入已齐
```python
def strategy_fingerprint(engine) -> str:
    meta_blob = json.dumps(sorted(engine.list_strategies(), key=lambda m: m["id"]), sort_keys=True, default=str)
    file_blob = b""
    for s in engine._strategies.values():
        p = Path(s.file_path)
        if p.exists():
            file_blob += hashlib.sha256(p.read_bytes()).digest()
    return hashlib.sha256(meta_blob.encode() + file_blob).hexdigest()[:16]
```

### 9. POOL-03 AST 守卫（分拆后）
**Source:** `test_pool_hub.py:469-503`（`_EXECUTION_TOKEN`/`_WRITE_PATTERNS`/`_feature_sources`/`_imported_module_names`）
**Apply to:** 投影文件（pool_hub.py/pool.py）无写断言保持严格；快照服务（pool_snapshot.py）断言"只写 `screener_results` 且不碰运行时缓存"（RQ5 E1-E6）

### 10. 游客白名单
**Source:** `test_guest_masking.py:405-427`
**Apply to:** 新端点 `/api/pool/dates` + `/api/pool/history` 加入两个路径元组（RQ5 E7）

---

## No Analog Found (Gaps)

| File / Feature | Role | Data Flow | Reason / Fallback |
|----------------|------|-----------|-------------------|
| `strategy_fingerprint`（sha256 指纹） | service 子功能 | transform | 仓库无任何"策略集版本指纹"实现；`engine.py:263`（file_path）与 `285-291`（list_strategies meta）只提供输入。**Fallback:** 22-RESEARCH.md RQ1 设计骨架（sha256(list_strategies meta + 源文件内容)，16 hex） |
| `as_of` 严格校验 `^\d{4}-\d{2}-\d{2}$` | API 子功能 | request-response | 无 API 层正则校验先例；最近似是 `api/screener.py:420` 的 `date.fromisoformat`（无格式白名单、可被容错解析）。**Fallback:** 22-RESEARCH.md RQ2（正则 + `date.fromisoformat` 双重校验防路径穿越，Pitfall 4） |
| 快照缺失空态 `{"as_of": None, "available": False, ...}` | API/service 子功能 | request-response | 无"快照缺失 → 200 空态标记"先例；`build_pool_hub` 空缓存早退 (pool_hub.py:87-90) 是最接近形状但无 `available` 键。**Fallback:** 22-RESEARCH.md RQ2 + FRONT-01 空态规约 |
| `build_pool_hub_snapshot` | service | request-response | 新函数；投影核心 analog 存在（pool_hub.py:104-126），但"从快照读 + 空态分支"无既有实现。**Fallback:** 22-RESEARCH.md RQ2 Code Example（`snap is None → available:False`） |

> 其余 6 个文件 + 1 数据 artifact 均有 exact/role-match analog；上述 4 项是**服务/API 级子功能**缺口，非整文件无类比 — planner 需以 22-RESEARCH.md（RQ1/RQ2 Code Examples + Pitfalls + Security Domain）作为兜底实现依据。

## Divergences (Phase 22 特有差异, planner 须注意)

1. **`total` 权威 vs `len(rows)`（投影抽取时必改）:** 现 `pool_hub.py:108` 用 `total = len(rows)`；但 run_all 持久化 `results[sid] = {"total": r.total, ...}`（api/screener.py:503）且 display_limit 截断（L490-491）使 `len(rows) < total`。`_project_hub` 必须改 `total = result.get("total", len(rows))`（22-RESEARCH RQ1 Pitfall 2：快照不存 total 则截断后 total 漂移）。**这是对当前 hub 行为的有意修正**——确认 17 个回归测试不锁死"total == len(rows)"（fixture L43-112 的 total 与 rows 数一致，无截断例，安全）。
2. **`concept_attribution: "current_snapshot"` 键:** `_project_hub` 返回该键（RQ4 诚实标注）后，`GET /api/pool/hub` 响应也会带它。`test_get_pool_hub_missing_cache_empty`（L442-447）只对**空缓存早退路径**做精确 dict 相等（不经过 `_project_hub`），populated hub 各测试均按 key 断言——追加键安全，但执行时先跑 test_pool_hub.py 全量确认。
3. **快照服务是写入者，不能沿用投影无写断言:** `_WRITE_PATTERNS` 会匹配 `pool_snapshot.py` 的 `os.replace`/`mkdir`——AST 守卫必须**分拆**（RQ5 E2：投影严格、快照只写 `screener_results`），绝不放宽 `pool_hub.py` 的断言（Pitfall 7）。
4. **EOD job 不得经 HTTP 自调:** `api/screener.py` 与 `api/strategy.py:228` 的 run_all 都是 POST 路由；EOD job 只能直调 `ScreenerService.run_all_with_hits`（RQ3）。`ScreenerService.__init__` 目前只有 repo——`engine` 需经构造参数或显式传入（fingerprint 与策略执行都需要）。
5. **`_write_cache_locked` 的 union 分支绝不复制进快照:** `strategy_cache.py:118-151`（`combined = {**old_map, **cur_map}` L146）是当日多次运行并集——快照必须只落当次 `results`，测试断言快照文件无 `today_ever_rows`/`today_ever_matched`（POOL-04 铁律，Pitfall 1）。

## Metadata

**Analog search scope:** `backend/app/services/`（strategy_cache.py, pool_hub.py, screener.py）、`backend/app/api/`（pool.py, screener.py）、`backend/app/strategy/engine.py`、`backend/app/jobs/daily_pipeline.py`、`backend/tests/`（test_pool_hub.py, test_guest_masking.py, test_factor_hits.py）、`data/`（kline_daily_enriched hive 布局, screener_results 空占位）
**Files scanned:** 13（strategy_cache.py, pool_hub.py, api/pool.py, api/screener.py, services/screener.py, engine.py, daily_pipeline.py, test_pool_hub.py, test_guest_masking.py, test_factor_hits.py, main.py 接线 L513-514 经 research 确认, 22-RESEARCH.md, 21-PATTERNS.md 风格参照）
**Pattern extraction date:** 2026-08-05
**Line numbers verified against live code:** 全部 excerpt 行号在本 session 逐行读取确认（strategy_cache 原子写 L169-172、pool_hub 投影 L104-126、api/screener run_all L414-524、daily_pipeline glob L376-409/L580、_run_tracked L722-760、start_scheduler L957-1075、test_pool_hub 守卫 L468-546、test_guest_masking 白名单 L405-427）。
