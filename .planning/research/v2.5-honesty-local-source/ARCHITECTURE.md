# 架构研究: stockdb 本地通道接入 + 竞价诚实性修复落点

**Domain:** AthenaQuant 受管数据源通道接入 (v2.5-A) + 诚实性修复 (v2.5-B) + 部署日 (v2.5-C)
**Researched:** 2026-08-07
**Overall confidence:** HIGH (双仓源码 + live 探测双证据)

## 1. 顶层结论 (TL;DR)

1. **通道形态 = HTTP 适配器, 非进程内 SDK import。** AthenaQuant backend 运行时为 CPython 3.11 (backend/.venv/pyvenv.cfg: home=/usr/bin, python3.11; 服务 pyc 全 cpython-311), stockdb `requires-python = ">=3.12"` (stockdb/pyproject.toml) → 进程内 import 被版本下限硬挡; 且 `stockdb.sdk.client.StockDBClient` 本身就是 httpx HTTP 客户端 (sdk/client.py:1-2), 进程内嵌入零数据面收益。新 provider 镜像 `free_stockdb_provider.py` 的 httpx 模式, **零新增运行时依赖** (httpx/polars 已在 backend deps, pyproject.toml)。
2. **关键可行性发现: 本机 stockdb 无任何竞价能力。** openapi 41 个 `/v1/*` 路径无 auction; src 全库 grep "auction" 仅 9 处 (分钟语义注释); 09:26 撮合行被 adapter 重标 09:30 折入分钟 bar (docs/DATA_CONTRACTS.md:492-494), 09:15-09:25 委托统计行被丢弃; lake 模块只有 duckdb_views/layout, 无竞价表。→ **竞价湖 (DATA-04..06) 本轮唯一来源仍是 xyz**; stockdb 通道只服务 daily/minute/quotes/factors 等链。若 v2.5 意图 stockdb 当竞价源, 属跨仓 blocker (需 stockdb 侧新增 09:26 撮合行端点)。
3. **诚实修复落点核实: source_blocked 是真缺口; "进度冻结@287-296" 行号已过期。** 逐 symbol emit 自初始提交 733b650e 起就在循环内 (auction_backfill.py:308-313, blame 证实); 里程碑所指 287-296 为空帧处理分支。**真实残留冻结 = fail-closed 提前返回路径无任何 emit** (行 200/224/228/266/268 直接 return, 无 done/进度行) + CLI 不接线 on_progress (默认 `_noop`, scripts/auction_backfill.py:104+ 调用处不传)。403 配额窗全灭场景恰好走 preflight_empty (行 268) → 0 进度行 → 冻结观感。
4. **鉴权: API key 必选, loopback 只是传输属性。** live 实测: 无 key 访问 /v1/health 与 /v1/quotes 均 401, 假 key 401 (api/auth.py require_api_key 全端点依赖, 无 loopback 豁免; MCP 另经中间件, api/app.py:134 层序 audit→auth)。

## 2. 集成点 (现有 seam)

| Seam | 现状 (证据锚点) | 对 stockdb 通道的意义 |
|---|---|---|
| Provider Protocol | `MarketDataProvider` + `ProviderCapabilities` (base.py:9-38), auction 能力位在 base.py:26 | 新 provider 声明能力即获链内资格 |
| 内置链 | `_BUILTIN_CHAIN`: daily=[free_stockdb,ifzq,xyz,tickflow], minute=[free_stockdb,ifzq,sina,xyz,tickflow] (chain.py:20-26) | stockdb_local 插入各链, gap-merge 语义不变 |
| 分发+单例 | `_get_provider` (chain.py:56-73) + `_provider_cache` lazy singleton | 新增 name 分支 + 单例工厂 (镜像 xyz_provider() chain.py:43-49) |
| 竞价单源选择 | 不在链里 — 隐式: `_default_sources`/`_first_auction_provider` (auction_probe.py:75-96, auction_sync.py:97-138) 枚举 capabilities.auction 内置源 + auction 数据集自定义源, **只取第一个, 探测与写湖必须同源** (auction_sync.py:106-109 注释) | 双源守卫的核心机制已存在 |
| 单一写路径 | `write_auction_partitions` (auction_sync.py:34-95): date= 分区 merge-upsert unique([symbol,datetime] keep=last), .tmp 原子 rename, 555..565 窗口谓词, canonical 4 列 + 2 可选 | 新通道写湖仍唯一经此, 无需新写面 |
| 湖 provenance | **湖无 source 列** (auction_backfill.py:15-18 铁律: provenance 即分区存在性, AQ-01..06 决策) | 通道身份只进 probe verdict.source / 终态 dict / 台账 |
| 鉴权/限频 | stockdb 全端点 X-API-Key (api/auth.py), 常数时间比较; 每客户端 token-bucket + slowapi 档位 (ARCHITECTURE.md 限频记账: quotes 300/min, daily 120/min, minute 60/min); key_hash 审计 (api/audit.py) | AQ 适配器须带头 + 尊重档位限频 (minute 60/min 是硬上限) |

## 3. 新组件 vs 修改

### 新组件
1. `backend/app/data_providers/stockdb_provider.py` — HTTP 适配器 (镜像 FreeStockDBProvider):
   - `name = "stockdb_local"` (与既有 "free_stockdb" 区分, 避免链名/台账混淆)
   - capabilities: daily/minute/instruments 按服务端真实能力声明 (openapi 证实); **auction=False 诚实声明** (服务端无此能力, 绝不伪造)
   - `get_auction` → 抛 NotImplementedError 或空帧 (镜像 fixture 语义), 进不了竞价候选
   - X-API-Key 头 (header-only, 禁 URL 传参 — 镜像 stockdb CR-02 纪律) + settings.stockdb_url/stockdb_api_key
   - 限速: 复用 `sleep_between_batches` (tickflow/rate_limits) 对齐服务端档位
2. `backend/app/config.py` — 新 settings 字段: `stockdb_url` (default `http://127.0.0.1:8000`, 镜像 free_stockdb_url config.py:80) + `stockdb_api_key` (env, 镜像 tickflow_api_key config.py:77)

### 修改
1. `chain.py`: `_get_provider` 新增 `stockdb_local` 分支 + lazy singleton + `_BUILTIN_CHAIN` 插槽 (daily/minute 建议链首 — 受管源优先; 或配置化位置, 决策点)
2. `xyz_provider.py:189-198` (get_auction try/except 吞空) + `:228-250` (_call_tool: `raise_for_status` 243, 异常/error 字段→"" 247/250): 把 **HTTP 403 / 错误文案配额窗 markers** 分类为 policy-block 信号 (typed 异常或带 reason 的空帧), 其余网络错误保持"空帧不抛"契约 (test_xyz_provider.py:126-137 断言依赖)
3. `services/auction_backfill.py`: 台账 reason 第三类 `"source_blocked"` — 现有两键形状 {symbol,reason} 不变 (test_auction_backfill_honesty.py:213 断言), 与 empty_response / str(e)[:200] 互斥 (同文件:284-305 需扩展); **所有 fail-closed 提前返回 (行 200/224/228/266/268) 补终态 emit** — 治"进度冻结"真因; 逐 symbol emit (308-313) 已存在, 勿重复实现
4. `services/auction_probe.py`: preflight 遇 policy-block → verdict fail_closed + detail="source_blocked" (现状 detail 见 NOT_CONFIGURED/FAIL_CLOSED 常量, 行 20-21)
5. `scripts/auction_backfill.py`: CLI 接 on_progress 打 stderr (现零进度输出) — 运营视角可见
6. `tests/`: test_xyz_provider.py (空帧契约改分类), test_auction_backfill_honesty.py (第三类 reason + fail-closed emit 断言), 新 test_stockdb_provider.py (hermetic, 镜像 test_xyz_provider 罐装模式)

## 4. 数据流变化

- **竞价流 (不变, 源仍 xyz):** xyz MCP → get_auction → run_auction_backfill (探针闸门→范围对齐→only_missing 预扫→预检→串行限速) → write_auction_partitions → kline_auction/date=*; 读: attach_auction_columns probe×分区双闸门 (auction_columns.py)。变更仅在失败分类 (source_blocked) 与终态进度 emit。
- **daily/minute 流 (新增通道):** stockdb_local 进链首 → fetch_with_chain gap-merge → 既有 kline_sync 写路径。数据流形状不变, 只是源优先级前移。
- **provenance:** 湖仍无源列; 通道身份进入台账 (per-symbol reason 的 source 语义) 与终态 dict (可选加 `source="xyz|stockdb_local"` 键 — W-5 键集扩展, 需测试矩阵同步, 决策点)。

## 5. 双源分区守卫 (Q②) — 结论: 现有机制已覆盖, 无新守卫类

- **竞价湖:** 单源选择 (`_first_auction_provider` 只取第一个, 探测与写湖同源) + 重任务 run-slot 互斥 (API 路径 try_acquire_run_slot, R7, api/auction_backfill.py:97-99) + merge-upsert 幂等 + last-rename-wins 原子写。本轮 stockdb 无竞价能力 → **竞价零新守卫**。若未来 stockdb 加竞价端点: 配置化单源偏好 (勿让 sorted() 隐式决定), 回填/EOD 错峰 (CLI 已文档化纪律)。
- **daily/minute:** 链内多源本就走同一写路径 gap-merge,"混写" 是补缺口的设计语义而非损坏; **不引入 per-partition 源戳** (与 AQ"湖无 provenance 列"决策冲突, 列为决策点)。
- 剩余真实风险面: CLI 无 run-slot (文档化纪律 "避开 EOD 窗口") + 双回填任务跨端点并发 — 维持现状纪律即可, 不建议本轮扩守卫。

## 6. 鉴权 (Q③) — 结论: API key, 非 loopback trust

- 服务端**无 loopback 豁免** (live 401 实测 health/quotes); X-API-Key header-only (CR-02 禁 URL token); 常数时间比较 + key_hash 审计 (api/auth.py, api/audit.py)。
- AQ 侧: env 注入 `STOCKDB_API_KEY`, **建议专用 AthenaQuant key** — 限频桶隔离 (per-key) + 审计归因 (服务端可区分通道来源, 即服务端侧 provenance)。
- 部署: D8 parity 清单须含 stockdb key/url 同步到 AQ env; 127.0.0.1 传输不需 TLS, 但 key 不得落日志/落盘。

## 7. 构建顺序 (Q⑤)

- **P0 受管通道** (Phase A): config settings → stockdb_provider.py → chain 注册 → hermetic 测试 → live 冒烟 (受控读, 镜像 test_provider_chain 模式)。
- **P1-1 source_blocked** (Phase B, 独立于 P0): xyz 分类 → backfill reason 第三类 → probe verdict → 测试扩展。
- **P1-2 进度诚实** (Phase B, 独立于 P0): fail-closed 终态 emit + CLI on_progress → emit 断言测试。
- **P2 部署日** (Phase C, 依赖 P0 全绿): env parity, 运行前 /v1/health 预检 (带 key), md5 parity 覆盖 stockdb 相关配置, 3018 stale container 处置纳入清单。
- 依赖: P1 两件均不依赖 P0 (纯 AQ 内修改); P0 不依赖 P1; **P0 与 P1 可并行, P2 收口**。若"竞价源切换"是隐性预期 → 必须先开 stockdb 竞价可行性门 (跨仓), 独立 phase, 阻塞 (A)。

## 8. 证据锚点汇总

| 事实 | 锚点 | 置信 |
|---|---|---|
| AQ 运行时 3.11 | backend/.venv/pyvenv.cfg; 服务 pyc cpython-311 | HIGH |
| stockdb ≥3.12 | stockdb/pyproject.toml requires-python | HIGH |
| SDK 即 HTTP 客户端 | stockdb/sdk/client.py:1-2 | HIGH |
| 本机无竞价端点 | openapi 41 路径; src grep "auction" 9 处 (0 功能); DATA_CONTRACTS.md:492-494 | HIGH |
| 全端点 401 | live curl health/quotes 无 key 401, 假 key 401 | HIGH (实测) |
| 逐 symbol emit 已在 | auction_backfill.py:308-313, blame=733b650e | HIGH |
| fail-closed 无 emit | auction_backfill.py:200/224/228/266/268 | HIGH |
| 403 吞空 | xyz_provider.py:194-198 + 236-251 (raise_for_status 243→"" 247) | HIGH |
| 台账两键契约 | test_auction_backfill_honesty.py:213, 284-305 | HIGH |
| 湖无 provenance 列 | auction_backfill.py:15-18 铁律 | HIGH |

## 9. 下游消费者建议

- **Roadmapper:** Phase A=P0 (stockdb 通道, 新组件 2 个+chain 修改), Phase B=P1 两项诚实修复 (纯 AQ 内, 可合并或拆分), Phase C=P2 部署日。竞价源切换若在范围内 → 前置跨仓可行性 phase。
- **Synthesizer:** 把"本机 stockdb 无竞价端点"提为全局风险 (影响 (A) 的范围定义); "3.11 vs 3.12" 决定通道形态 (HTTP 非 SDK import), 写入 STACK 决策理由。
- **开放问题:** ① xyz 403 配额窗的**真实响应体结构 UNKNOWN** (窗口未触发, 无法复现) — 分类器以 HTTP 403 + 文案 markers 双信号设计, 需 2h 窗复现时回填定稿; ② W-5 终态是否加 `source` 键 (决策点); ③ stockdb 未来竞价端点排期 (跨仓, 未知)。
