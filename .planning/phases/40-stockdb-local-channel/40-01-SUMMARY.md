# 40-01-SUMMARY.md — 契约先行 (Wave 1)

**Phase:** 40-stockdb-local-channel · **Wave:** 01 (契约先行) · **Date:** 2026-08-07
**Executor:** ExecP4001 · **Status:** DONE — 3 commits (T1 RED → T2 GREEN → T3 补齐), 17/17 契约测试全绿

## 交付物

| Artifact | Path | 说明 |
|---|---|---|
| 夹具 ×4 | `backend/tests/fixtures/stockdb/{daily_sh600519_20260805,minute_sh600519_20260805,error_401,error_429}.json` | 冻结 live 实测响应体 (零网络, CI hermetic) |
| 契约测试 | `backend/tests/test_stockdb_provider.py` | 三差异 + 错误 + 批语义 + 限频 + 分钟端日语义, 17 tests |
| 适配器本体 | `backend/app/data_providers/stockdb_provider.py` | StockDBProvider + typed 异常 + 单点归一化 |

## Commit 链 (RED → GREEN 可回溯)

| Commit | Sha | 内容 |
|---|---|---|
| T1 (RED) | `4e16499` | 冻结夹具 + 三差异/错误契约测试 — 收集期红: `ModuleNotFoundError: No module named 'app.data_providers.stockdb_provider'` |
| harness 修复 | `df24481` | fake transport 路由键改按 `urlparse(url).path` (与 `_get_json` 真实调用面一致) |
| T2 (GREEN) | `ff15572` | local_stockdb 适配器本体 (三差异归一化 + typed 错误) — 契约测试 9/9 绿 |
| T3 | `bcba35d` | 批语义 + 限频对齐 + 分钟端日语义契约 — 全文件 17/17 绿 |

## Verify 命令输出摘录

**T1 (RED, 验收第一步行):**
```
collected 0 items / 1 error
E   ModuleNotFoundError: No module named 'app.data_providers.stockdb_provider'
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
```

**T2 (GREEN, 契约测试):**
```
collected 9 items
tests/test_stockdb_provider.py .........    [100%]
9 passed in 0.34s
```

**T3 + 全文件 (最终):**
```
collected 17 items
tests/test_stockdb_provider.py .................    [100%]
17 passed in 0.49s
```

## 契约锁死点 (可执行规范)

- **三差异 (LOCAL-03, 硬验收):** `symbol == "600519.SH"` (非 SH600519); `volume == 42689.0 且 != 4268900.0` (恒等 ×1, 湖实测=手); `str(df["date"][0]) == "2026-08-05"` 且 `dtype == pl.Date` (aware→naive)。请求侧 `600519.SH → symbols=SH600519` 有显式断言。
- **错误契约 (LOCAL-01):** 401→`StockDBAuthError` 且 transport calls==1 (不重试); 429→Retry-After (头优先, body 回退) sleep 后重试 1 次, 仍 429→`StockDBRateLimited` 上抛 (绝不伪装空帧); 400→`StockDBBadRequest`; 200+`[]`→真空空帧不抛。分类只依状态码 (Pitfall 5)。
- **批语义:** 批端点 `{sym: [bars]}` dict 双 symbol 断言; `batch_size=2` + 3 symbols → 2 次调用, 首片 `"SH600519,SH600000"` 末片 `"SZ000001"`。
- **限频对齐:** `sleep_between_batches` 调用记录全为 `(0,120),(1,120)` — 默认 rpm=120 对齐服务端 daily/minute 档位。
- **分钟端日语义 (Pitfall 3):** `get_minute(end=2026-08-05)` → 请求 `end=2026-08-06` (+1day); 日K end 原样 `2026-08-05`; `bar_time` 输出 naive `datetime(2026,8,5,9,30)` (无 tzinfo), freq 输出列=请求字符串。

## 约束复核

- **零新增依赖:** `git diff 68fee7a -- backend/pyproject.toml backend/uv.lock` → 0 行。
- **写路径零改动:** `kline_sync.py / base.py / normalizer.py / repository.py` — `git diff --name-only` 空。
- **禁 catch-all:** 适配器 `_get_json` 仅窄捕获 typed 路径 (401/429/400), 无 `except Exception: return []`。
- **header-only:** X-API-Key 只经 `_get_json` 的 `headers={"X-API-Key": ...}` 注入, 无 URL 传参。
- `frontend/src/pages/Watchlist.tsx` 未触碰 (保持唯一 unstaged 改动)。

## 协作注记

- 向 ExecP4002 (wave 2) / ExecP4003 (wave 3) 广播了模块契约: 类 `StockDBProvider` (name=`local_stockdb`)、构造 `(base_url="", api_key="", timeout=20.0, rpm=120, batch_size=200)`、模块级 `StockDBAuthError/StockDBRateLimited(.retry_after)/StockDBBadRequest`、`_to_prefix/_to_suffix` 纯函数、`get_daily/get_minute/close` 签名; base_url/api_key 经 `getattr(settings, ...)` 回退 (config 字段由 wave 2 落地, 当前缺失不炸)。
