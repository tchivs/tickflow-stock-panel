# Technology Stack: v2.5 接入本机 stockdb SDK + 诚实性修复

**Project:** AthenaQuant v2.5 (honesty + local source channel)
**Researched:** 2026-08-07
**Confidence:** HIGH (关键结论均本地实测/源码核实; 唯一推断项已标注)

---

## 核心结论 (TL;DR)

1. **stockdb SDK 不是独立包**: `src/stockdb/sdk/` 属 `stockdb` 发行版, `stockdb/__init__.py:3`
   顶层 re-export, SDK 直接 `from stockdb.contracts.schemas import ...` (client.py:16-25)。
   **必须让整个 `stockdb` 包可 import**, 不能只拷 sdk/。
2. **Python 版本是唯一硬阻断**: `sdk/stream.py:30` 用 PEP 695 `type` 别名 (3.12+),
   `sdk/__init__.py:3` 无条件 import stream → **`import stockdb` 在 3.11 直接 SyntaxError**。
   AthenaQuant 现状 = 3.11.2 (venv 实测)、Docker python:3.11-slim (Dockerfile:42)、
   scipy pin `<1.18` 保 3.11。**v2.5 (A) 必须伴随 Python 3.12 运行时升级**。
3. **共享依赖零摩擦**: httpx 0.28.1 (要求 >=0.28,<0.29 ✓, uv.lock:952)、pydantic 2.13.4
   (要求 >=2.13,<3 ✓, uv.lock:2488); websockets 15.0.1 (要求 >=17,<18 ✗, langgraph 传递依赖)
   仅影响 WS 流, REST 通道不受影响。
4. **诚实性修复 + 部署日执行 = 零栈变化**。

---

## 1. SDK 依赖面 (实测)

| 依赖 | stockdb pin | AthenaQuant 锁定 | 兼容 |
|---|---|---|---|
| Python | `>=3.12` (.python-version=3.12) | 3.11.2 / 3.11-slim | **✗ 阻断** |
| httpx | `>=0.28,<0.29` | 0.28.1 | ✓ |
| pydantic | `>=2.13,<3` | 2.13.4 | ✓ |
| websockets | `>=17,<18` | 15.0.1 | ⚠ 仅流 |
| 其余 (rocksdict/tdxpy/typer/slowapi/mcp/scrapling…) | — | — | SDK import 路径不触碰 |

SDK 实际 import 面 = httpx + pydantic + websockets (client.py:11, contracts/schemas.py:15)。
重型服务端依赖只被 api/providers/lake/kernel 引用, 不在 SDK 路径上。

**3.11 阻断已实测**: `PYTHONPATH=../stockdb/src uv run python -c "import stockdb"` →
`SyntaxError (stream.py:30, type Channel = Literal[...])`。client/models/errors/__init__ 四文件
3.11 下均可 parse — 只坏在 stream.py 的 PEP 695。

---

## 2. 零新增依赖: 方案评估

| 方案 | 依赖影响 | 结论 |
|---|---|---|
| **A. `uv pip install -e ../stockdb --no-deps` + Python 3.12 升级** | 零新第三方库 | ✅ **推荐**。uv_build 后端支持 PEP 660 editable; `--no-deps` 必须 (否则整树含 tdxpy/rocksdict 原生构建、scrapling 重型浏览器进 env — stockdb 自己注释「核心 API 机不装重型浏览器」) |
| B. pyproject `[tool.uv.sources]` path dep | uv.lock 解析 stockdb **全量**依赖树 | ❌ 违背零新增 + websockets>=17 与 15.0.1 冲突 |
| C. vendored 轻 client (sdk + contracts/{schemas,missing,provenance}) | 零安装, 3.11 可跑 | ⚠ 备选。fork 漂移风险, 违背「接入 SDK」意图 |
| D. 纯 httpx 薄 client (镜像 free_stockdb_provider) | 零, 3.11 可跑 | ⚠ 备选。重复实现 ETag/重试/类型模型 |
| E. PYTHONPATH=/stockdb/src / subprocess | 零 | ❌ 脆弱, 生产容器不可复现 |

**建议**: 采用 A, 前置条件 = Python 3.12 (重建 venv、Dockerfile `python:3.12-slim`、
pyproject requires-python、解除 scipy 上限说明、dev.sh/CI 同步)。拒绝升级 → 只能 C/D,
且里程碑需声明「未接入 SDK 本体」。

**部署日注意**: Docker 构建上下文不含 `../stockdb` — 镜像内需 COPY stockdb 源码 +
`uv pip install -e --no-deps`, 或预构建 wheel 拷入; 首次安装走 build isolation 需网络。

---

## 3. 集成点

- **新 provider 模块** `data_providers/local_stockdb_provider.py`: 实现 `MarketDataProvider`
  protocol (base.py:24-48), 经既有 normalizer 归一化到内部 schema。
- **注册**: `data_providers/chain.py:22-27` `_BUILTIN_CHAIN` (daily/minute 插入) + 单例工厂
  进 `_provider_cache`。**命名必须新名 `local_stockdb`** — `free_stockdb` 已指远端 C++
  服务 (chain.py:11-12, config.py:80-83)。
- **配置**: `app/config.py` 镜像 `free_stockdb_url` 加 `local_stockdb_url`
  (默认 http://127.0.0.1:8000) + 可选 `local_stockdb_api_key` (SDK api_key → `X-API-Key`
  头; 服务端 STOCKDB_API_KEYS 未配则匿名可访问, DATA_CONTRACTS.md:709-713)。
- **能力声明**: `ProviderCapabilities(auction=False, ...)` — openapi 实测 (curl :8000)
  无任何 auction 端点, tushare 白名单也无 auction (DATA_CONTRACTS.md:1042-1046) →
  **不能服务 DATA-04..06 竞价湖**, xyz (stockdb_get_call_auction) 仍是 auction 唯一内置源;
  auction_probe 链 (auction_probe.py:87-110) 不加本通道。
- **不走 custom-source YAML** (那是 GenericHTTPProvider 的 HTTP JSON 形态; SDK 是原生
  Python client, provider 模块是正确形态)。

---

## 4. 诚实性修复 + 部署日: 栈需求 = 零

- **source_blocked**: `xyz_provider.py` (纯 httpx JSON-RPC MCP client, 403/配额窗已实测)
  内补标签逻辑 — 现有栈足够。
- **空帧进度 emit**: `services/auction_backfill.py:245-312` emit 路径 — polars + stdlib。
- **部署日**: `scripts/auction_backfill.py` / `scripts/verify_auction_backfill.py` (零写入,
  DuckDB 视图 + glob, 头注释「零新依赖」) + md5 parity / 容器操作 — 无栈变化。

---

## 5. 明确「不要加什么」

- ❌ 不裸装 stockdb (无 `--no-deps`); 不写进 pyproject dependencies / `[tool.uv.sources]`。
- ❌ 不为 v2.5 升 websockets (REST-only, stream 模块 import 兼容 15.x 只是不实例化)。
- ❌ 方案 A 下不 vendoring (避免双客户端漂移)。
- ❌ 不把 local_stockdb 接进 auction 链 (无 auction 数据)。
- ❌ 诚实性修复不加任何新库。

## Sources

- 源码: stockdb pyproject.toml; sdk/{client,models,errors,stream,\_\_init\_\_}.py;
  contracts/schemas.py; docs/DATA_CONTRACTS.md (709-713, 1042-1046); AthenaQuant backend/
  pyproject.toml, uv.lock (952/2488/3927), Dockerfile:42, config.py:80-83,
  data_providers/{base,chain,registry}.py, services/auction_probe.py:87-110,
  services/auction_backfill.py:245-312, scripts/verify_auction_backfill.py:1-33。
- 运行时探测: curl :8000 openapi.json (33 个 /v1 路径, 无 auction); `import stockdb` 于 3.11
  venv → SyntaxError stream.py:30 (实测)。
- [INFERENCE] 里程碑上下文「AthenaQuant 是 Python 3.12」与实测 3.11.2 冲突 — 需里程碑
  显式确认 3.12 升级为 v2.5 前置。
