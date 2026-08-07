# Requirements: AthenaQuant v2.5 诚实加固与本机数据源接入

**Defined:** 2026-08-07
**Core Value:** An investor can turn reliable market data and their own holdings into an auditable, actionable research and monitoring workflow without operating multiple disconnected tools.

## v2.5 Requirements

Requirements for the v2.5 milestone. Each maps to a roadmap phase. Research basis: `.planning/research/v2.5-honesty-local-source/SUMMARY.md` (commit c507c66; confidence HIGH). Key research findings: (1) 本机 stockdb 无竞价端点 (openapi 41 路径零 auction) → 竞价源仍受 xyz 配额窗约束; (2) SDK 需 Python ≥3.12 (PEP 695, 3.11 实测 SyntaxError) → 通道形态 = HTTP 适配器, 零新增运行时依赖; (3) 日K+复权 (600519=4024 行) 与 T-day 竞价窗口 (09:25 撮合行对账闭合) 可用; 分钟 09:30 bar = 集合竞价统计 → 5537 标的 ≈46min 历史统计路径; (4) 403-vs-真空吞错链 (xyz_provider.py:189-198/:228-250) 与 fail-closed 零 emit 为两处真实诚实性缺口; (5) 双源归一化 (symbol/单位/时区) 为头号风险。Cross-cutting guards: 零新增运行时依赖, 诚实 provenance (source_blocked 三态 / 统计口径绝不算逐笔 / fail-closed 空态), POOL-03 零执行权 AST guard, user `Watchlist.tsx` 零触碰。

### stockdb 本地通道接入 (Local Source Channel) — Phase 40

- [x] **LOCAL-01**: `local_stockdb` HTTP 适配器 — `backend/app/data_providers/stockdb_provider.py` 镜像 FreeStockDBProvider httpx 模式: `name = "local_stockdb"`, `ProviderCapabilities` 诚实声明 (`auction=False`), X-API-Key header-only (禁 URL 传参), `sleep_between_batches` 对齐服务端限频档位 (quotes 300/min, daily/minute/intraday 120/min, ticks 60/min, 429 带 Retry-After); 零新增运行时依赖 (httpx/pydantic 已在 deps)。
- [x] **LOCAL-02**: 配置与注册 — `config.py` 新增 `local_stockdb_url` (默认 `http://127.0.0.1:8000`) + `local_stockdb_api_key` (env 注入, 不入 git, 建议专用 AthenaQuant key → 限频桶隔离 + 审计归因); `chain.py` `_get_provider` 新增分支 + lazy singleton + `_BUILTIN_CHAIN` 插槽 (daily/minute 链首, 受管源优先, 位置配置化)。
- [x] **LOCAL-03**: 归一化契约 — 适配器单点归一化: `SH600519→600519.SH` 前缀映射 + 量单位对齐 (**实测 stockdb 输出 `volume_hand` 手 == 湖内手, 恒等 ×1**; 研究 Q1: 需求原稿「手→股×100」为假设, 实测推翻 — 契约测试锁死量级不漂移) + 时区剥 aware (实测 `2026-08-05T00:00:00+08:00` → naive, 镜像 `kline_sync.py:93-132 _normalize_daily`), 契约测试锁死三差异 (同股双键/量级失真/时区漂移永不发生); 写湖唯一经既有写路径 (merge-upsert 幂等 + 原子 rename)。
- [x] **LOCAL-04**: 日K/分钟旁路 — daily/minute 流经新通道进链首 gap-merge 走既有 `kline_sync` 写路径; 双源分区守卫沿用现有机制 (单源选择 + run-slot 互斥 + 幂等写); 湖仍无 provenance 列 (铁律), 通道身份进台账/终态 dict。

### 诚实性修复 (Honesty Fixes) — Phase 41

- [x] **HON-01**: `source_blocked` 三态化 — xyz_provider.py:189-198/:228-250 HTTP 403/配额窗 markers 分类为 policy-block 信号 (typed 异常或带 reason 空帧), 其余网络错误保持「空帧不抛」契约 (test_xyz_provider.py:126-137 保持绿); 台账 reason 第三类 `"source_blocked"` (两键形状 {symbol,reason} 不变, 与 `empty_response`/`str(e)[:200]` 互斥); `services/auction_probe.py` preflight 遇 policy-block → verdict `fail_closed` + detail=`"source_blocked"`; R1 重试只对可重试态生效。
- [x] **HON-02**: fail-closed 终态 emit — `services/auction_backfill.py` 所有 fail-closed 提前返回路径 (行 200/224/228/266/268) 补终态 emit (每 symbol 一行, 含 reason); 取消路径独立 stage (`cancelled`/实际 pct, 绝不 `done`/100); `scripts/auction_backfill.py` CLI 接 on_progress 打 stderr (现零进度输出); 回归锁: 全空帧批量 → 断言每 symbol 进度行 + 终态 failed 计数正确。

### 分钟湖扩湖 → 历史竞价解锁 (Minute Lake Expansion) — Phase 42

- [ ] **MIN-01**: 分钟湖扩湖 — stockdb 通道 backfill-minute 落 `kline_minute` 分区, 5537 标的全宇宙驱动 (逐 symbol 幂等跳过 + merge-upsert 原子写); 增量续跑幂等。**源覆盖 source-gated (研究实测, 42-RESEARCH)**: 当前 Tushare token stk_mins 频限 1 次/小时 (两次 40203 实测) → 全量覆盖需数年, 不可达; 备选源深度封顶 (腾讯 ≈3 日 / TDX ≈90 日无 09:30 bar / 东财不可达); ≈46min 仅为 AQ 读侧节奏 (5537×1 GET @120/min)。机制 (驱动/幂等/夹具测试) 零源依赖交付; 实际覆盖 = 源插件深度, 升级 token 档位或部署目标机 (3018) 重探为 checkpoint:human-verify (与 FA-04 source-gated 先例同构, 绝不虚报覆盖)。
- [ ] **MIN-02**: 历史竞价统计路径 — 分钟 09:30 bar = 集合竞价统计 (量/额) 进入竞价覆盖报告 (独立统计口径, 绝不算逐笔); FA-04/RC-02 统计口径解锁门 (≥0.94 或诚实 partial, 双口径并列报告)。
- [ ] **MIN-03**: 分钟诚实标注 — 09:30 bar 标注「集合竞价统计」非逐笔; canonical 竞价湖只收 09:25 撮合行 (09:15-09:24 委托统计绝不入湖); T-21-01 分钟截断语义不回归 (evaluation_time 截断保持)。

### T-day 竞价采集 sidecar (T-Day Auction Capture) — Phase 43

- [ ] **SDC-01**: 盘中 sidecar 采集 — 09:15-09:25 逐秒快照 + 09:25 撮合行定时采集 (独立脚本 + 盘中 cron 窗口); live 对账闭合 (09:25 撮合行 price×vol == intraday 09:30 bar amt); 数据落 staging (tick 湖/独立目录), 不入 canonical 湖 (虚拟量非成交)。
- [ ] **SDC-02**: T-day 累积 — 自 T-day 逐日累积真实竞价列 (auction_volume/amount/price, 多 num_trades 元数据); DATA-06 派生输入 (unmatched_volume/virtual_price) 语义经 probe 确认后映射 (不猜测)。
- [ ] **SDC-03**: 诚实门 — 采集失败 fail-closed (当日无数据 → 无当日分区, 不伪造); sidecar 状态可观测 (台账/告警, 09:26 后缺失可告)。

### 部署日执行面 (Deploy-Day Execution) — Phase 44

- [ ] **DEP-01**: 凭证/连通性前置 — stockdb key 配置 + 容器内连通性验证 (127.0.0.1:8000 loopback 不通 → host 网络或网关方案, 实测判定); 3018 容器对齐检查 (4 运行时文件 md5 vs HEAD)。
- [ ] **DEP-02**: 新端点 200-body 验证脚本 — 3 新端点 (backfill/validation/backtest) auth-gated 200-body 脚本化 (login cookie → 请求 → body 形状断言, 不再只验 401 门)。
- [ ] **DEP-03**: D1..D8 runbook 脚本化 — 观测窗口每项可执行 (09:26 premarket / 15:30 EOD+池持久化 / 15:40 recap / D7 探针周终 / 分钟点亮门 = 15:30 后分区存在 && auction_intraday_confirm 非空, 非盘中误判)。
- [ ] **DEP-04**: 3018 rebuild 对齐 — 重建配方落地 (预检验证 build 66s + boot 18s) + 数据卷/权限检查 (root-owned 修复) + 旧容器替换流程文档化。

## Future Requirements (Deferred)

- **FA-04 全量竞价回填解锁**: 历史逐笔不可得 (stockdb 无竞价端点, tick 无历史) — 依赖 T-day sidecar 逐日累积或分钟统计口径; 配额窗 campaign 纪律保持 fallback。
- **RC-02 ≥0.94 真列重跑**: 随 FA-04 解锁; 当前统计口径路径先行。
- **竞价窗口 sidecar 正式化**: SDC-01/02 若 P2 验证成功 (连续交易日累积), 升级为常驻通道。
- **DATA-06 真实输入映射**: unmatched_volume/virtual_price 真实语义经 stockdb T-day 数据 probe 后物化。

## Out of Scope

- **进程内 import stockdb SDK**: PEP 695 需 Python ≥3.12 (AQ 运行时 3.11) — HTTP 适配器替代, 除非单独升级运行时 (另立里程碑)。
- **09:15-09:24 委托统计入 canonical 竞价湖**: 虚拟匹配量非成交 (研究 P1 anti-feature 明示)。
- **宣称 stockdb 解锁全量历史竞价逐笔回填**: 实测不可得, 诚实标注统计口径。
- **自动下单/执行权**: 平台边界延续 (选股/股池/研究 = 零执行权)。
- **`frontend/src/pages/Watchlist.tsx` 任何触碰**: 用户文件, 全程零改动。
- **上游 xyz MCP 配额的进一步逆向**: 实测充分 (首窗~70→403, 恢复余量~13), 不再投入。

## Traceability

| REQ-ID | Phase | Status |
|--------|-------|--------|
| LOCAL-01 | Phase 40 | Complete |
| LOCAL-02 | Phase 40 | Complete |
| LOCAL-03 | Phase 40 | Complete |
| LOCAL-04 | Phase 40 | Complete |
| HON-01 | Phase 41 | Complete |
| HON-02 | Phase 41 | Complete |
| MIN-01 | Phase 42 | Planned |
| MIN-02 | Phase 42 | Planned |
| MIN-03 | Phase 42 | Planned |
| SDC-01 | Phase 43 | Planned |
| SDC-02 | Phase 43 | Planned |
| SDC-03 | Phase 43 | Planned |
| DEP-01 | Phase 44 | Planned |
| DEP-02 | Phase 44 | Planned |
| DEP-03 | Phase 44 | Planned |
| DEP-04 | Phase 44 | Planned |
