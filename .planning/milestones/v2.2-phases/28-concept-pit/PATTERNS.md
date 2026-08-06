# Phase 28: 概念板块 PIT 历史映射 — Pattern Map

**Mapped:** 2026-08-06
**Files analyzed:** 8 new/modified artifacts (6 backend + 1 frontend + 1 probe script)
**Analogs found:** 7 / 8 (test analog `test_premarket_snapshot.py` does not exist — see No Analog Found)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/app/services/concept_history.py` (new) | service | file-I/O (atomic hive-partition parquet write + read) | `pool_snapshot.py` + `premarket_snapshot.py` + `ext_data.py:write_ext_parquet` | exact (3 analogs, one per concern) |
| `backend/app/services/pool_hub.py` (modify) | service | CRUD read (projection) | current `pool_hub.py:38-56,96-187,225-267` + `market_overview_builder._read_ext_rows:82-117` | exact (self-analog) |
| `backend/app/jobs/daily_pipeline.py` (modify) | job | event-driven (EOD hook) | current `_pool_eod_persist:973-1015` + `premarket_pool_preview` insert pattern | exact (self-analog) |
| `backend/app/api/pool.py` (modify) | route | request-response | current `/history:78-113` (as_of double-check `:99-107`) | exact (self-analog, passthrough only) |
| frontend concept badge (CONCEPT-04) | component | request-response (UI render) | `StockListTable.tsx` ConceptChips `:49-80` / `AuctionColumnStatusBadge` in `PoolHubPage.tsx:328-333` | role-match |
| `backend/tests/test_concept_history.py` (new) | test | file-I/O + AST guard | `test_pool_snapshot.py` + `test_pool_hub.py` fixtures `:57-132` / AST guard `:857-1012` | exact |
| `backend/scripts/probe_concept_drift.py` (new) | utility | batch/transform (OQ-3 probe) | `backend/scripts/probe_phase13.py` | role-match |
| CONCEPT-06 seam (`_dimension_rank` / `_load_concept_map_df`, splittable) | service | transform | `market_overview_builder.py:243-315` / `rps_rotation.py:60-109` | exact (self-analog) |

---

## Pattern Assignments

### `backend/app/services/concept_history.py` (new — service, file-I/O)

**Best analog:** `pool_snapshot.py` (atomic write + strict date + defensive read + list_dates), `premarket_snapshot.py` (independent-root precedent), `ext_data.py` (parquet write + schema cast).

**Module skeleton + docstring 铁律** — copy `premarket_snapshot.py:1-16` shape (independent store precedent). The module docstring must declare the "zero new deps / no strategy_cache / no execution imports" rule so the AST guard (E1/E3) has a textual anchor:

```python
"""概念 PIT 历史归档 — CONCEPT-01..07。

写 data/ext_history/{gn_ths|hy_ths}/date={as_of}/part.parquet + manifest.json
(平台自有根, 与 EOD screener_results / premarket_results 物理分离)。

铁律:
- 原子写: temp + os.replace (镜像 pool_snapshot.persist_point_snapshot)。
- _DATE_RE fullmatch 后才拼路径 (防路径穿越)。
- 同 as_of 幂等重写, 无 .tmp 残留。
- 本模块不 import strategy_cache / 执行族模块 — AST 守卫 E1/E3 形锁定。
"""
```

**Imports** — mirror `pool_snapshot.py:21-28` + `import polars as pl` (parquet I/O):
```python
import json, logging, os, re
from datetime import date, datetime
from pathlib import Path
from typing import Any
import polars as pl
```

**Root / date / version constants** — copy `pool_snapshot.py:32-38` shape, swap root to the platform-owned history root (independent-root precedent from `premarket_snapshot.py:37`):
```python
_HISTORY_ROOT = "ext_history"                       # 平台自有根 (绝不进 ext_data)
_KINDS = ("gn_ths", "hy_ths")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")      # 防路径穿越; 拼路径前 fullmatch
_SCHEMA_VERSION = 1
```

**`_json_default`** — copy verbatim from `pool_snapshot.py:40-46`.

**Path derivation + strict date validation** — copy `pool_snapshot.py:48-49` (path) and `:73-75` (validate before path-building):
```python
def _partition_dir(data_dir: Path, kind: str, as_of: str) -> Path:
    return data_dir / _HISTORY_ROOT / kind / f"date={as_of}"

# 写前必须 (镜像 pool_snapshot.persist_point_snapshot):
if not isinstance(as_of, str) or not _DATE_RE.fullmatch(as_of):
    raise ValueError(f"invalid as_of: {as_of!r}")
date.fromisoformat(as_of)   # 镜像 api/pool.py:105-107 的双重校验
```

**Atomic write (temp + os.replace + non-fatal warning)** — copy `pool_snapshot.py:92-101` verbatim pattern:
```python
try:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(...)            # parquet → tmp.write_bytes; manifest → tmp.write_text(json)
    os.replace(tmp, path)
    logger.info("概念分区已写入: %s/%s (%d 行)", kind, as_of, n_rows)
except Exception as e:  # noqa: BLE001
    logger.warning("写入概念分区失败: %s", e)   # 非致命, 不阻断 EOD
```
**Adapt:** `part.parquet` uses `df.write_parquet(tmp)` then `os.replace` (NOT `write_text` — parquet is binary; RESEARCH §6.1 dry-run proved `hive_partitioning=True` read-back works). `manifest.json` uses the `write_text`/`os.replace` path. Manifest payload mirrors `persist_point_snapshot` payload pattern (dict of provenance keys, `pool_snapshot.py:81-88`): `{as_of, kind, dimension_field, source_url, fetched_at, captured_at, rows, schema_version, sha256}`.

**Schema alignment** — reuse `ext_data.cast_df_to_schema` + `write_ext_parquet` timeseries-branch discipline (`ext_data.py:526-541`): `cfg_dir.mkdir(parents=True, exist_ok=True)` + `df.write_parquet(out_path)`; keep column order stable via `cast_df_to_schema(df, config.fields)` (`ext_data.py:508-515`).

**Defensive read → None** — copy `pool_snapshot.load_point_snapshot:106-124` verbatim shape (invalid as_of → None, missing path → None, parse error → None):
```python
def read_partition(data_dir, kind, as_of) -> dict | None:
    if not isinstance(as_of, str) or not _DATE_RE.fullmatch(as_of):
        return None
    part = data_dir / _HISTORY_ROOT / kind / f"date={as_of}" / "part.parquet"
    if not part.exists():            # 分区存在性判定优先 (RESEARCH §1.6: 避免 Date vs str 比较坑)
        return None
    try:
        df = pl.read_parquet([part]) # 或 hive_partitioning=True 读回
        ...
        return {"rows": df.to_dicts(), "manifest": manifest}
    except Exception as e:  # noqa: BLE001
        logger.warning("读取概念分区失败: %s", e)
        return None
```

**list_dates glob** — copy `pool_snapshot.list_snapshot_dates:126-140` (root missing → `[]`, `date=*` glob, filter on `part.parquet` existence, `reverse=True` for ISO desc).

**`capture_from_upstream` (OQ-3 probe only)** — reuse `ext_presets._flatten_concept_rows` / `_flatten_industry_rows` (`ext_presets.py:117-147`) for the upstream→local schema transform; use **sync** `httpx.Client` (NOT the async `_fetch_json` in `ext_presets.py:170-181` — capture must stay synchronous per RESEARCH §3.3).

---

### `backend/app/services/pool_hub.py` (modify — service, CRUD read)

**Analog:** current self. Preserve zero-write contract (guard `test_build_pool_hub_has_no_write_path` at `test_pool_hub.py:913`).

**`_build_concept_map` upgrade** — current impl at `pool_hub.py:38-56` (reuse `_dimension_field`/`_read_ext_rows`/`_dimension_values`/`_symbol_keys` from `market_overview_builder`). Add `as_of` branch: when `as_of` non-empty, read `concept_history.read_partition(data_dir, "gn_ths", as_of)` and build the map from partition rows using the **same** `_dimension_values` / `_symbol_keys` join logic (`market_overview_builder.py:121-164`). New signature per RESEARCH §3.2:
```python
def _build_concept_map(data_dir, as_of=None) -> tuple[dict, str, str | None, str | None]:
    # → (concept_map, attribution, effective_date, captured_at)
    # 1. as_of 非空 + 分区命中 rows 非空 → as_of_snapshot, effective_date=as_of, captured_at=manifest.captured_at
    # 2. 回退: 现有 for config in ExtConfigStore(data_dir).load_all() 逻辑原样 (pool_hub.py:41-55)
    #    有概念 config 且 rows 非空 → current_snapshot
    #    有概念 config 且 rows 空 → unavailable
    #    无概念 config → current_snapshot (向后兼容默认)
```

**`_project_hub` attribution state machine** — current `pool_hub.py:96-187`. Change `:97` `concept_map = _build_concept_map(data_dir)` to unpack the tuple; keep `:123` `"concept_board": concept_map.get(symbol.upper(), [])`; replace hardcoded `:182` `"concept_attribution": "current_snapshot"` with the returned attribution; **only when `attribution == "as_of_snapshot"`** append `concept_effective_date` / `concept_captured_at` (fallback states keep the exact current key set — regression lock `test_build_pool_hub_snapshot_has_concept_attribution:486`).

**`build_pool_hub_snapshot` passthrough** — current `pool_hub.py:225-267`. Do **not touch** the empty-state dict at `:246` (`concept_attribution: "current_snapshot"` + `snapshot_origin: None` — exact dict asserted by `test_build_pool_hub_snapshot_missing_available_false:469`). Non-empty branch `:252-267`: pass `as_of=snap["as_of"]` into `_project_hub(...)`.

**`build_pool_hub`** — do **not** change (`as_of=None` → realtime stays `current_snapshot`; empty-cache dict at `:210` has no attribution key — asserted by `test_build_pool_hub_empty_cache:377`).

---

### `backend/app/jobs/daily_pipeline.py` (modify — EOD hook)

**Analog:** current `_pool_eod_persist` + the premarket job insertion pattern in the same file.

**Hook insertion** — inside `_pool_eod_persist:973-1015`, after `persist_point_snapshot(...)` (`:1008-1011`) and **still inside** `if results:` (`:1006`), insert a synchronous, non-fatal capture call:
```python
if results:
    strategy_cache.write_cache(data_dir, str(as_of), results)
    pool_snapshot.persist_point_snapshot(...)
    # ── CONCEPT-01: 概念历史归档 (读本地快照零网络, 同步; 失败不阻断) ──
    from app.services import concept_history
    try:
        concept_history.capture(data_dir, str(as_of))   # as_of 是 date 对象, str()=ISO
    except Exception as e:  # noqa: BLE001
        logger.warning("概念历史归档失败（不阻断股池持久化）: %s", e)
```
**Do not** `await` — the function stays sync (RESEARCH §3.3; `_run_tracked` single-flight at `daily_pipeline.py:723` is sync). Job registration stays as-is (`daily_pipeline.py:1131-1140`, mon-fri +5min).

---

### `backend/app/api/pool.py` (modify — passthrough only)

**Analog:** current `get_pool_history:78-113`. The endpoint already calls `build_pool_hub_snapshot(...)` and returns the full hub dict — the new `concept_effective_date` / `concept_captured_at` keys ride through `_project_hub` output unchanged. No new routing logic.

- Keep as_of double-validation `:99-107` (`_AS_OF_RE.fullmatch` + `date.fromisoformat`) — it is the **exact pattern to copy** for `concept_history` internal date validation too.
- Keep the endpoint GET-only (guard `test_pool_api_is_get_only:905` + `test_pool_api_no_compute_trigger:960`).

---

### Frontend concept badge (CONCEPT-04 — component, request-response render)

**OFF-LIMITS:** `frontend/src/pages/Watchlist.tsx` — do not read/claim (user-pending).

**Data type** — `frontend/src/lib/api.ts:764-766` already declares `concept_attribution?: string` in `PoolHubResponse`. Extend with `concept_effective_date?: string | null` / `concept_captured_at?: string | null` alongside it.

**Badge precedent** — copy `AuctionColumnStatusBadge` pattern (`frontend/src/pages/PoolHubPage.tsx:328-333` render site; component lives in `StockListTable.tsx:102-160`). Render conditional badge near `DateNavigator` (`PoolHubPage.tsx:176`) or above `StockListTable`, driven by the server-frozen `data.concept_attribution` (server-derived, zero client inference — same PIT-3 discipline as `auction_columns`).

**Concept cell** — leave `ConceptChips` untouched (`StockListTable.tsx:49-80`, rendered at `:373` `<ConceptChips concepts={row.concept_board} />`); the badge is a **separate** top-level element keyed on `concept_attribution`, not per-row.

Badge copy contract (CONCEPT-04):
- `concept_attribution !== "as_of_snapshot"` → 「概念归属为当前快照，非该日数据」 (or tooltip).
- `concept_attribution === "as_of_snapshot"` → 「概念按当日快照」 + show `concept_effective_date`.

---

### `backend/tests/test_concept_history.py` (new — test)

**Analog:** `test_pool_snapshot.py:1-63` (hermetic conventions) + `test_pool_hub.py` fixtures and AST guard.

**Test conventions to copy** (`test_pool_snapshot.py:1-63`): module docstring stating hermeticity ("不碰真实数据目录"), `_AS_OF` constant, local `_snapshot_path`-style helper, `_default_results`-style fixture builder.

**Ext fixture to reuse/copy:** `_write_concept_fixture` (`test_pool_hub.py:113-132`) — writes a hermetic `ext_data/{id}/config.json` + `part.parquet` with field `所属概念`. New tests also need a **write-side** fixture producing `ext_history/{kind}/date={as_of}/part.parquet` (mirror `_write_snapshot_payload` in `test_pool_snapshot.py:48-63`).

**API-level tests:** reuse `_make_client` pattern from `test_pool_hub.py` (`client.get("/api/pool/history", params={"as_of": _AS_OF})`, e.g. `test_pool_history_rejects_bad_as_of:841-847`).

**New AST guard tests** (CONCEPT-05) — mirror the E-guard family in `test_pool_hub.py:857-1012`:
- Copy `_EXECUTION_TOKEN` (`:858`) and `_WRITE_PATTERNS` (`:868-875`) definitions verbatim.
- Copy `_imported_module_names` helper (`:884-896`).
- New guard: `_HISTORY_ROOT == "ext_history"` + "every write-containing function references `_HISTORY_ROOT`" — direct port of `test_pool_snapshot_writes_only_screener_results` (`:920-947`), which does `re.search(r'_SNAPSHOT_ROOT\s*=\s*"([^"]+)"', src)` + `ast.walk` over write funcs (`write_funcs = {"replace", "mkdir"}`).

---

### `backend/scripts/probe_concept_drift.py` (new — OQ-3 probe script)

**Analog:** `backend/scripts/probe_phase13.py`. Copy the script skeleton: module docstring (purpose + manual-only note), `from __future__ import annotations`, `import sys` + `sys.path.insert(0, str(Path(__file__).resolve().parent))`, `def main() -> int` returning 0/1, print-based report, `if __name__ == "__main__": raise SystemExit(main())` (`probe_phase13.py:1-10,129-135`).

**Adapt:** iterate trading days, call `concept_history.capture(data_dir, d)` or `capture_from_upstream`, compute `partition_sha256`, append to `data/ext_history/_probe/drift.jsonl`. Zero side effects on ext current snapshot / strategy_cache / screener_results (RESEARCH §6.2).

---

### CONCEPT-06 shared seam (splittable — `_dimension_rank` / `_load_concept_map_df`)

**`market_overview_builder._dimension_rank`** — current `market_overview_builder.py:243-315`. Add `as_of=None` param; when non-empty, map `kind=="concept"→"gn_ths"`, `kind=="industry"→"hy_ths"` and swap the ext-read loop to `concept_history.read_partition(...)` instead of `_read_ext_rows`; aggregation logic unchanged. Wire at call sites `build_market_overview` `:503-504` (pass `as_of` only when `explicit_as_of` `:372` is true).

**`rps_rotation._load_concept_map_df`** — current `rps_rotation.py:60-109` with 600s module-level cache (`_concept_map_cache`/`_concept_map_count`/`_concept_map_ts`). Add `as_of=None`; when non-empty **bypass or key the cache by as_of** (else a historical query can receive the latest-day map — RESEARCH §7 risk). Reuse the same `(_sym_up, concept)` pairs expansion + `pl.DataFrame(...).unique()` shape (`rps_rotation.py:73-105`). `build_rps_rotation` `:111-200` passes `as_of` through; join logic `:150-165` unchanged.

---

## Shared Patterns

### Atomic hive-partition write (temp + os.replace, non-fatal)
**Source:** `pool_snapshot.py:78-101` (mkdir `:78`, payload `:81-88`, temp+replace `:92-98`, except-warning `:99-101`); parquet flavor from `ext_data.write_ext_parquet` timeseries branch `:526-541`.
**Apply to:** `concept_history._write_partition` (part.parquet + manifest.json), both idempotent for same as_of, no `.tmp` residue.

### Strict `_DATE_RE` + `date.fromisoformat` double-check (path-traversal guard)
**Source:** `pool_snapshot.py:37,73-75`; `api/pool.py:99-107`.
**Apply to:** every `concept_history` path-building function (`capture`, `_write_partition`, `read_partition`, `list_partition_dates`).

### Defensive read → None (200-empty, never raise)
**Source:** `pool_snapshot.load_point_snapshot:106-124`.
**Apply to:** `concept_history.read_partition` (missing/invalid/corrupt → None).

### Platform-owned root isolation
**Source:** `_SNAPSHOT_ROOT="screener_results"` (`pool_snapshot.py:33`), `_PREMARKET_ROOT="premarket_results"` (`premarket_snapshot.py:37`).
**Apply to:** `_HISTORY_ROOT="ext_history"` — never inside `ext_data` (avoids double-counting user-configurable list).

### Read-seam reuse (join-key + dimension extraction)
**Source:** `market_overview_builder._dimension_field:121-134`, `_dimension_values:136-142`, `_symbol_keys:144-164`; already imported by `pool_hub.py:20-24`.
**Apply to:** both `_build_concept_map` (partition branch) and `_dimension_rank` as_of branch — do not reimplement field/symbol extraction.

### Zero-execution / zero-write discipline
**Source:** `test_pool_hub.py:857-1012` (`_EXECUTION_TOKEN:858`, `_WRITE_PATTERNS:868-875`, E1 `:895`, E2 `:920`, E3 `:949`, E4 `:905`, E5 `:960`, E6 `:999`).
**Apply to:** `concept_history.py` (only write root = `ext_history`), `pool_hub.py` (remains zero-write), `api/pool.py` (remains GET-only).

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `backend/tests/test_concept_history.py` (w.r.t. `test_premarket_snapshot.py`) | test | file-I/O | `test_premarket_snapshot.py` **does not exist** in `backend/tests/`. Use `test_pool_snapshot.py` (hermetic write/read conventions) + `test_pool_hub.py` (fixtures + AST guard) instead — both verified present. |
| `concept_history.capture` upstream path | service | event-driven | No existing service reads the THS upstream at EOD; `capture_from_upstream` adapts `ext_presets._flatten_*` + sync `httpx.Client` (async `_fetch_json` must NOT be reused — capture is sync). |

## Pattern Gaps (planner attention)

1. **`test_premarket_snapshot.py` is a phantom** — CONTEXT listed it as a convention source; the real repo has only `test_pool_snapshot.py` + `test_pool_hub.py`. Use those.
2. **Parquet hive-partition read-back** appends a polars `Date`-typed `date` column (`RESEARCH §1.6` dry-run). Read side MUST judge by partition existence (glob `date={as_of}/part.parquet`), never compare against the `date` column as a string.
3. **`capture` must stay synchronous** (EOD key path, zero network). `capture_from_upstream` is the only network path and is probe-only.
4. **CONCEPT-06 seam** delivers `read_partition` + signature extensions (as_of optional, default None behavior unchanged); overview/RPS wiring may be split to a later sub-task.

## Metadata

**Analog search scope:** `backend/app/services/*`, `backend/app/jobs/*`, `backend/app/api/*`, `backend/tests/*`, `backend/scripts/*`, `frontend/src/pages/*`, `frontend/src/components/pool-hub/*`, `frontend/src/lib/*`
**Files scanned:** 16 (pool_snapshot, premarket_snapshot, pool_hub, market_overview_builder, ext_data, ext_presets, rps_rotation, api/pool, daily_pipeline, test_pool_hub, test_pool_snapshot, probe_phase13, StockListTable, PoolHubPage, api.ts)
**Pattern extraction date:** 2026-08-06
**Off-limits:** `frontend/src/pages/Watchlist.tsx` (user-pending — not read, not claimed)
