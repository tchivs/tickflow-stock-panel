# 自选股联动(POOL-05 v2.1 / WATCH-01)研究

**领域:** 自选股与股池交叉高亮/过滤(自选清单本地持有一致)
**研究者:** ResearcherWatchlist
**日期:** 2026-08-06
**总体置信度:** HIGH(全部结论均基于仓库实读代码 + 本地数据实测;仅外部/语义性判断标 [INFERENCE])

---

## 现状(代码证据)

### 1. 自选能力已完整存在,且服务端是唯一事实来源(非 SQLite、非 localStorage)

- **存储 = Parquet**:`backend/app/services/watchlist.py:21-24` — `data/user_data/watchlist.parquet`,字段 `symbol` + `added_at` + `note`。实测该文件(2 行):`600664.SH` / `001258.SZ`,**全后缀 symbol 格式**。
- **服务层**:`watchlist.py` `list_symbols()/add()/remove()/move_to_top()/clear()/fetch_quotes()`;`add()` 已幂等去重(先删同 symbol 再插头部,`:37-52`)。
- **API**:`backend/app/api/watchlist.py` — `GET /api/watchlist`(`:45`)、`POST /api/watchlist`(`:49`)、`POST /api/watchlist/batch`(`:54`)、`POST /{symbol}/top`(`:62`)、`DELETE /{symbol}`(`:68`)、`DELETE /api/watchlist`(`:74`)、`GET /api/watchlist/enriched`(`:105`)。路由已注册:`backend/app/main.py:847 app.include_router(watchlist.router)`。
- **前端 API 客户端**:`frontend/src/lib/api.ts:2025-2051`(watchlistList/Add/BatchAdd/Remove/MoveToTop/Clear/Quotes/Enriched);查询键 `frontend/src/lib/queryKeys.ts:25-28`(`QK.watchlist` / `watchlistEnriched` / …)。
- **自选页**:`frontend/src/pages/Watchlist.tsx` 存在(**用户有未提交改动 — 本次仅按结构引用,不读内容、不修改、不提交**);自选页与策略页共享表格骨架 `components/stock-table/StockDataTable.tsx` 与列配置 `lib/watchlist-columns.ts`。
- **localStorage 只存 UI 偏好,绝不存自选清单**:`frontend/src/lib/storage.ts:39-52` — `watchlistColumns` / `watchlistView` / `watchlistCandle` / `watchlistIntraday` / `watchlistBoardFilter` 全是视图偏好,不是 symbol 列表。

### 2. 服务端已把「自选」当一级池消费(这是不能引入第二套自选清单的根本原因)

- `backend/app/tickflow/pools.py:22` — `PoolId` 字面量含 `"watchlist"`;`:57-58` `if pool_id == "watchlist": return _load_watchlist()`(读取同一份 `watchlist.parquet`)。
- `backend/app/jobs/daily_pipeline.py:154-156` 与 `backend/app/services/extend_history.py:55-56` — Free 用户拉数兜底 `base.update(get_pool("watchlist"))`。
- `backend/app/services/quote_service.py:903-910` — Free 档自选实时监控(前 5 只)直接读 `watchlist.list_symbols()`。
- 结论:自选清单被 选股/实时/盘后管道/TickFlow 池 四处服务端消费。**localStorage 方案会让这四处全部与前端自选脱节。**

### 3. 股池行字段与匹配键

- `backend/app/services/pool_hub.py:121-137`(`_project_hub`):每行投影 `symbol`(全后缀,直接取自结果行 `row["symbol"]`)、`code` = `symbol.split(".", 1)[0]`(`:129`)、`name` / `open_gap` / `change_pct` / `concept_board` / `hit_factors` / `cross_resonance` + 竞价列透传。
- 实测 `data/user_data/strategy_cache.json`:`boll_breakout` 179 行,`symbol='603221.SH'`。与自选 parquet 的 `600664.SH` **同格式** → **匹配键 = 全后缀 symbol,已天然一致,前端可直接 `Set.has(row.symbol)` 精确 join**。
- 历史视图 `GET /api/pool/history` 与最新 `/api/pool/hub` 共享同一 `_project_hub`(`pool_hub.py` docstring;`api/pool.py:80-95`),行形状 bit-identical — 联动逻辑对最新/历史天然同构。

### 4. 游客/认证语义(联动对 guest 无意义,且 guest 面被测试锁死)

- `backend/app/main.py:778-788` — 游客可读面恰好 4 个只读 GET:`/api/pool/hub`、`/api/screener/strategies`、`/api/pool/dates`、`/api/pool/history`。**`/api/watchlist` 不在内 → guest 访问自选 API 一律 401**(`:831-840` 中间件)。
- `backend/app/services/guest_masking.py:47-55` — 游客行 `code/name/symbol` 全部替换为 `******`;`api/pool.py:42-47`(hub)与 `:92-98`(history)按 `reviewer_principal` 有无派生 `mode: guest|vip` 并施掩码。
- `backend/tests/test_guest_masking.py` — T-19-03 守卫锁死游客面(恰好 4 路径、GET-only、无 6 位代码泄露);`test_pool_hub.py:788-791,826-833` POOL-03 AST 守卫锁死 pool 特性不得 import 执行族模块。
- **前端 401 会跳登录**:`frontend/src/main.tsx:22-27` — QueryCache/MutationCache `onError` 收到 401 → `window.location.href = '/login?...'`。因此 **股池页在 guest 模式绝不能发起 `QK.watchlist` 查询**,必须按 `mode==='vip'` 门控。
- 结论:自选联动是 **VIP(已登录)专属能力**;guest 保持现状(掩码 + 横幅),不渲染任何自选控件。

### 5. 前端已存在完全相同的联动先例(策略页)— 直接可抄

- `frontend/src/pages/Screener.tsx:429-447` — `useQuery(QK.watchlist)` → `watchlistSet = new Set(symbols.map(s => s.symbol))` → 传入表格;toggle 用 `api.watchlistAdd/Remove` mutation,成功即 `invalidateQueries(QK.watchlist)`。
- `frontend/src/components/screener/ScreenerTable.tsx:24-28,166-210` — symbol 列内星标按钮(在自选中 `Check` 实心 / 不在 `Plus` 空心),`disabled` 于 pending。
- `frontend/src/lib/useSharedMutations.ts:32-41` — `useWatchlistBatchAdd`(Screener/Intraday 共用,批量加自选)。
- 跨页一致性机制已存在:`QK.watchlist` 是全局共享缓存,自选页/策略页/个股弹窗(`StockPreviewDialog.tsx:47-60`)任一增删都失效同一 key → 股池页复用同一 key 即自动一致。

---

## 候选方案对比

| 方案 | 工作量 | 风险 | 与现有架构契合 |
|---|---|---|---|
| **(a) 纯前端 localStorage 自选 + 前端 join** | 低(前端) | **高**:与服务端 `watchlist.parquet` 分裂双源;自选页/实时监控/自选池(`pools.py`)/盘后兜底(`daily_pipeline.py`)/extend_history 全部读服务端清单 → 两套自选互相漂移;跨设备/清浏览器丢失;违反「单一事实来源」 | **低**:与现有服务端自选体系根本冲突,等于另起炉灶 |
| **(b) 后端自选 CRUD + hub 投影标注 `is_watched`** | 中(后端投影 + 前端消费) | **高**:`tests/test_pool_hub.py:788-791` 的 POOL-03 AST 守卫 `_EXECUTION_TOKEN` **含 `watchlist`**,`pool_hub.py/pool.py/pool_snapshot.py` 任何 `import watchlist` 直接红;须显式改守卫(削弱锁定的安全边界)或另设不在 pool 特性的 annotate 端点;guest 掩码还要同步剥离 `is_watched`;纯展示关注点换取服务端耦合 | **中低**:投影核心 `_project_hub` 是纯函数,塞入自选集合会破坏其「无外部状态」契约;且历史/最新同旗语义需新定义 |
| **(c) 现有服务端 watchlist API + 前端 join(共享 react-query 缓存)** | 低(纯前端,抄 Screener) | **低**:零后端改动、零守卫改动、零掩码改动;guest 按 `mode` 门控不触 401;`QK.watchlist` 缓存天然跨页一致 | **高**:完全复用既有自选体系;匹配键(全后缀 symbol)两端已一致;与 Screener/个股弹窗模式同构 |

---

## 推荐方案 + 理由

**推荐 (c):复用现有服务端 `watchlist.parquet` + `/api/watchlist` API,在股池前端做 join(高亮/过滤),自选集合经共享 `QK.watchlist` 缓存「本地持有一致」。**

理由:

1. **架构契合**:自选清单的唯一事实来源已是服务端 Parquet(`watchlist.py:21-24`),且被实时/池/管道多处消费。前端 join 只是「读同一份数据投影到股池表」,不产生第二份清单。
2. **风险最低**:完全避开两条锁死的测试边界 — POOL-03 执行族守卫(`test_pool_hub.py` token 含 `watchlist`)与 GUEST 游客面守卫(`test_guest_masking.py` T-19-03)。方案 (b) 必然触碰其一,方案 (a) 触碰「单一事实来源」架构不变量。
3. **工作量最小、有现成模板**:Screener.tsx 已实现一模一样的「取自选集合 → Set → 行内星标 → mutation 增删」链路,股池页照搬并加一个「只看自选」过滤开关即可。
4. **跨页一致天然成立**:`QK.watchlist` 是全局缓存;自选页/策略页/个股弹窗/股池页共用同一 key,任一增删都 `invalidateQueries(QK.watchlist)` → 股池星标/过滤即时一致,无需新同步机制。
5. **游客语义正确且零改动**:guest 面不发自选查询(避免 401 跳登录),不渲染星标/过滤,维持 GUEST-01 掩码现状;GuestModeBanner 文案是锁定的 exported 常量,本期不动。
6. **匹配键零成本**:股池行 `symbol`(全后缀)与自选 parquet `symbol` 已实测同格式,`Set.has(row.symbol)` 精确 join 即可,无需归一化。

> 「自选清单本地持有一致」按此解释:清单事实在服务端,前端经共享缓存持有一份一致投影(local consistency),而非「存到 localStorage」。[INFERENCE] 若产品意图确为「无服务端、纯浏览器清单」,则与上述四处服务端消费冲突,需另行决策 — 列入开放问题。

---

## 需求草案(可验收)

### WATCH-01:股池明细行自选星标 + 切换(VIP)

**描述:** VIP 模式下,股池钻取明细表(`StockListTable`)每行代码旁渲染自选星标:在自选中=实心高亮,不在=空心;点击调现有 `api.watchlistAdd/Remove` 增删,并失效 `QK.watchlist`。游客模式不渲染任何自选控件。

**验收标准:**
- `PoolHubPage` 在 `mode === 'vip'` 时通过 `useQuery({ queryKey: QK.watchlist, queryFn: api.watchlistList })` 获取自选集合;`mode === 'guest'` 时**不发该查询**(无 401、无登录跳转)。
- 星标判定 = `watchlistSet.has(row.symbol)` 精确全等(`PoolHubRow.symbol`,全后缀)。
- 点击星标调 `api.watchlistAdd(symbol)` / `api.watchlistRemove(symbol)`;成功即 `invalidateQueries(QK.watchlist)`(+`QK.watchlistEnriched()`,与 `useSharedMutations.ts:32-41` / `Screener.tsx:440-447` 同款);pending 期按钮 `disabled`。
- guest 会话渲染的股池表与现状逐像素一致(无星标列、无新按钮、无新文案)。

### WATCH-02:「只看自选」过滤开关(VIP)

**描述:** VIP 模式在明细表上方提供「只看自选」开关,开启后仅显示当前策略 rows 中在自选集合的行;与既有概念子串筛选(`PoolHubPage.filteredRows`)AND 组合;`total` 卡片计数保持权威全量不变(与概念筛选同语义,D-04)。

**验收标准:**
- 开关开启且当前策略自选命中 0 行 → 诚实空态「自选清单中无该策略个股」(非静默空白)。
- 开关对最新 `/api/pool/hub` 与历史 `/api/pool/history` 视图同样生效(两者行形状 bit-identical)。
- 开关状态存 `storage`(如 `poolWatchlistOnly`,与既有 UI 偏好键同型,`storage.ts` 模式),不落后端。
- guest 模式不渲染该开关。

### WATCH-03:自选集合一致性与匹配键契约

**描述:** 自选联动的前端集合必须与自选页/策略页共享同一 `QK.watchlist` 缓存,任何入口的增删都经缓存失效即时反映到股池页;匹配键固定为全后缀 symbol,精确匹配,不做大小写/后缀猜测。

**验收标准:**
- 股池页不使用独立的自选存储/独立查询键;复用 `QK.watchlist` + `api.watchlistList`。
- 在自选页删一只股、在策略页加一只股后,回到股池页(不刷新页面)星标/过滤随之更新(经 react-query 缓存,而非硬刷新)。
- join 用 `row.symbol` 全等比较;不存在「`600664` 匹配 `600664.SH`」这类模糊匹配;新增入口传 symbol 时沿用全后缀格式(搜索/策略/股池入口均已如此)。

### WATCH-04:批量加自选(可选 / 边界)

**描述:** 提供从股池批量加入自选的能力,复用现有 `POST /api/watchlist/batch`(`api.watchlistBatchAdd`);批量范围=当前策略**可见 rows**(受 `display_limit` 截断,`len(rows) ≤ total`,见 `pool_hub.py` docstring Divergence 1),**绝不**按未展开的 `total` 批量(避免一次写超限)。

**验收标准:**
- 批量按钮仅 VIP 可见;仅对 `activeStrategy.rows`(当前可见行,可选再叠加「只看自选」反向取未自选行)调用 `watchlistBatchAdd`。
- 重复加入已有 symbol 幂等(`watchlist.add` 已去重,`watchlist.py:37-52`),不产生重复行。
- 成功回调失效 `QK.watchlist` + `QK.watchlistEnriched()`。

---

## 风险与开放问题

1. **POOL-05 编号冲突**:v2.0 已 shipped 的 POOL-05 =「历史视图独立只读端点」(见 `.planning/REQUIREMENTS.md` v2.0 与 `pool.py`/`pool_hub.py` docstring),v2.1 又把「自选股联动」标为 POOL-05(PROJECT.md Target features)。v2.1 需求清单须显式区分(建议 v2.1 用 `POOL-05 = WATCH-01` 或改号),避免追溯/验证串号。
2. **Watchlist.tsx 用户未提交改动**:本方案只消费公共 API + `QK.watchlist`,与页面内部实现解耦,理论不受影响;但规划/执行前需确认用户改动未改 `QK.watchlist` 契约或引入第二套自选存储(本地 storage)。
3. **自选 symbol 未规范化**:`watchlist.add` 原样存 symbol(`watchlist.py:37-52`);若未来某入口传入无后缀 `600664`,join 会失配。当前所有入口(搜索 `instrumentSearch`、策略行 `r.symbol`、股池行 `row.symbol`)均为全后缀,故本期不引入服务端规范化;若出现裸代码入口,需先修入口而非加模糊匹配。
4. **guest 体验**:guest 面不提供自选联动(无星标/无开关),也不会把「登录后可用」塞进锁定的 GuestModeBanner 文案(UI-SPEC Copywriting Contract 锁 `BANNER_TITLE/BODY` 与 `GUEST_BANNER_ACCESSIBLE_TEXT`)。是否要在股池页另加非锁定文案的登录引导,属产品决策,本期建议不做。
5. **is_watched 服务端化(未来)**:若未来池行上万行或需要服务端过滤,再评估:独立 annotate 端点(置于 `api/watchlist.py`,不进 pool 特性)或显式修改 POOL-03 守卫 —— 均需独立决策,本期明确不做。
6. **自选与历史 as_of 语义**:星标/过滤是「当前自选清单」对任意 as_of 行的**实时标注**,不做「历史自选快照」(自选是用户偏好,非时间序列)。若产品要「某历史日我自选了哪些」,那是另一需求,本期不覆盖。
7. **ETF 自选**:自选页可加 ETF(`api/kline.py:32` `asset_types=stock,etf`),股池仅股票 → join 自然不命中,无副作用,无需特判。

---

## Sources

- 全部结论基于仓库实读代码与本地数据实测(`data/user_data/watchlist.parquet`、`data/user_data/strategy_cache.json` 均直接读取确认);无外部数据源依赖。
- 关键代码位置:`backend/app/services/watchlist.py`、`backend/app/api/watchlist.py`、`backend/app/api/pool.py`、`backend/app/services/pool_hub.py`、`backend/app/services/guest_masking.py`、`backend/app/main.py:776-847`、`backend/tests/test_pool_hub.py:788-833`、`backend/tests/test_guest_masking.py`、`frontend/src/pages/Screener.tsx:429-447`、`frontend/src/pages/PoolHubPage.tsx`、`frontend/src/components/pool-hub/StockListTable.tsx`、`frontend/src/lib/api.ts:2025-2051`、`frontend/src/lib/queryKeys.ts`、`frontend/src/main.tsx:22-27`。
