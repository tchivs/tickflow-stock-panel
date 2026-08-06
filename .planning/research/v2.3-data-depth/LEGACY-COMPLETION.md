# 领域 C 研究：遗留 P2 补全 + 部署验证清单 (Legacy P2 Completion + Deploy Verification)

**Researched:** 2026-08-06（只读研究；唯一写盘 = 本文件 + DEPLOY-CHECKLIST.md）
**Domain:** WATCH-04 / CHART-04 / R13 / OQ-3 / 部署验证清单
**Confidence:** HIGH（全部结论基于本会话实读代码 file:line；仅外部实时竞价源与真实交易日行为标 [INFERENCE]）
**Companion:** `.planning/research/v2.3-data-depth/DEPLOY-CHECKLIST.md`（合并清单）

---

## 0. 结论速览（per-item verdict）

| Item | Verdict | 一句话 |
|------|---------|--------|
| WATCH-04 批量加自选 | **CLOSED（已交付）**；「按行勾选批量」扩展 = IN（可选） | phase 25 已交付并 11/11 验证；选择型批量是纯前端+e2e 扩展，sandbox 可验证 |
| CHART-04 虚拟成交列 | **OUT**（外部实时竞价源 gate）+ DOCS（立场存档） | 诚实「估算」标注已上线；实时列数据阻塞在外部源，v2.3 只做立场决策 |
| R13 15:30 缓存刷新 | **IN**（确定性回归测试）+ 部署日确认项 | 代码已修复（ce5c705 2026-07-01，finally refresh_cache）；补一条 sandbox 确定性测试钉死语义 |
| OQ-3 概念 drift 探针 | **IN**（脚本机制 sandbox 可跑一次）+ OUT（一周报告部署观察） | 脚本离线 capture 路径可直接跑；逐日 diff 报告需 ≥5 真实交易日 |
| 部署验证清单 | **DOCS**（本领域交付物本体） | 见 DEPLOY-CHECKLIST.md |

---

## 1. WATCH-04 批量加自选（v2.1 P2）

### 1.1 现状：已交付，非遗留

- 审计结论：`.planning/milestones/v2.1-MILESTONE-AUDIT.md:24` — "WATCH-04 批量加自选为 P2 已交付; 服务端 is_watched 投影因 POOL-03 AST 守卫(执行族 token 含 watchlist)不可做 — 纯前端 join 为唯一合规路径"。
- 验证报告：`.planning/milestones/v2.1-phases/25-watchlist-sync/25-VERIFICATION.md` — status passed，11/11 must-haves；WATCH-04 证据 `PoolHubPage.tsx:80-96`（handleBatchAdd scope=filteredRows）+ `:196-210`（批量按钮+toast）+ e2e WATCH-04 PASSED（POST body 集合比较 = {300750.SZ, 600519.SH} + toast）。
- 当前代码（本会话复核）：
  - `frontend/src/pages/PoolHubPage.tsx:112-114` — `handleBatchAdd` scope = 可见行 `filteredRows.map(r => r.symbol)`（display_limit 内，绝不按 total）。
  - `frontend/src/pages/PoolHubPage.tsx:309-320` — 批量按钮「批量加自选」，仅 VIP 且 `!watchlistOnly` 渲染（D6：开关开启时可见行全在自选 → 隐藏，语义最诚实）；aria-label 已登记。
  - `frontend/src/components/pool-hub/StockListTable.tsx:354,384-385` — 星标按钮 `watchlistSet.has(row.symbol)` 全等 join + aria-label 移出自选/加入自选。
  - 后端端点：`backend/app/api/watchlist.py:35-40` — `POST /api/watchlist/batch` 逐 symbol `watchlist.add`（幂等去重 `watchlist.py:37-52`）。
  - e2e：`frontend/e2e/pool-hub.spec.ts:1237-1254` WATCH-04 用例 + `:628` ALLOWED_RE 白名单含 4 新控件名 + `:658-662` no-mutating 语义放宽（非 watchlist 写仍为零）。
- `frontend/src/pages/Watchlist.tsx` 用户未提交改动全程零触碰（25-VERIFICATION 守卫审计：`git log` 最近提交 9c6c1fc 在 phase-25 之前；当前 `git status` 仍 ` M`，未动）。

### 1.2 「从池表选择批量加自选」需要什么（若 v2.3 想做选择型扩展）

已交付 = **一键加全部可见行**。若需求升级为**按行勾选 + 批量加选中行**（表格选择型），增量：

1. `StockListTable.tsx`：VIP 代码单元格加 checkbox（每行 `aria-label=选择{code}`）+ 表头「全选当前可见行」checkbox；新增 props（selection Set + 回调 + 批量按钮 disabled 态）。
2. `PoolHubPage.tsx`：selection state（`Set<string>`）；批量按钮 scope = 选中行（空选 → disabled + 文案「已选择 0 只」或隐藏）；与 watchlistOnly 交互（选中行全在自选 → 同样隐藏/禁用）；切日期/切策略时清空或保留（建议清空，语义最诚实）。
3. e2e 守卫同步（必踩）：`pool-hub.spec.ts:628` ALLOWED_RE 白名单必须登记新控件可访问名（P1）；guest 零控件断言不变；快照更新（VIP 表格区含 checkbox，参照 25 快照先例）。
4. 零后端改动：`POST /api/watchlist/batch` 已存在且幂等，body 上限由 display_limit ≤200 天然约束（`StrategySettingsDialog.tsx:390` min=10 max=200）。

**Sandbox 可验证？** 是——与已交付 WATCH-04 完全同构：installShell mock（`pool-hub.spec.ts:305-308`）+ 请求捕获断言 POST body。规模 ~纯前端 + e2e，1-2 个执行任务。

**Scope 建议**：非 v2.3 P1（已交付版已覆盖 95% 用户价值）；若要纳入，标 P2 可选。

---

## 2. CHART-04 虚拟成交列（v2.1 P2）

### 2.1 当时 defer 的原因（v2.1 审计 + phase 26 研究）

- `.planning/milestones/v2.1-MILESTONE-AUDIT.md:21` — "CHART-04 虚拟成交实时列 defer(阻塞外部实时竞价源); 历史撮合价格曲线 defer(湖无价格列)"。
- `26-RESEARCH.md` §1.7（OQ-1）— 外部实时竞价源不可得：内置源链无 `auction` 数据集（`backend/app/tickflow/chain.py:20-26`）；`ProviderCapabilities.auction: bool = False` 默认（`backend/app/data_providers/base.py:19-26`）；仅自定义源配置 auction 数据集才可能 probe available（`custom/config.py:10` / `custom/loader.py:353-357`）。判定条件已写：源返回窗口内行且含 `auction_unmatched_volume` + `auction_virtual_price` → 可行，否则正式 defer。
- 「实时」= 连续竞价实时行情无竞价字段；盘中实时虚拟成交列还需 live 竞价流，gate 更深。

### 2.2 现状：诚实标注已上线（无需再补代码）

- 派生链路：`backend/app/services/auction_columns.py:17-19`（三常量）+ `:100-106`（compute_auction_unmatched_amount = 虚拟未匹配量 × 虚拟参考价）+ `:123-124`（两输入列在分区才派生）。湖空（0 分区）→ 列永不出现，诚实缺列。
- UI 标注已「估算」化：
  - `frontend/src/components/pool-hub/StockListTable.tsx:321` — 组头「派生 · 虚拟成交」；`:319` title "由竞价量与历史均量、委托量输入派生的估算值，非真实成交。"；`:335` 「虚拟未匹配金额（元·估算）」 title "虚拟未匹配量 × 虚拟参考价的估算值，非真实成交金额。"。
  - `frontend/src/lib/api.ts:741-742` — `auction_unmatched_amount` 注释「元·估算, 派生」。
  - 池钻取存在性声明 `auction_columns:{real,derived}`（`backend/app/services/pool_hub.py:114-121,183-186`），列渲染完全由服务端声明驱动，前端零推导（PIT-3）。
  - 湖 schema 描述带估算标注先例：`backend/app/api/pipeline.py:178` 「估算, 非真实成交」。

### 2.3 v2.3 立场决策（三选一）

| 选项 | 评估 |
|------|------|
| a. 诚实标注（现状） | **已交付**，无需代码。任何新 UI 若混排派生列必须沿用「估算」标注纪律（`api.ts:741-742` 先例）。 |
| b. 默认关 toggle（派生组可选展开） | 小前端改动（storage.kv UI 偏好 + 默认折叠「派生 · 虚拟成交」组），e2e 可测；但湖空时组永不渲染 → 现值≈0。可选 IN，非 P1。 |
| c. 保持 defer + 立场存档 | 推荐：在 REQUIREMENTS/roadmap 记明 CHART-04 = 实时虚拟成交列，re-eval gate = 外部实时竞价源可得（OQ-1 判定条件）；与 tier-2 盘前真实竞价列共享同一 gate（v2.1 audit:82）。 |

**Scope 建议**：v2.3 取 c（DOCS 存档 + 明确 re-eval gate）；b 仅当有用户明确诉求再做。

---

## 3. R13（v2.2 audit：15:30 管道是否刷新 repo latest-day enriched 缓存）

### 3.1 代码事实：已修复（早于 v2.2 审计）

- `backend/app/jobs/daily_pipeline.py:1115-1136` — `_pipeline_then_refresh`（调度 cron 路径）：`:1128/:1130` 调 `run_now` → **`:1135` `repo.refresh_cache()` 置于 `finally`**（部分成功也刷缓存；异常继续上抛由 `_run_tracked` 标记 failed）。注释 `:1116-1118` 明示 "仅手动触发或重启才会刷缓存, cron 调度路径此前漏了这步"。
- git blame：`ce5c705`（2026-07-01）引入，`9aa96ed`（2026-07-08）改 finally + 成功也生效，`ddde2b9`（2026-07-09）加 `qs.paused()` 防管道运行期间实时行情覆写 parquet 竞态（`:1123-1128`）。
- 结论：**15:30 调度管道运行后必然刷新 Polars 内存缓存**（`repository.py:351` refresh_cache；`_refresh_enriched` 从 parquet 加载最新日 `repository.py:461-577`）。v2.2 审计的 [INFERENCE]（v2.2-MILESTONE-AUDIT.md:18）现可代码级钉死为已缓解。

### 3.2 15:40 复盘读路径

- `backend/app/services/auction_recap.py:524-530` — `ScreenerService(repo)._load_enriched_for_date(as_of)` 单次装载（Block 2 + Block 3 同帧复用）。
- `backend/app/services/screener.py:245-254` — 优先 repo 最新日缓存：`get_enriched_latest_asset`（`repository.py:920-935`），`cache_date == target_date` → 直接用内存帧。
- pre-EOD 规则：`auction_recap.py:339-346`（as_of==today ∧ now < `get_pipeline_schedule()` 默认 15:30，`preferences.py:329-332`）→ Block 3 change_pct/close 统计省略 + `_SIGNAL_NOTE_EOD_PENDING` 注记（`:393-396` + resonance `:467-470`）。
- 时序：15:30 管道（paused quote → run_now 落盘 EOD enriched → finally refresh_cache）→ 15:40 复盘读缓存 = **EOD 终值**（close 15:00 已定盘，15:30-15:40 无盘中覆写）。R13 语义链完整。

### 3.3 Sandbox 可验证性：IN（确定性测试）

可写确定性回归测试（fixture 数据，无网络）：
1. 配方测试：`run_now`（或最小等价：写今日 enriched 分区）+ `repo.refresh_cache()` → `get_enriched_latest_asset("stock")` 返回 `cache_date == T` 且 close = EOD 终值（非盘中帧）。
2. 语义测试：`build_auction_recap` 注入 now=15:40（> 调度）+ 缓存含 T EOD 帧 → Block 3 `avg_change_pct`/`close_fulfill_rate` 从 EOD 值计算；注入 now=15:10（< 调度）→ 同帧统计省略 + `pre_eod` 头标签（31-01-PLAN.md:120 已有 pre_eod 判别测试先例，扩展到「15:30 后 EOD 缓存语义」）。
3. 真实交易日部署确认（OUT 部分）：复盘面板 `avg_change_pct` 与手动按 enriched 分区算的 EOD change_pct 一致（入 DEPLOY-CHECKLIST 第 8 项）。

### 3.4 OQ-3 drift 探针（`backend/scripts/probe_concept_drift.py`）

- 脚本性质：manual-only operator 脚本（docstring "manual-only, operator 部署后跑"）；用法 `python scripts/probe_concept_drift.py [YYYY-MM-DD] [--upstream]`。
- 离线路径 `capture()`：读当前 `ext_gn_ths`/`ext_hy_ths` 快照 → 前向归档 `ext_history/{kind}/date={as_of}/part.parquet`（`concept_history.py:171-174`）+ `_probe/drift.jsonl` 追加每 kind 一行（sha256/rows/effective_date）；`--upstream` 走 `capture_from_upstream`（独立同步 httpx 测量上游 `:217-224`）。零副作用于 ext_data 当前快照/strategy_cache/screener_results。
- **Sandbox 可跑**：ext_data 快照存在（ext_gn_ths 260KB/5542 行）→ 离线 capture 一次可产生诚实单日记录，验证脚本机制（IN smoke）。但「一周逐日 diff + 去重哈希 + 概念增删样本」需 ≥5 真实交易日连续运行（v2.2 audit:28 "OQ-3 一周逐日 diff 探针部署后跑"）→ 周终报告为部署观察项（OUT）。
- 部署观察点：ext_history 首个真实 EOD 捕获会创建该目录（数据湖 reality：`data/ext_history/` MISSING，首次 capture 创建）→ 清单需确认目录创建 + drift.jsonl 逐日累加 + 周报告无意外哈希漂移；上游 concepts.json 更新节奏未知（effective_date 暴露 + 探针校准，audit:29）。

---

## 4. 部署验证清单（交付物二）

全部累计真实交易日验证项合并见 `DEPLOY-CHECKLIST.md`。来源：
- v2.1 audit open items（`.planning/milestones/v2.1-MILESTONE-AUDIT.md:81-83`）：真实 09:26 cron 触发；tier-2 盘前真实竞价列 gate；CHART-04 gate。
- v2.2 audit tech_debt（`.planning/milestones/v2.2-MILESTONE-AUDIT.md:83-86`）：09:26 盘前监控 + 15:40 复盘 + LLM 点评部署确认；kline_auction 空湖 → 真列分支验证 + BT-07 gate；OQ-3 一周 diff；R13 语义验证；tier-2 gate 延续。
- Phase 30 UAT-1（30-UAT.md:16-27）：09:26 实盘调度 + 投递。
- Phase 31 UAT-1/2（31-UAT.md:16-34）：15:40 定时复盘渲染 + LLM 点评 live-model。
- Phase 27 盘前预览（v2.1 audit:53）：premarket_results/date={T}/part.json 落盘观察。
- 盘后管道调度默认 15:30（`preferences.py:329-332`）+ 15:35 EOD 股池持久化（daily_pipeline.py:1154-1162）+ 15:40 复盘默认（`preferences.py:434-444`）。

---

## 5. v2.3 领域建议（scope 推荐）

1. **R13 确定性回归测试（IN，P1 建议）**：钉死「调度管道后 repo 缓存 = EOD 终值」配方 + 复盘 EOD 语义（§3.3）。这是本领域唯一有真实代码价值的 sandbox 动作——把 v2.2 audit 的 [INFERENCE] 转成回归锁。
2. **部署验证清单（DOCS，本领域核心交付）**：DEPLOY-CHECKLIST.md 作为 v2.3 完成后部署操作手册。
3. **CHART-04 立场存档（DOCS，P1 轻量）**：需求/roadmap 记明 re-eval gate（外部实时竞价源 + 两输入列），与 tier-2 共享 gate；诚实标注已交付无需代码。
4. **WATCH-04 选择型批量（IN，P2 可选）**：仅在明确产品诉求时做（§1.2 清单）。
5. **OQ-3 探针机制 smoke（IN，P2 可选）**：sandbox 离线跑一次验证 drift.jsonl 落盘机制；周报告本身部署观察。

**不建议**：为 CHART-04 做默认关 toggle（湖空时零价值）；任何服务端 is_watched 投影（POOL-03 守卫锁死，`test_pool_hub.py:857-902`）；批量回填 job（OQ-1 立场：回填 job 仍绝无回填，v2.1 audit:27）。

---

## 6. 证据索引（本会话实读）

| 证据 | file:line |
|------|-----------|
| WATCH-04 已交付审计 | .planning/milestones/v2.1-MILESTONE-AUDIT.md:24 |
| WATCH-04 验证 11/11 | .planning/milestones/v2.1-phases/25-watchlist-sync/25-VERIFICATION.md |
| handleBatchAdd scope=filteredRows | frontend/src/pages/PoolHubPage.tsx:112-114 |
| 批量按钮 + watchlistOnly 隐藏 | frontend/src/pages/PoolHubPage.tsx:309-320 |
| 星标 + aria-label | frontend/src/components/pool-hub/StockListTable.tsx:354,384-385 |
| batch 端点幂等 | backend/app/api/watchlist.py:35-40 |
| e2e WATCH-04 + ALLOWED_RE | frontend/e2e/pool-hub.spec.ts:1237-1254,628,658-662 |
| CHART-04 defer | .planning/milestones/v2.1-MILESTONE-AUDIT.md:21; 26-RESEARCH.md §1.7/OQ-1 |
| 派生列常量+计算+闸门 | backend/app/services/auction_columns.py:17-19,100-106,123-124 |
| UI 估算标注 | frontend/src/components/pool-hub/StockListTable.tsx:319,321,335; frontend/src/lib/api.ts:741-742 |
| 存在性声明 | backend/app/services/pool_hub.py:114-121,183-186 |
| R13 修复（finally refresh_cache） | backend/app/jobs/daily_pipeline.py:1115-1136（blame: ce5c705/9aa96ed/ddde2b9） |
| 复盘读缓存路径 | backend/app/services/auction_recap.py:524-530; backend/app/services/screener.py:245-254; repository.py:920-935 |
| pre-EOD 规则 | backend/app/services/auction_recap.py:339-346,393-396,467-470 |
| 管道调度默认 15:30 | backend/app/services/preferences.py:329-332 |
| 复盘调度默认 15:40 | backend/app/services/preferences.py:434-444 |
| probe 端点 | backend/app/api/data.py:626-640 |
| OQ-3 探针离线路径 | backend/scripts/probe_concept_drift.py; backend/app/services/concept_history.py:171-174,217-224 |
| v2.2 deploy 项 | .planning/milestones/v2.2-MILESTONE-AUDIT.md:83-86; 30-UAT.md:16-27; 31-UAT.md:16-34 |
| POOL-03 守卫锁死服务端投影 | backend/tests/test_pool_hub.py:857-902 |
