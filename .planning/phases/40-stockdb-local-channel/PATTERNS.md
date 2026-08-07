# Phase 40: stockdb 本地通道接入 — Pattern Map

**Mapped:** 2026-08-07 · **Files:** 5 新增 / 5 修改 · **Analogs:** 9/10 (无 auction — 设计差异非缺口)

## File Classification

| File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `backend/app/data_providers/stockdb_provider.py` (新) | provider | request-response + transform | `free_stockdb_provider.py:44-180` (class+capabilities), `:300-330` (get_minute 形状) | exact |
| `backend/app/config.py` (改) | config | — | `config.py:80-83` (`free_stockdb_url` Field) | exact |
| `backend/app/data_providers/chain.py` (改) | registry | — | `chain.py:20-26` (`_BUILTIN_CHAIN`), `:31-38` (lazy singleton), `:62-88` (`_get_provider`), `:147-179` (`health_check`) | exact |
| `backend/app/services/preferences.py` (改) | config | — | `preferences.py:159` (`_ALLOWED_DATA_PROVIDERS`) | exact |
| `backend/app/api/settings.py` (改) | controller | request-response | `settings.py:435-441` (free_stockdb builtin 条目) | exact |
| `backend/tests/test_stockdb_provider.py` (新) | test | — | `test_ifzq_provider.py:16-41` (`_FakeResponse`/`_JsonTransport`) + `test_stocksdk_provider.py:31-46` (monkeypatch 注入) + `test_xyz_provider.py:18-25` (canned payload) | exact |
| `backend/tests/fixtures/stockdb/*.json` (新) | fixture | — | 无静态夹具目录先例 (见下); 参考 `test_ifzq_provider.py:43-57` 内联 canned dict | new |
| `backend/tests/test_provider_chain.py` (改) | test | — | `test_provider_chain.py:24-56` (`_FakeProvider` + monkeypatch `chain._get_provider`) | exact |
| `.env.example` (改) | config | — | `.env:3` (`TICKFLOW_API_KEY=` 注释占位风格) | exact |
| `kline_sync.py` / `base.py` / `normalizer.py` / `repository.py` / `rate_limits.py` / `auction_probe.py` | — | — | **复用不动**: `kline_sync.py:93-135` `_normalize_daily`、`:254` `repo.append_daily(merged)`、`repository.py:1700-1720` merge-upsert+原子 rename | — |

## Pattern Assignments

### `stockdb_provider.py` (provider) — 镜像 `free_stockdb_provider.py`

- **类头/能力声明** (镜像 `free_stockdb_provider.py:64-72`): `name = "local_stockdb"`; `ProviderCapabilities(instruments=False, daily=True, adj_factor=False, minute=True, realtime=False, financial=False, auction=False)` — 诚实声明无竞价 → `auction_probe.py:110` 按 `capabilities.auction` 枚举自然排除 (镜像 xyz `auction=True` 反例 `xyz_provider.py:52-59`)。
- **`__init__`** (镜像 `free_stockdb_provider.py:74-89`): `httpx.Client(timeout=timeout)` + `base_url.rstrip("/")`; base_url/api_key 缺省回退 `settings.local_stockdb_url` / `_api_key` (镜像 `chain.py:35` 单例传 `base_url=settings.free_stockdb_url` 的注入面)。
- **请求骨架**: 批端点 `GET /v1/daily?symbols=` + **`headers={"X-API-Key": ...}` header-only (禁 URL 传参)**; `chunked(symbols, 200)` + `sleep_between_batches(i, rpm=120)` (镜像 `rate_limits.py:42-47,59-75` 进程级共享槽)。
- **错误契约 — 严禁复制 catch-all**: free_stockdb `_vals`/`_keys` 的 `except Exception: return []` 空帧吞错是 P2 反模式; local 按状态码窄捕获: 401→`StockDBAuthError`(不重试), 429→`StockDBRateLimited`(Retry-After 重试 1 次后上抛), 400→`StockDBBadRequest`; 仅 200+`[]` 返回空帧 (RESEARCH Pattern 3)。
- **get_daily 归一化** (镜像 `free_stockdb_provider.py:300-330` 逐 symbol 建帧 + `normalizer.py:29-58 normalize_daily` 复用): symbol 前缀→后缀 (`SH600519`→`600519.SH`)、`volume_hand` 恒等 ×1 cast Float64 alias volume、aware date→`pl.Date` naive、丢弃 provenance 列; **not** 镜像 `ifzq_provider.py:166,231` 的 `×100 手→股`。
- **get_minute**: 端日语义 `[start, end+1day]` (RESEARCH Pitfall 3); `bar_time` aware→`replace(tzinfo=None)` 北京墙钟 (契约 `test_minute_timestamp_convention.py:1-58`); freq int pass-through (镜像 `free_stockdb_provider.py:40-41 _MINUTE_UNIT_MINUTES` 反方向)。

### 注册面 — 4 处必须同改 (RESEARCH Pattern 4 全链路)

1. `chain.py:20-26`: `"daily": ["local_stockdb", ...]`、`"minute": ["local_stockdb", ...]` 链首插槽。
2. `chain.py:62-88`: `_get_provider` 加 `if name == "local_stockdb": return local_stockdb_provider()` 分支; 单例镜像 `chain.py:31-38` (`_provider_cache.get` + 懒建)。
3. `chain.py:147-179`: `health_check` 并入 `{"free_stockdb", "xyz"}` 同款 probe 分支 (`get_daily(["000001"])` 非空判断, 镜像 :153-158)。
4. **`preferences.py:159` `_ALLOWED_DATA_PROVIDERS` += `"local_stockdb"`** — 缺失则 `_sanitize_chain` (:185-198) 过滤回 tickflow, 即 :155-158 注释文档化的静默假象陷阱。

### `config.py` + `settings.py` + `.env.example`

- `config.py:80-83` 后追加 `local_stockdb_url: str = Field(default="http://127.0.0.1:8000", ...)` + `local_stockdb_api_key: str = Field(default="", ...)` (env_file 已接线 :71, `extra="ignore"` :73 → 密钥不落 git)。
- `settings.py:435-441` 同款 builtin 条目: `{"name": "local_stockdb", "datasets": ["daily", "minute"], "health": provider_chain.health_check("local_stockdb"), "base_url": settings.local_stockdb_url}` — 与白名单一致性是前端切换的前提。
- `.env.example` 注释占位: `LOCAL_STOCKDB_URL=` / `LOCAL_STOCKDB_API_KEY=` (镜像 `.env:3` UPPER_SNAKE 风格; 真实 key 只进 `.env`, 与 `TICKFLOW_API_KEY` 同纪律)。

## 命名与测试惯例

- **Provider 名**: 模块 `stockdb_provider.py`、类 `StockDBProvider`、`name = "local_stockdb"` (LOCAL-01 定稿; 惯例: 模块=`<name>_provider.py`, 类=`<Name>Provider` — 参照 xyz/ifzq/tencent)。
- **测试文件**: `test_<name>_provider.py` → `test_stockdb_provider.py` (现有 test_xyz/test_ifzq/test_tencent/test_stocksdk 全符此式; **无 test_free_stockdb\*** — free_stockdb 覆盖在 test_provider_chain.py)。
- **夹具**: 仓库现无静态 fixtures 目录 — provider 测试用内联 canned dict (`test_ifzq_provider.py:43-57 _QFQ_DAILY`, `test_xyz_provider.py:18-25 _canned_payload`) 或 tmp_path 写 (`test_production_host.py:91-107`)。本 phase 引入 `backend/tests/fixtures/stockdb/*.json` 冻结 live 实测体 (daily 4024 行太大不宜内联; 研究 Code Examples 已给文件清单), 加载 helper `_load_fixture` 镜像 `_canned_payload` 调用面。
- **注入方式三选一** (与既有测试同构): ifzq `_JsonTransport`+`_FakeResponse` (`test_ifzq_provider.py:16-41`) — StockDBProvider 需 status_code/headers, 扩展该 fake; xyz `provider._call_tool = fake` (`test_xyz_provider.py:27-36`); stocksdk monkeypatch 模块函数 (`test_stocksdk_provider.py:31-34`)。推荐 httpx 兼容 fake (status_code+headers+json) 以覆盖 401/429 头断言。

## 守护模式

- **POOL-03 AST 守卫 — 适用, 但形改为「provider 只读 HTTP 客户端」**: 既有模板 `test_pool_hub.py:951-972` / `test_auction_history.py:301-320` (E1 无执行族 import + E4 仅 GET 路由 + `_WRITE_PATTERNS` 无写路径)。对 data_providers 面: `test_stockdb_provider_is_read_only_http_client` — 断言 `stockdb_provider.py` import 无执行族 token (broker/order/execution/trade/portfolio), 无写模式 `open(`/`write_parquet`/`os.replace`/`unlink`/`mkdir`, 且 HTTP 动词仅 `client.get(` (无 post/put/delete), **api_key 只出现在 headers dict** (禁 URL 传参 → LOCAL-01 硬验收)。
- **限频对齐测试 (hermetic)**: 不碰真服务 — monkeypatch `sleep_between_batches` 记录 rpm 参数断言 `== 120` (对齐服务端档位 RESEARCH 限频表); 429 用例 fake 返回 `status_code=429` + `Retry-After` 头, 断言遵守重试 1 次后上抛 `StockDBRateLimited` (绝不伪装空帧)。
- **契约测试 hermetic**: 夹具 = 冻结 live 实测体 JSON, 零网络 (RESEARCH §Code Examples 骨架: `_provider(routes)` 注入); 三差异硬验收断言 symbol 精确 `"600519.SH"`、`volume == 42689.0 and != 4268900.0`、`date.dtype == pl.Date` + naive 值 (REQUIREMENTS.md LOCAL-03 已定稿恒等 ×1, Q1 已闭环 — 不再需要 discuss)。

## 关键差异点

| 维度 | local_stockdb | free_stockdb | xyz | ifzq |
|---|---|---|---|---|
| 鉴权 | X-API-Key header-only | 无 | MCP 内部 | 无 |
| 协议 | REST `/v1/daily\|minute`, 批端点 {sym:[bars]} ≤200 | KV `cmd=vals&t=日k` | MCP tool | HTTP JSONP |
| symbol | `SH600519` 前缀 → 需转后缀 | 6 位 code | 带后缀已规范 | 带后缀 |
| volume | `volume_hand` 手 → **恒等 ×1** | 手直通 | 已规范 | **×100 手→股 (若镜像则错)** |
| 时区 | aware +08:00 → 剥 naive | int yyyymmdd | naive | naive |
| 错误 | typed 窄捕获 (401/429/400) | catch-all 空帧 (**不复制**) | 403/配额窗 markers | — |
| auction | **False** → 不进竞价链 | False | **True** (`xyz_provider.py:59`) | — |

## PLAN 任务分解骨架

- **Wave 0 (契约先行, 定合同)**: `tests/fixtures/stockdb/*.json` (daily_sh600519_20260805 / minute_sh600519_20260805 / error_401 / error_429 冻结体) + `test_stockdb_provider.py` 三差异/错误/批语义/限频/只读守卫 — 红转绿的验收基准。
- **Wave 1 (实现, 依赖 Wave 0 契约)**: `stockdb_provider.py` (能力声明 → httpx+header → `_get_json` typed 异常 → get_daily 归一化 → get_minute end+1day → close)。
- **Wave 2 (注册, 依赖 Wave 1)**: `config.py` 两字段 → `chain.py` (链首 + 分支 + 单例 + health) → `preferences.py` 白名单 → `api/settings.py` 条目 → `.env.example`。**同波提交, 防白名单漏注册的半完成态**。
- **Wave 3 (链集成测试)**: `test_provider_chain.py` 扩展 (`_ALLOWED_DATA_PROVIDERS` 含 local_stockdb、`chain_for("daily")[0] == "local_stockdb"`、fake local provider gap-merge 用例, 镜像 :24-56) + `test_config.py` env 覆盖。
- **Wave 4 (冒烟)**: 走既有 `kline_sync` 路径 (`fetch_with_chain("daily")` 链首命中; **kline_sync.py 零改动**); 全量 `cd backend && .venv/bin/python -m pytest tests/ -x`。
- **关键依赖边**: 契约测试(0) → 实现(1) → 注册(2) → 链测试(3) → 冒烟(4); 无跨 wave 反向依赖。**非目标**: 不动 flush_live_daily 语义 (`repository.py:1787-1791` 双路径共存仅记录)、不动 base.py/normalizer/kline_sync。

## No Analog Found

| File | Reason |
|---|---|
| `tests/fixtures/stockdb/*.json` | 仓库首个静态 JSON 夹具目录 (既有为内联 dict / tmp_path); 计划沿用研究 Code Examples 文件清单与字段冻结惯例 |
| `stockdb_provider.py` 的 typed 错误分类 | 既有 provider 无 typed HTTP 错误类先例 (free_stockdb catch-all 为反模式); 类命名镜像 `auction_probe.py` 错误常量纪律 (截断消息, 不泄 body) |

## Metadata

**Scope:** `backend/app/data_providers/*`, `backend/app/services/{preferences,kline_sync,auction_probe}.py`, `backend/app/api/settings.py`, `backend/app/tickflow/{rate_limits,repository}.py`, `backend/tests/*`, `.env*` · **Patterns source:** RESEARCH.md 全 497 行 + 上述源码直读 (file:line 均已核实) · **Valid until:** 2026-09-06
