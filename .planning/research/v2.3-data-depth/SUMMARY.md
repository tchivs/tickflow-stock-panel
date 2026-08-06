# v2.3 数据纵深解锁 — Research Synthesis (SUMMARY)

**Synthesized:** 2026-08-06
**Research basis:** `.planning/research/v2.3-data-depth/` — AUCTION-BACKFILL.md (6m1s, PARTIAL), POOL-BACKFILL.md (4m33s, IN/PARTIAL), LEGACY-COMPLETION.md + DEPLOY-CHECKLIST.md (4m54s, IN/DOCS)
**Scope ruling:** 3/3 域全 IN(部分条件式),4 phases (32-35),MEDIUM-HIGH
**Honesty posture:** 延续 — 湖空诚实空态、probe fail-closed、列缺席不填、零新增运行时依赖、POOL-03 零执行权、Watchlist.tsx 零触碰

---

## 领域裁决

### A. 竞价/分钟历史可达性 — 竞价 OPEN(实测), 分钟 CLOSED

| 事实 | 证据 |
|------|------|
| xyz MCP `http://8.138.149.215:7898/mcp` 暴露 `stockdb_get_call_auction`:单 symbol 单请求取满 248 交易日(2025-07-29..2026-08-05)09:25:00 最终撮合行,1.6s/请求 | probe #6 (248 行全命中) |
| 数据真伪:上游 `current` 与本地 `kline_daily` open 三日期逐值相等 (11.41=11.41 / 12.30=12.30 / 11.19=11.19) — 真实交易所集合竞价 | AUCTION-BACKFILL.md §4 交叉验证 |
| 单请求强制 1 symbol(带宽限制:批量 3 码报错);2010 至今声明,2024-01-02 抽验通过;无鉴权头 | probe #7/#5 |
| 分钟历史 CLOSED:xyz 1m 仅 ~21 交易日 (2026-07-07..08-04);ifzq/sina 尾随窗口;TickFlow minute 需 pro+(当前 key=Free);现有 `sync_and_persist_minute` (≤30 天偏好) 即可达上限 | AUCTION-BACKFILL.md §3 |
| 全仓库无 provider 声明 `auction=True`(base.py:19-26 字段存在未用);`chain.py _BUILTIN_CHAIN` 无 auction 键;`data/data_sources/` 空 → probe 恒 fail-closed | AUCTION-BACKFILL.md §2 |
| schema 映射:code→symbol(补 .SZ/.SH)、time→datetime、volume→auction_volume、money→auction_amount、current→auction_virtual_price;**auction_unmatched_volume 上游无 → 列缺席诚实处理** | AUCTION-BACKFILL.md §6 表 |

**裁决:IN — Phase 32 竞价历史回填。** 主链路:kline_auction 湖从 0 分区回填至与 kline_daily 对齐 (248 交易日 × 全市场,单 symbol 串行 ~1.6s/请求,限速);解锁 BT-07 全量回测 gate (v2.2-REQUIREMENTS.md:60) + 29 真列分支 + 31 真实竞价活跃度。分钟回填正式 defer (记录关闭理由)。`auction_unmatched_volume` 真实列 defer (上游无字段)。

### B. 股池历史回填 (OQ-1) — IN, 沙箱子集 + 部署全量

| 事实 | 证据 |
|------|------|
| OQ-1 = 回填 job 已建、从未执行 (Phase 24 交付 HIST-01..04 全链路;screener_results 仍 0 分区,磁盘实测 248 enriched / 0 快照) | POOL-BACKFILL.md;v2.1-MILESTONE-AUDIT.md:27 |
| 回填入口已存在:`POST /api/pipeline/backfill` (api/pipeline.py:90, 单飞/执行槽/后台, max_days 1..500) → `run_pool_backfill` (pool_backfill.py:30: 缺口集/升序/取消/失败继续/绝不 write_cache) → `persist_point_snapshot(origin='backfill')` | POOL-BACKFILL.md evidence |
| 沙箱确定性可行:run_all_with_hits 读 enriched + 启动预计算缓存 + 默认参数;竞价湖空 → requires_auction_data 短路 fail-closed;幂等重跑;248 日 ≈ 20-120min / 79-693MiB [INFERENCE] | POOL-BACKFILL.md |
| POOL-03 交织:回填属 operator 执行面(端点只在 api/pipeline.py E4、不 import 执行族 E1/E3、只写 screener_results E2) — 结构性合规,无需 token | POOL-BACKFILL.md |
| premarket_results MISSING = 部署门禁 + 实时数据依赖(唯一创建方 09:26 job,非 fixture_mode 才调度;手动调因无今日 enriched → available:false) — 无沙箱确定性路径,诚实 OUT | POOL-BACKFILL.md |
| PIT:读侧 as_of 分区解析已就绪 (pool_hub.py read_partition);ext_history 仅真实 EOD 前向创建;上游无历史 → 存量日诚实 current_snapshot 回退 | POOL-BACKFILL.md |

**裁决:IN — Phase 33 股池回填 OQ-1。** 沙箱子集 5-10 日验证 (origin=backfill + cache byte-identical + /pool/history 渲染 + 幂等) 为 in-sandbox 验收;全量 248 为部署后 operator 指引。premarket 模拟 OUT (诚实缺口)。

### C. 遗留 P2 + 部署验证 — IN (R13 测试) + DOCS

| 事实 | 证据 |
|------|------|
| WATCH-04 批量加自选:**v2.1 已交付**(audit :24,PoolHubPage.tsx:112-114/:309-320);扩展 = 行勾选 + selection Set + ALLOWED_RE 注册 (纯前端 + e2e) — 可选 P2 | LEGACY-COMPLETION.md |
| CHART-04 估算标注**已上线**(StockListTable.tsx:319,321,335 + api.ts:741-742;派生列门控 auction_columns.py:123-124) — 剩立场文档 + 再评估门 | LEGACY-COMPLETION.md |
| **R13 代码早已修复**:daily_pipeline.py:1135 `refresh_cache()` in finally (blame ce5c705 2026-07-01) — v2.2 审计的 [INFERENCE] 已过时;剩 = 确定性回归测试 + 部署确认 | LEGACY-COMPLETION.md |
| OQ-3 探针:offline capture 路径沙箱可跑 (concept_history.py:171-174);周报需 ≥5 真实交易日 — smoke IN / 周报 OUT | LEGACY-COMPLETION.md |
| 部署验证:8 项清单成册 (D1 09:26 premarket cron、D2 15:30 EOD+cache+15:35 persist、D3 tier-2 真实竞价列、D4 09:26 monitor payload、D5 15:40 recap+LLM、D6 R13、D7 OQ-3、D8 stance) — DOCS | DEPLOY-CHECKLIST.md |

**裁决:IN + DOCS — Phase 35 遗留补全与部署验证。** R13 回归测试 (P1);CHART-04 立场文档 (P1);部署验证清单 (P1);WATCH-04 批量扩展 (P2);OQ-3 smoke (P2)。

---

## v2.3 范围定案

| Phase | 主题 | 域 | 主要交付 |
|-------|------|----|----------|
| 32 | 竞价历史回填 | A | xyz auction capability + `auction_backfill.py` job + POST 端点 + 诚实闸门 + 幂等原子写 + 限速取消;分钟回填 defer 声明 |
| 33 | 股池回填 OQ-1 | B | 沙箱子集回填验证 + 全量 operator runbook + PIT 归属联动 + premarket 诚实缺口 |
| 34 | 竞价回测解锁 BT-07 | A | 真列验证报告激活 + 248 日全量回测 (9 策略, real/derived/eod) + backtest_results 持久化 |
| 35 | 遗留补全与部署验证 | C | R13 回归测试 + CHART-04 立场 + 部署验证清单 8 项 + WATCH-04 批量 (P2) + OQ-3 smoke (P2) |

**决策记录:**
- D1:竞价回填源 = xyz MCP(唯一实测有 2010-至今历史竞价);回填闸门 = 只写 kline_daily 已存在日期分区(对齐诚实)
- D2:分钟回填 defer — 源实测不可达 248 天;`sync_and_persist_minute` 维持 ≤30 天增量
- D3:BT-07 gate 解锁条件 = Phase 32 湖对齐;Phase 34 依赖 Phase 32 完成
- D4:OQ-1 验收口径 = 「screener_results 覆盖 enriched 全缺口」(沙箱子集验证 + 部署全量执行)
- D5:R13 由 [INFERENCE] 转为已修复事实,交付 = 回归测试 + 部署确认项 (D6)
- D6:WATCH-04/CHART-04 主体 v2.1 已交付;本期只做扩展 (P2) 与立场文档

**Unchanged:** 用户 `frontend/src/pages/Watchlist.tsx` 零触碰;零新增运行时依赖;POOL-03 零执行权;诚实 provenance (origin=backfill / data_gate / 列缺席不填)。
