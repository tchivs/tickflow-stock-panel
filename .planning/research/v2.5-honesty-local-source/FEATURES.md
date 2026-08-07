# Feature Landscape — 本机 stockdb 数据源通道 + 诚实性加固 (v2.5)

**Domain:** AthenaQuant 受管数据源通道 (stockdb SDK) · **Researched:** 2026-08-07 · **模式:** Ecosystem (live probe 佐证) · **语言:** 中文
**结论速览:** 竞价撮合 **T-day 可用 / 历史部分可用 / 逐笔级不可得**; 日 K 深度+复权 **可用**; 分时 **当日可用**; 鉴权限频 **X-API-Key + slowapi 双层, 明确**。

---

## 1. 竞价数据可得性 (核心问题①)

| 层次 | 结论 | 证据 (live 实测 2026-08-07, key=testkey123) |
|------|------|------|
| **T-day 09:25 撮合行** | **可用** — tick 湖含 `09:25:00` 真实撮合行 (price/vol_hand/num_trades/buyorsell), 比 xyz 单行多 num_trades | `data/ticks/sh/SH600519/20260807.parquet`: `09:25:00 1308.66/173手/120笔/中性`; 对账闭合: 17300×1308.66 = 22,639,818 = intraday 09:30 bar amt |
| **T-day 09:15-09:24 窗口快照** | **可用** — 3s 快照级委托统计 (price+累计虚拟量, num_trades=0); 是**虚拟匹配量**非逐笔 | 同 parquet 首行 `09:15:07`, 09:24:58 vol=158 → 09:25:00 撮合 173; DATA_CONTRACTS.md:1163-1169 |
| **历史竞价 (回填)** | **部分可用** — 分钟 `09:30 bar = 集合竞价统计` (量/额) 历史含之; 但分钟湖极稀疏 (16 文件, 600519 仅 2026-08-05) | `/v1/minute/sh600519?freq=1` → `2026-08-05T09:30 v=521手 amt=69,207,556` (52100×1328.36 闭合); DATA_CONTRACTS.md:382-387, 449-459 |
| **历史全宇宙竞价明细 / 逐笔级** | **不可用** — tick 无历史回填 (免费源历史分笔不可得, TDX 仅交易时段); 解锁路径 = `backfill-minute` (Tushare stk_mins, DATA_CONTRACTS.md:1070) 扩湖后取 09:30 bar | `data/ticks/` 15 文件全为 20260807; `/v1/ticks/sh600519?date=2026-08-06` → 0 行; TickBar 无逐笔展开 (schemas.py:426-441) |
| **DATA-06 派生输入** (unmatched_volume/virtual_price) | **UNKNOWN** — 09:15-09:24 行 vol_hand 是虚拟匹配量 (累计), 非未匹配委托量; 语义映射需 probe, 不猜测 | tick 行 num_trades=0 + vol 递增形态 |

**结论:** stockdb 可作 **T-day 竞价通道** (撮合明细+窗口快照, 逐秒级) 与 **历史竞价统计通道** (分钟 09:30 bar); 但不能立即解锁 xyz 全量历史回填 (FA-04) — 需先扩分钟采集或自 T-day 逐日累积。日 K/实时旁路立即可用。

---

## 2. 能力面盘点 (问题②③④)

| 能力 | 结论 | 证据 | 复杂度/依赖 |
|------|------|------|------|
| 历史日 K 深度 | **可用** — 600519=4024 行 (≈2005 起); daily lake 7649 parquet | `/v1/daily/sh600519` length=4024 | Low |
| 复权 adjust=none\|qfq\|hfq | **可用** — 读取时纯函数 (湖只落原始价) | DATA_CONTRACTS.md:101-102, 248-250; qfq 实测生效 | Low |
| 分时 intraday | **当日可用** — freq=1 当日窗口, 腾讯 close-only, 09:30=竞价统计; 无跨日历史 | `/v1/intraday/sh600519`; DATA_CONTRACTS.md:650-654 | Low |
| 鉴权 | **X-API-Key** header; 无 key → 全 401; compare_digest | API.md:37-49; .env `testkey123` | Low (自托管) |
| 限频 | **slowapi 端点 + 内核 token bucket**: quotes 300/min, daily/minute/intraday 120/min, **ticks 60/min**; 429 带 Retry-After | openapi.json; API.md:100-127; DATA_CONTRACTS.md:686-691 | 回填节奏=约束 |
| SDK | StockDBClient typed: quote/daily/minute/intraday/depth/financial/factors/jobs/symbols/tushare; **无 tick 方法** | sdk/client.py:76-226 | Med (tick 走 raw HTTP 或补 SDK) |
| 其他 | 实时快照/WS 推送 (API.md:568-572) · 五档 depth · 财务/因子 · /v1/market/* · MCP /mcp (host 白名单 API.md:647-649) | openapi 40 路由 | — |

**限频对回填的约束 (下游建议):** 5537 标的竞价回填走 minute 09:30 bar 路径: 120/min → ≈46 min 严格限频完成 (远优于 xyz ~2h 窗 70-100 请求); ticks 60/min 则 ×2。

---

## 3. Table Stakes (通道必备)

| Feature | Why | Complexity | Notes |
|---------|-----|------------|-------|
| 鉴权 + 限频纪律 | 受管通道必须可审计限速 | Low | X-API-Key + slowapi; 429 语义完整 (API.md:86-90) |
| 诚实缺失语义 | 空=本地无非异常; adjust 因子缺失 → 显式 ValueError | Low | DATA_CONTRACTS.md:662-663 (MJ-06/EXRI-03) |
| 历史日 K + 复权 | 策略/回测底座 | Low | 4024 行/600519, qfq/hfq |
| 实时快照/分时 | 盘前/盘中面 | Low | quotes + intraday + WS |
| SDK 类型化客户端 | 通道接入点 | Low | 连接复用/ETag 304/重试 |

## 4. Differentiators (相对 xyz)

| Feature | Value | Complexity | Notes |
|---------|-------|------------|-------|
| T-day 竞价窗口快照 (09:15-09:24 + 09:25 撮合, 逐秒) | 超越 xyz 单行: 多 num_trades + 窗口形态 | Med | tick 需 sidecar 盘中定时采集 (collect_loop --tick-every) |
| 分钟 09:30 bar = 历史竞价统计 | 历史竞价路径 (扩分钟湖后) | Med | 依赖 backfill-minute (Tushare token) |
| 复权读取时计算 | 湖原始价不被污染 | Low | 与 AthenaQuant 前复权口径一致 |
| ETag/304 + fields 裁剪 | 回填带宽友好 | Low | DATA_CONTRACTS.md:880-886 |
| 本地旁路 (日 K/实时) 零配额 | 解除 xyz 2h 窗依赖 | Low | 立即可用 |

## 5. Anti-Features (显式不建)

| Anti-Feature | Why Avoid | Instead |
|--------------|-----------|---------|
| 09:15-09:24 委托统计 (num_trades=0) 入 canonical 湖 | 虚拟量非成交 | 湖只收 09:25:00 撮合行 (555..565 谓词已锁) |
| 分钟 09:30 bar 标为"逐笔" | 是聚合统计 (close-only) | 标注 集合竞价统计 |
| 宣称 stockdb 解锁全量历史竞价回填 | 分钟湖 16 文件 / tick 无历史 | 诚实标注: T-day 通道 + 历史路径待扩湖 |
| daily amount=null 当错误 | 腾讯 6 字段源无 amount (合法三态) | 按三态处理 |
| 伪造 tick 历史回填 | 免费源历史分笔不可得 | 诚实缺口声明 |
| BJ 缺口与 403 配额吞请求同标签 | 即 HON-1 待修 | source_blocked 标签区分 |

## 6. 诚实性修复 + 部署日执行面 (B/C 特征)

| 项 | 规格 | 证据锚点 |
|----|------|----------|
| HON-1 `source_blocked` 标签 | 非 BJ 标的 `empty_response` (403/配额吞) 与 BJ 永久缺口 (333) 可区分; 现状 reason 无法区分 | verify_auction_backfill.py:187-217; FA-05-BJ-STANCE.md |
| HON-2 逐 symbol 进度 emit | 空帧路径 `continue` 跳过循环底 emit → 配额窗全空批次进度冻结; 修复 = 每 symbol 恒 emit (含空帧) | auction_backfill.py:279-293 (continue) vs :308-312 (emit); W-4 :243-248 |
| D 系 runbook | D1 09:26 盘前 / D2 15:30 EOD / D3 竞价源接入 / D4 监控 / D5 复盘 / D6 R13 / D7 概念 drift (≥5 交易日) / D8 立场 | docs/deploy-verification.md:16-190 |
| 3 新端点 200-body | POST /api/kline/auction/backfill · GET /api/research/backtest(+/{run_id}) · GET /api/research/auction/validation | REQUIREMENTS.md DV-01 |
| 3018 容器对齐 | image 2026-08-04 vs HEAD 2026-08-07, 4 运行时文件 md5 全 DIFFER → D8 rebuild 对齐 | docs/deploy-verification.md:206-209 |

## 7. 下游消费者建议

1. **竞价适配器**: T-day 取 tick `09:25:00` 行 (vol_hand×100=股, price×vol_hand×100=元, 对账已闭合); 历史取分钟 `09:30 bar` (volume_hand×100 / amount_yuan); 两路统一 canonical 四列; symbol 转换 `SH600519` → `600519.SH`.
2. **SDK**: tick 无 typed 方法 → raw `_get("/v1/ticks/...")` 或补 SDK 方法; minute/intraday/daily 直接用 typed 方法.
3. **回填节奏**: minute 路径 120/min → 5537 标的 ≈46min, 可替代 xyz 数周 campaign; 但历史竞价需先扩分钟湖.
4. **HON-1/2** 纯后端 Low 改动, 可作 v2.5 前置 commit; 空帧 emit 修复同惠 CLI 与 job 轮询面.

## Sources

- stockdb: DATA_CONTRACTS.md (§7/§12/§21), API.md (§2/§4/§7), README.md, sdk/client.py, schemas.py:426-441, providers/eastmoney.py:724-745, live curl (127.0.0.1:8000, 2026-08-07)
- AthenaQuant: PROJECT.md (v2.5), data_providers/xyz_provider.py:48-203, services/auction_backfill.py, scripts/verify_auction_backfill.py, docs/deploy-verification.md, docs/features.md:84-89
- 置信度: 竞价 T-day/历史部分/日 K/鉴权限频 = HIGH (live 实测+对账闭合); DATA-06 输入映射 / 逐笔级 = UNKNOWN (需 probe)
