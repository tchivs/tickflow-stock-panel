---
phase: 40-stockdb-local-channel
verified: 2026-08-07T15:10:00Z
status: passed
score: 4/4 LOCAL requirements — LOCAL-01/02/03/04 verified (2 sandbox-unassertable items recorded in behavior_unverified)
behavior_unverified: 2 — (1) 容器内 127.0.0.1:8000 连通性: live 冒烟在宿主跑 (本 verifier 已独立复跑通过), 但 app 容器内到 stockdb 容器的 loopback 可达性未在部署拓扑中实测 (Phase 44 DEP 重建配方验证项); (2) 双源真实链长期行为: ETag/304 条件缓存未启用 (研究建议, PLAN 未含), 真实链上长期 gap-merge/429 窗/空帧-vs-403 行为需生产观测
overrides_applied: 0 — 执行区间 68fee7a..HEAD 未改动 REQUIREMENTS.md/ROADMAP.md 文本; LOCAL-03「手→股 ×100→恒等 ×1」修正为规划期提交 602a6f5 完成 (研究 Q1 RESOLVED), 当前需求文本即修正后文本, 契约测试锁死恒等
human_verification: 3 items (真实 stockdb key 轮换/审计归因 — 专用 key 仅为建议未强制; 容器内 127.0.0.1 连通性; 双源真实链长期行为观测) — sandbox 无法断言, 按既有诚实政策标注
---

# Phase 40 Verification — stockdb 本地通道接入 (LOCAL-01..04)

**Verifier:** VerifierP40 · **Date:** 2026-08-07 · **Scope:** `.planning/REQUIREMENTS.md` LOCAL-01..04 (Phase 40), ROADMAP Phase 40 五项 success criteria, 提交集 68fee7a..HEAD (12 commits: wave1 `4e16499/df24481/ff15572/bcba35d`, wave2 `8655a57/1ee1979/f468c7f` + docs `e1c1a41`, wave3 `c83ae2d/1df4b87/75dab53` + docs `5efc2fd`).
**Method:** Behavior-level verification — 逐需求读实现 + 契约测试 + 冻结夹具; 独立重跑 4 个相关测试文件 (53 passed); 守卫核验 (dep diff / kline_sync diff / Watchlist / AST 守卫判据存在); live 冒烟由本 verifier 独立复跑 (真实 stockdb 服务 + 真实 key, 只读 GET); 全量 hermetic 回归按分工由 orchestrator 统一最后跑 (本 verifier 不重复全量)。所有数字为本 verifier 亲自重推导, 不采信 SUMMARY 文本。

## Verdict: **PASSED**

四项需求全部验证通过: LOCAL-01 适配器 (auction=False 诚实声明 + header-only + 限频对齐 + typed 错误 + 零新依赖 + AST 只读守卫), LOCAL-02 注册 (config 两键 + env 注入 + lazy 单例 + 链首插槽 + 白名单 + health + settings builtin), LOCAL-03 归一化契约 (三差异锁死, 42689.0 恒等锚点 live 复跑一致), LOCAL-04 旁路 (daily/minute 链首 gap-merge + 幂等写 + 湖无 provenance 列 + 通道身份进日志, kline_sync.py 零改动)。

---

## 1. 守卫核验 (guard rails)

| 守卫 | 命令 (本 verifier 亲自跑) | 结果 |
|---|---|---|
| 零新增依赖 | `git diff 68fee7a..HEAD -- backend/pyproject.toml backend/uv.lock` | **0 行** — pyproject/uv.lock 零改动 (适配器仅 import httpx/polars, 均既有 deps) |
| kline_sync 零改动 | `git diff --name-only 68fee7a..HEAD -- backend/app/services/kline_sync.py` | **空** — 写路径零触碰 |
| 写路径家族零改动 | `git diff 68fee7a..HEAD --stat -- backend/app` | 仅 5 文件: settings.py +7 / config.py +10 / chain.py +27-5 / stockdb_provider.py +238 (新建) / preferences.py +2-1 — normalizer.py/base.py/repository.py 均不在 |
| Watchlist 零触碰 | `git status --short` + `git diff --name-only 68fee7a..HEAD \| grep -i watchlist` | 提交内 **0**; 工作树唯一未暂存项 `M frontend/src/pages/Watchlist.tsx` (既有用户改动, 本 verifier 未读取) |
| AST 守卫四判据在 | `pytest tests/test_stockdb_provider.py -k read_only` | **1 passed** — `test_stockdb_provider_is_read_only_http_client` 判据 A 无执行族 import / B 无写模式 token / C 仅 client.get / D api_key 仅 headers 行, 全部断言存在 |
| 提交集完整性 | `git log --oneline 68fee7a..HEAD` | 12 commits 与 claim 完全一致 (wave1 4 + wave2 3+1docs + wave3 3+1docs), HEAD=`5efc2fd` |
| .env.example 纪律 | `git diff 68fee7a..HEAD -- .env.example` | +5 行注释占位 (`LOCAL_STOCKDB_URL=`/`LOCAL_STOCKDB_API_KEY=`), 真实 key 只进 .env |

---

## 2. 逐需求证据 (REQ-by-REQ)

### LOCAL-01 — `local_stockdb` HTTP 适配器 — **PASS**

证据 (stockdb_provider.py 全文读 + test_stockdb_provider.py 18 用例):

- **name/capabilities**: `name = "local_stockdb"`; `ProviderCapabilities(instruments=False, daily=True, adj_factor=False, minute=True, realtime=False, financial=False, auction=False)` — auction=False 诚实声明。auction_probe.py:110 枚举候选源仅当 `getattr(provider.capabilities, "auction", False)` → local_stockdb 永不入 auction_probe 链 (success criterion 1 的第二半)。
- **X-API-Key header-only**: 唯一请求面 `_get_json` (行 133-149) 仅 `self._client.get(url, params=params, headers={"X-API-Key": self.api_key})` — 无 URL 传参; AST 守卫判据 D 对每个含 `X-API-Key` 的代码行强制含 `headers` (tokenize 级剔除注释/文档串)。
- **限频对齐**: 构造默认 `rpm=120`, `sleep_between_batches(i, rpm)` 每次批间调用 (daily/minute 各一处在 get_daily/get_minute) — 对齐服务端 daily/minute 120/min 档位; 契约测试 `test_sleep_between_batches_aligns_to_server_rpm` 断言调用记录 `[(0,120),(1,120)]`。quotes 300/min / ticks 60/min 档位为服务端属性, 本 phase 面 (daily/minute) 不触及 (Q3 scope 决策, RESEARCH.md:383), 非缺口。
- **429 带 Retry-After**: `_parse_retry_after` 头优先 → body `retry_after` 回退 → 缺省 1s; 429 按 Retry-After sleep 后重试恰 1 次, 仍 429 → `StockDBRateLimited` 上抛 (绝不伪装空帧)。测试: `test_429_honors_retry_after_then_raises` (sleeps==[50.0], calls==2), `test_429_retries_once_then_returns_frame`, `test_429_retry_after_header_controls_wait`, `test_429_retry_after_falls_back_to_body`。
- **typed 错误, 禁 catch-all**: 401→`StockDBAuthError` (transport calls==1, 不重试), 400→`StockDBBadRequest`, 200+`[]`→真空空帧不抛; 分类仅依状态码 (Pitfall 5)。测试 `test_401_raises_typed_auth_error_not_empty` / `test_400_raises_typed_bad_request` / `test_200_empty_bars_is_legitimate_vacuum`。
- **批语义**: 批响应 `{sym: [bars]}` dict; `batch_size=2` + 3 symbols → 2 次调用, 首片 `"SH600519,SH600000"` 末片 `"SZ000001"` (`test_get_daily_chunks_by_batch_size`); 双 symbol 归一化 (`test_batch_endpoint_parses_sym_bars_dict`)。
- **零新增运行时依赖**: pyproject/uv.lock 0 行 diff; 适配器 import 面 = stdlib (logging/re/time/re/datetime/typing) + httpx + polars (既有 deps)。
- **AST 守卫四判据**: 判据 A (无执行族 import: broker|order|execution|trade|portfolio|watchlist|position|account|transaction|下单|委托)、B (无 open(写)/write_parquet/os.replace/unlink/mkdir)、C (仅 client.get, 无 post/put/delete/patch)、D (api_key 仅 headers) — 测试在且绿 (本 verifier 单独跑 `-k read_only` → 1 passed)。

### LOCAL-02 — 配置与注册 — **PASS**

证据 (config.py / chain.py / preferences.py / api/settings.py + test_local_stockdb_registration.py 10 用例):

- **config 两键**: config.py:86-93 `local_stockdb_url: str = Field(default="http://127.0.0.1:8000")` + `local_stockdb_api_key: str = Field(default="")`, env `LOCAL_STOCKDB_URL` / `LOCAL_STOCKDB_API_KEY` 经 pydantic-settings 既有接线; `.env.example` 两行占位 (真实 key 只进 .env, 不入 git)。测试 `test_config_defaults` / `test_config_env_override` 绿。
- **lazy 单例**: chain.py:40-51 `local_stockdb_provider()` — `_provider_cache.get("local_stockdb")` 缓存, 首次构造 `StockDBProvider(base_url=settings.local_stockdb_url, api_key=settings.local_stockdb_api_key)`; `_get_provider("local_stockdb")` 分支 (行 83-84)。测试 `test_get_provider_local_stockdb_returns_singleton` (`a is b` 显式断言 + 构造 kwargs 捕获 == {base_url, api_key})、`test_singleton_uses_settings_defaults`。
- **链首插槽 (受管源优先, 位置配置化)**: `_BUILTIN_CHAIN` daily=`["local_stockdb","free_stockdb","ifzq","xyz","tickflow"]`, minute=`["local_stockdb","free_stockdb","ifzq","sina","xyz","tickflow"]` (adj_factor/financial/instruments 不动); `chain_for("daily")[0] == chain_for("minute")[0] == "local_stockdb"`。测试 `test_builtin_chain_heads_local_stockdb`; 用户覆盖保持原顺序不自动插链首 (`test_user_chain_override_position_wins` — 位置配置化)。
- **白名单 (静默回退陷阱锁)**: preferences.py:159 `_ALLOWED_DATA_PROVIDERS` 含 `local_stockdb`; `test_local_stockdb_in_whitelist` 在 `_clean_whitelist()` 隔离后断言 (缺失则 `_sanitize_chain` 过滤回 tickflow → 用例红); `test_set_provider_chain_keeps_local_stockdb_first` 断言保存链首不被过滤; test_data_source_selection.py `test_local_stockdb_swappable_via_preferences` 锁「前端切换假成功」陷阱 + 未知源仍安全回退。
- **health_check**: chain.py:167-175 并入 probe 分支, 探针符号用前缀形态 `"SH600519"` (裸码 400 误报防护, 服务端 schemas.py:25 要求前缀形态), 401/429 typed → "error"; `test_health_check_local_stockdb_ok_warn_error` 三态绿。
- **settings builtin**: api/settings.py:442-448 条目 `{name: "local_stockdb", display_name: "Local StockDB (本机)", datasets: ["daily","minute"], health: health_check(...), base_url: settings.local_stockdb_url}`; 单测 `test_settings_builtin_lists_local_stockdb` + 链级 TestClient 最小 app `GET /api/settings/data-sources` → 200 且 builtin 含条目 (test_provider_chain.py:564-589)。

### LOCAL-03 — 归一化契约 — **PASS**

证据 (夹具 4 个冻结 live 响应体 + test_stockdb_provider.py 三差异用例 + RESEARCH 锚点):

- **三差异唯一转换点**: `_map_daily_row`/`_map_minute_row` 单点归一化; `_to_suffix`/`_to_prefix` 纯函数 (前缀↔后缀双向)。
- **差异① symbol**: 夹具 `daily_sh600519_20260805.json` 原始 `"symbol":"SH600519"` → 契约 `df["symbol"][0] == "600519.SH"` (同股单键, 无分区键分裂); 请求侧 `600519.SH → symbols="SH600519"` 有显式断言 (`test_request_symbols_sent_in_prefix_form`)。
- **差异② 量单位恒等 ×1**: 夹具 `"volume_hand": 42689` → 契约 `df["volume"][0] == 42689.0 且 != 4268900.0` (恒等, 绝不 ×100); 锚点 RESEARCH.md:166「stockdb 42689 == 湖 42689.0 实测同值; 全分区 amount/(close×volume)≈100 证实湖=手」; 需求文本已修正为恒等 ×1 (commit 602a6f5, 规划期)。
- **差异③ 时区剥 aware→naive**: 夹具 `"date":"2026-08-05T00:00:00+08:00"` → `str(df["date"][0]) == "2026-08-05"` 且 `dtype == pl.Date`; 分钟面 `bar_time` aware → `datetime(2026,8,5,9,30)` 无 tzinfo + freq 列 = 请求字符串 (`test_minute_bar_time_is_naive`)。镜像 kline_sync 既有 `_normalize_daily` 语义 (naive 墙钟)。
- **写湖唯一经既有写路径**: 适配器输出规范化帧 → `normalize_daily(rows, source=self.name)` (既有 normalizer, 零改动) → 链 → `kline_sync` append_daily (merge-upsert + 原子 rename 既有机制); kline_sync.py/base.py/normalizer.py/repository.py 均零 diff。
- **夹具锚点 42689.0 由本 verifier live 复跑一致** (见 §4)。

### LOCAL-04 — 日K/分钟旁路 — **PASS**

证据 (chain.py fetch_with_chain 实现 + test_provider_chain.py 6 新增 + test_local_stockdb_write_path.py 4 用例):

- **链首 gap-merge (daily)**: `test_chain_local_stockdb_heads_gap_merge` — local 01-02/03 日 + free 02-03/04 日 → 3 行无重复, dates==[2024-01-02,03,04] ((symbol,date) 去重 + 前序覆盖); 实现: fetch_with_chain key_cols 按数据集 = `["symbol","date"]`, 已覆盖行 anti-join 剔除后 `concat(how="diagonal_relaxed")` (chain.py:113-157)。
- **链首 gap-merge (minute)**: `test_chain_local_stockdb_heads_minute_gap_merge` — (symbol,datetime) 去重合并 3 行 (key_cols minute=`["symbol","datetime"]`)。
- **空帧回退**: `test_chain_local_empty_falls_through` — local 空帧 → free 补全 (空帧=真空走回退语义保持); `test_chain_returns_empty_when_all_empty` 既有反例。
- **异常跳过 + 通道身份日志**: `test_chain_local_exception_skips_with_warning` — local 抛 `StockDBAuthError` → free 兜底 + caplog 断言 `chain[daily]` warning 行含 `local_stockdb`; `test_channel_identity_in_chain_log` — INFO 行 `chain[daily]: provider local_stockdb added 4 rows` (通道身份进日志; 湖无 provenance 列 → 身份不进湖, 铁律)。
- **默认链首断言**: `test_chain_builtin_heads_local_stockdb` — preferences.load={} 时 get_provider_chain("daily"/"minute")[0] 与 chain_for 均 == local_stockdb。
- **写路径冒烟 (全链贯通)**: `test_local_channel_writes_via_existing_append_daily` — fake local 链首 → fetch_with_chain → repo.append_daily → 湖 parquet, 返回 4 == 湖 `kline_daily/date=*/*.parquet` 总行数。
- **幂等写**: `test_local_channel_write_is_idempotent` — 二次运行 first==second==4, 湖行数仍 4 (merge-upsert `unique(subset=["symbol","date"], keep="last")` + 原子 rename 既有机制锁用户可观测结果)。
- **湖无 provenance 列 (铁律)**: `test_lake_schema_has_no_provenance_columns` — 湖 parquet schema ⊆ {symbol,date,open,high,low,close,volume,amount,quote_ts}, 无 source/fetched_at/schema_version/volume_hand/ingested_at。
- **双源分区守卫沿用**: 单源选择 = test_data_selection 既有白名单+可切换; run-slot 互斥 = test_auction_backfill._wait_slot_free 既有; 幂等写 = 本 wave 新锁 (机制未动)。
- **kline_sync.py 零改动** 已由守卫复核 (见 §1)。

---

## 3. 独立测试跑 (本 verifier)

```
$ cd backend && .venv/bin/python -m pytest tests/test_stockdb_provider.py tests/test_local_stockdb_write_path.py tests/test_provider_chain.py tests/test_data_source_selection.py -q
53 passed, 1 warning in 2.25s
```

| 文件 | 结果 | 构成 |
|---|---|---|
| test_stockdb_provider.py | 18 passed | 17 契约 (三差异/错误/批/限频/分钟端日语义) + 1 AST 守卫 |
| test_local_stockdb_write_path.py | 4 passed | 全链贯通/幂等/无 provenance 列/通道身份日志 |
| test_provider_chain.py | 23 passed | 6 新增 local 链首 (gap-merge daily+minute/空帧回退/异常跳过/默认链首/TestClient settings 面) + 既有 17 |
| test_data_source_selection.py | 8 passed | 白名单可切换 (local_stockdb) + 未知源回退等既有 |

(40-03 claim「test_provider_chain + test_data_source_selection 合并 31 passed」= 23+8 ✓; wave1 17 + wave2 41 + wave3 新增与既有混合, 新增测试总数与 claim 一致。全量 1836 passed/4 skipped 记录于 40-03-SUMMARY, 由 orchestrator 统一最后跑, 本 verifier 按分工只跑相关文件。)

## 4. live 冒烟 — 本 verifier 独立复跑 (非仅采信证据文件)

真实 stockdb 服务可达 (`curl /health` → 404, 与 runbook 前置一致), `../../stockdb/.env` 存在 (STOCKDB_API_KEYS 首 key 读取):

- **空 key 对照**: 无 key 请求 → `StockDBAuthError` 抛自真实服务端 401 `{"error":"unauthorized","detail":"invalid api key","code":401}` — typed 路径实测复现。
- **带 key 冒烟** (LOCAL_STOCKDB_API_KEY 注入 + `get_daily(['600519.SH'], 2026-08-05..2026-08-05)`):

```
rows: 1
[{'symbol': '600519.SH', 'date': datetime.date(2026, 8, 5), 'open': 1328.36, 'high': 1333.8, 'low': 1303.5, 'close': 1306.45, 'volume': 42689.0, 'amount': None}]
SMOKE-OK re-verified by verifier: volume == 42689.0
```

- 与 40-03-SUMMARY 摘录逐字段一致: symbol 后缀形态, date naive, close 1306.45, volume 42689.0 (双源交叉锚点), amount=None 诚实透传 (腾讯日K合法缺成交额); 单请求 1 标的, 不触限频。

## 5. ROADMAP success criteria 对照

| # | 判据 | 证据 |
|---|---|---|
| 1 | `_get_provider("local_stockdb")` 解析 lazy 单例; auction=False 诚实声明; 永不入 auction_probe 链 | chain.py:40-51 + 测试 `a is b`; stockdb_provider.py:70-79; auction_probe.py:110 枚举 gate |
| 2 | config 两键 + env 注入; X-API-Key header-only; 限频 120/min 对齐; 429 带 Retry-After | config.py:86-93 + env 测试; `_get_json` headers-only + AST 判据 D; rpm 契约测试; 429 头/体回退测试 |
| 3 | 归一化契约锁三差异 (同股双键/100×量失真/时区漂移永不发生); 写湖唯一经既有写路径 | 夹具+三差异契约测试 (42689.0/!=4268900.0/naive); normalizer.py/kline_sync.py 零改动 |
| 4 | daily/minute 链首 gap-merge 经既有 kline_sync 写路径; 双源守卫沿用; 通道身份进台账 (湖无 provenance 列) | gap-merge daily+minute 测试; 写路径 4 冒烟 (幂等/无 provenance/日志身份); 守卫沿用清单 |
| 5 | 零新增运行时依赖; hermetic + live 冒烟通过 | pyproject/uv.lock 0 行; 53 passed (相关文件) + 全量 1836/4 (orchestrator 末跑); live 复跑 SMOKE-OK |

## 6. 诚实边界 (behavior_unverified)

**已验证**: 适配器/注册/归一化契约/链集成/写路径冒烟全量行为级验证 (代码 + 契约测试 + 夹具, 本 verifier 重跑 53 passed); 守卫 (dep/kline_sync/Watchlist/AST 四判据) 全绿; live 冒烟由本 verifier 在宿主独立复跑通过 (42689.0 双源锚点一致 + 空 key 401 typed 路径实测)。

**未验证 (behavior_unverified)**: (1) **容器内 127.0.0.1:8000 连通性** — live 冒烟在宿主跑 (本 verifier 已复跑), 但 app 容器 (3018 形态) 内到 stockdb 容器的 loopback 可达性未在部署拓扑实测, 容器内 health 仍属 UNKNOWN (RESEARCH 已记录该部署形态差异; Phase 44 DEP 重建配方验证项); (2) **双源真实链长期行为** — ETag/304 条件缓存未启用 (研究建议, PLAN 未含), 真实链上长期 gap-merge/429 窗/空帧-vs-403 行为需生产观测; 本 phase 提交的验收 = 适配器 + 注册 + 契约锁 + 链集成 + 写路径冒烟 + 宿主 live 冒烟, 均已交付。

## 7. Human items (sandbox 无法断言)

1. **真实 stockdb key 轮换/审计归因**: LOCAL-02「建议专用 AthenaQuant key → 限频桶隔离 + 审计归因」为建议非强制 — 适配器接受任意 `LOCAL_STOCKDB_API_KEY` (env 注入, 不入 git)。Operator 须在 stockdb 服务端 `STOCKDB_API_KEYS` 配置专用 AthenaQuant key (与开发/其他消费方隔离限频桶), 并纳入轮换纪律; 审计归因依赖不同消费方使用不同 key, 当前无强制校验。
2. **容器内 127.0.0.1 连通性**: live 冒烟在宿主通过, 但部署后 app 容器内访问 stockdb (:8000) 的连通形态 (loopback / host 网络 / 网关) 需在部署拓扑实测判定 — Phase 44 DEP 重建配方中验证 (stockdb 凭证/连通性 preflight); 容器内 health 未点亮前不得假设。
3. **双源真实链长期行为**: 真实生产链上 local_stockdb 链首 + 兜底源的长期运行观测 — 429 窗实际触发/回退表现、空帧-vs-403 分类、ETag/304 缓存未启用的带宽/延迟影响 (研究建议, PLAN 未含, 如生产暴露可后续补); 全量扩湖 (Phase 42 backfill-minute) 依赖本通道 120/min 档位纪律, 批次节奏需按限频档位执行。

## 8. Honesty notes

- 所有 PASS 证据为本 verifier 亲自重观察: 自己的 pytest 跑 (53 passed + 18/4/23/8 分文件 + AST 守卫 -k 单跑), 自己的 git log/diff/status 跑 (12 commits 顺序与 claim 一致, dep/kline_sync/Watchlist/env-example 守卫), 自己的 live 冒烟复跑 (42689.0 + 401 typed)。
- 全量 1836 passed/4 skipped 采信 40-03-SUMMARY 记录并按分工交由 orchestrator 末跑 — 本 verifier 不重复全量, 不虚报为已跑。
- RESEARCH.md:166 锚点 (stockdb 42689 == 湖 42689.0, amount/(close×volume)≈100 全分区交叉验证) 与 live 复跑一致; LOCAL-03 需求文本修正 (602a6f5) 为规划期产物, 本 phase 执行区间未再改需求文本 (overrides_applied: 0)。
- stockdb_provider.py 中 `_PROVENANCE_COLS` 常量为未引用死代码 (归一化通过 `_map_daily_row` 显式选列隐式丢弃 provenance 字段, 契约测试锁死湖面无污染) — 记录为惯性备注, 非缺陷, 不影响验收。
- 容器内连通性 / key 轮换强制化 / 双源长期行为三事项按既有政策诚实标注, 不标记为已验证。
