# 功能手册

各功能模块的详细说明。配置见 [configuration.md](./configuration.md),部署见 [deployment.md](./deployment.md),部署验证见 [deploy-verification.md](./deploy-verification.md),策略相关见 [strategy.md](./strategy.md)。

> 首次使用建议顺序:**设置 → 凭据与能力**(重新检测) → **立即跑盘后管道**(拉日 K + 算指标) → **自选页**加标的 → **选股页**扫描 → **回测页**验证 → **监控中心**配规则。

---

## 🔍 选股引擎(Screener)

**27 个内置策略**,每个策略一个独立 Python 文件,基于 Polars 表达式向量化实现(`backend/app/strategy/builtin/`):

| 类型        | 代表策略                                                 |
| :---------- | :------------------------------------------------------- |
| 趋势 / 形态 | 趋势突破 · 均线多头 · MA 金叉 · MACD 金叉放量 · 布林突破 |
| 量价 / 涨停 | 量价齐升 · 高换手强势 · 连板股 · 断板反包 · 涨停动量     |
| 反转 / 波动 | 超跌反弹 · 超卖反转 · 新低反转 · 低波动龙头 · 回踩 MA20  |
| 竞价 / 盘前 | 竞价多头 · 盘前强势量化 · 早盘之星 · 极速抢筹 · 竞价阿尔法 · 金色两点半 · 竞价全面 · T+1闪电 · 盘中确认 |

全 A 股一次扫表,Polars 毫秒级返回。选股页点策略卡片即可扫描,结果支持导出。

**ETF 支持**:选股页顶部可切换 `股票 / ETF`。ETF 复用已算好的 `kline_etf_enriched` 技术指标,仅开放**技术类内置策略**(趋势/量价/反转/波动);依赖涨停信号的策略(连板股、断板反包)为股票专有,ETF 模式下不显示。需先在数据页开启 ETF 拉取(`pipeline_pull_etf`)并跑一次盘后管道。

扩展策略的三种方式见 [strategy.md → 扩展策略](./strategy.md#扩展策略的三种方式)。

### 🗓️ 股池日期导航

每次盘后 run_all 的结果以**冻结式点快照**落盘 `screener_results/date={as_of}/`(携带计算时刻与策略版本指纹),可经日期列表(`GET /api/pool/dates`)与按日取池(`GET /api/pool/history?as_of=`)浏览历史股池。快照由盘后 EOD job 自动预生成,无数据日显示诚实空态;概念板块默认为当前归属标注(`current_snapshot`),非当日快照归属(历史日若已有 as_of 归档则按当日快照归属,详见下文「概念板块 PIT」)。

历史缺口(有 enriched 数据但缺快照的交易日)可由运营经 `POST /api/pipeline/backfill` **一键批量回填**——后台 job 逐日重算并落快照,进度经 `/api/pipeline/jobs/{id}` 可见;`GET /api/pool/dates` 同时返回 `backfill_needed` 缺口计数与 `backfill_examples` 示例日,回填完成后缺口归零。每份快照带 **`snapshot_origin`** 来源标注(`eod`=盘后归档 / `backfill`=事后回填重算),历史视图经 `GET /api/pool/history` 透传;旧快照缺该字段按 `eod` 读,provenance 诚实不伪造。

### 🧭 概念板块 PIT（历史映射）

盘后 EOD job 将当日同花顺概念（`ext_gn_ths`）与行业（`ext_hy_ths`）快照**前向归档**到平台自有根 `data/ext_history/{gn_ths|hy_ths}/date={as_of}/part.parquet`，每分区旁带 provenance `manifest.json`（`source_url` / `fetched_at` / `captured_at` / `rows` / `schema_version` / `sha256` / `dimension_field`）。

- 历史股池视图（`GET /api/pool/history?as_of=`）概念归属按 **as_of 分区解析**：分区存在 → `as_of_snapshot`（该日存档归属，前端显示「概念按当日快照」+ 概念数据生效日期）；分区缺失 → 回退当前快照并标注 `current_snapshot` / `unavailable`（诚实，绝不伪造历史）；存量上线前 ~247 个历史日不回填，恒为当前归属标注。
- 前端股池页在明细区渲染概念归属徽标：非 `as_of_snapshot` → 「概念归属为当前快照，非该日数据」；`as_of_snapshot` → 「概念按当日快照 · 概念数据生效日期 {date}」。
- 诚实边界：归档仅前向（EOD 起），内容来自平台可见的当前 ext 快照（离线确定性），与实时 hub 的 `current_snapshot` 标注区分；概念归属单状态不混用。

### ⭐ 自选股联动（Watchlist Sync）

已登录研究员可在股池钻取明细表每行代码旁用自选星标一键加入/移出自选（在自选为实心高亮，不在为空心）；用钻取区 header 的「只看自选」开关把表格收窄到当前策略在自选清单中的行，或点「批量加自选」把当前可见行一次性加入自选。自选集合经共享 `QK.watchlist` 缓存与自选页/策略页/个股弹窗即时一致，匹配键为全后缀 `symbol` 精确匹配（无归一化/无 code 匹配）。游客会话不渲染任何自选控件、也不发起自选查询（仅服务端已脱敏的只读面）。

### 🕗 盘前预览 (Premarket Preview)

工作日上午 **09:26**（09:25 集合竞价撮合定盘后，北京时间）独立 job 经 `ScreenerService.run_all_with_hits(as_of=今日)` 生成**今日盘前预览股池**，写入独立分区 `premarket_results/date={T}/part.json` —— **绝不写** `strategy_cache.json` 最新指针，也不写 `screener_results` EOD 点快照（EOD 语义与归档日期不动）。

- 预览数据帧含补算的 `open_gap`（开盘涨幅，与盘后 EOD 同一公式），每份预览带 `window: "pre_open"`、`computed_at`、`provisional: true`（基于开盘/定盘价，**非收盘定稿**）、`degraded`（真实竞价列不可用时为 true）与 probe 判定。
- 只读端点 `GET /api/pool/premarket` 返回今日预览（缺失 → 200 `available:false` 诚实空态，非 404）；股池页「最新」视图在盘前预览存在且今日 EOD 快照未生成时展示预览池并标注「盘前预览 · 竞价窗口 09:15-09:25 · 非收盘定稿」，15:35 EOD 后自动回退收盘池。
- **诚实边界**：真实竞价列仅在今日 probe `available` 且实时源返回今日窗口行时可用（第二档，依赖外部实时竞价源）；未配置时仅展示派生列（`degraded`），**绝不**把盘前预览标为收盘定稿、不把 09:30 bar 标为集合竞价数据；日期导航只列 EOD 快照日，盘前预览不进入归档日期。

### 🧪 竞价策略历史验证 (Auction Strategy Validation)

只读端点 `GET /api/research/auction/validation` 输出 9 个竞价/盘前策略（极速抢筹、竞价全面、T+1闪电、盘中确认、竞价阿尔法、金色两点半、竞价多头、盘前强势量化、早盘之星）在 enriched 历史窗口上的**信号质量报告**（POOL-03 零执行：GET-only，不写任何湖/缓存，不触发计算/同步/回填；报告区间不受回测 186 天 guard 限制，覆盖由 enriched 缓存边界决定，窗口超覆盖自动回夹并双字段回显 `window.requested_*/effective_*`）。

- **诚实数据门**：`data_gate: available|empty` —— `kline_auction` 湖空 → 200 `{data_gate:"empty", coverage:0}`（**绝不 404/500**），`empty_reason: no_auction_partitions|enriched_unavailable|no_dates_in_window`；`enabled` 日期 = `kline_auction` 分区 ∩ enriched 交易日；`probe` 为服务端权威状态透传（不参与历史闸门）。
- **分支标注（互斥）**：4 个真列策略（极速抢筹/竞价全面/T+1闪电/盘中确认）恒 `branch:"real"` —— 湖空时 `n_dates==0` 诚实报告，**绝不降级为派生**；竞价阿尔法按湖有无取 `real|derived`；4 个 EOD 代理（金色两点半/竞价多头/盘前强势量化/早盘之星）恒 `branch:"eod"`；`minute_confirm:"not_applied"` 显式（分钟确认层不在报告范围）。
- **前瞻口径（BT-04）**：信号日 T 以开盘价入场；`next_day_open_ret = open_{T+1}/open_T − 1`、`next_day_close_ret = close_{T+1}/open_T − 1`、`open_gap_outcome = open_{T+1}/close_T − 1`；结果日 = 全市场交易日历的下一交易日（绝不按标的行内 shift）；结果日缺行计入 `n_missing_outcomes`，统计排除，**绝不 0 填/前向填充**。
- **诚实边界**：真实竞价列验证以待 `kline_auction` 历史分区就位（当前 0 分区 —— 湖空时真列分支诚实空，不伪造真值）；本报告为纯 API 研究报告，无前端消费（D-05）。

### 🧪 竞价回测 (Auction Backtest)

竞价族 9 策略在 enriched 历史窗口上的**信号质量回测**（BT-07）：单面板向量化扫描 → 候选掩码 → BT-04 前瞻（结果日 = 全市场交易日历下一交易日）→ 长格式命中行 + provenance manifest → 原子落盘 `backtest_results/run_id={确定性哈希}/`（`part.parquet` + `manifest.json`）。回测区间**不受回测 186 天 guard 限制**（D-06：单面板向量化扫描，覆盖由 enriched 缓存边界决定，窗口回夹 + `requested_*/effective_*` 双字段回显；guard 仍只守卫 legacy vectorbt 组合回测面）。

- **触发面（O1，operator CLI，manual-only）**：零 API POST —— 写触发独立于研究查询面，研究端点恒 GET-only（AST 守卫锁死）。参数恒 META 默认（O2：不接受策略参数覆盖，策略定义变化由 `strategy_version` 指纹记入 manifest，跨日可比性由 META 默认保证）。同参数重跑幂等 — fingerprint 含**湖覆盖 digest**（`lake_coverage`: auction_symbol_count + 分区日期数, RC-01）：同命令 + 湖覆盖变化 → 新鲜 run_id + 重写（回填后重跑绝不静默 reused 陈旧数据）；同湖同输入 → reused 不重写。

  ```bash
  cd backend
  # 全量: 9 竞价族 × 最近 248 个 enriched 交易日 × 全市场
  .venv/bin/python scripts/auction_backtest.py
  # 子集策略 + 显式窗口 + 标的裁剪
  .venv/bin/python scripts/auction_backtest.py --strategies golden_230,auction_bullish \
      --range 2026-01-01,2026-08-05 --symbols 000001.SZ,000002.SZ
  # DATA_DIR 覆盖 (镜像 probe_concept_drift)
  DATA_DIR=/path/to/data .venv/bin/python scripts/auction_backtest.py
  ```
  终态摘要：`run_id` / `wrote|reused` / requested+effective 窗口 / 每策略 `{id} branch= dates= hits= sym_covered= sym_hit= missing=` / `coverage.symbols` 诚实覆盖 / 落盘路径 / 耗时。`--rpm` 为保留参数（当前无操作 —— 本地向量化单面板回测无需限速，诚实不假装生效）；**`--force`（RC-04，CLI-only，零 API 面）**：绕过指纹检查强制重写 —— 覆写时 manifest 记录 `rewritten_at`（operator escape hatch，目录覆盖语义 provenance 诚实；正常路径幂等语义零影响）。
- **上游恢复后全量 ≥0.94 重跑 = 单条 operator 命令**（Phase 36 FA-04 全量回填完成后；5-10s，无新代码）：

  ```bash
  cd backend && time .venv/bin/python scripts/auction_backtest.py --range 248
  ```

  RC-01 digest 保证新 run_id（`wrote=True`，绝不静默 reused 陈旧结果）；预期 coverage ≈5204/5537（≥0.94）、rows ≈1.29M、gated-4 hits 720 → thousands+ [实测]、EOD 329,087 与 intraday 52,591 不变。证据：RUN-EVIDENCE-37-02.md §7。
- **只读查询（BT-09）**：`GET /api/research/backtest` 列运行（扫 `backtest_results/run_id=*` 目录读 manifest，返回 `{runs, count}` 按 `created_at` 降序；`?strategy=` / `?branch=` 按 manifest.strategies 过滤；空湖 → 200 `{runs:[], count:0}` 诚实空）与 `GET /api/research/backtest/{run_id}` 详情（manifest 全文 + `part.parquet` 行统计 + 采样 ≤20 行；`?strategy=&branch=&as_of=&symbol=` 谓词下推；坏格式 run_id → 400，不存在 → 404 `RESEARCH_BACKTEST`）。**全规模实测（37-03，2026-08-07，证据 RUN-EVIDENCE-37-02.md §9）**：40-60万行 part.parquet（`298d743e8083` = 382,398 行）详情查询 **sub-second 实测 0.05s**，谓词下推 `?strategy=auction_fast_grab&branch=real` 0.015s → n_rows 31；旧 run `1cbb901a5637`（381,690 行）继续可查（旧运行永不失效）；列表 count=7 与 backtest_results run_id 目录一致（vectorbt 平面文件诚实跳过）。查询面 **GET-only 零执行**：不写任何湖/文件、不 import 执行族或竞价同步/快照/回填/选股触发面模块（`tests/test_research_backtest_guard.py` AST 守卫 7 项：GET-only/零写/E3 字面量/import 白名单 + 服务面 E2 根隔离）。
- **湖面共存诚实**：`backtest_results/` 同时存在目录形 research 运行（含 `manifest.json`）与 legacy vectorbt 平面文件（`run_id={id}.parquet`，`services/backtest.py`）—— 列运行端点**只把含 manifest 的目录计入**，平面文件诚实跳过（不报错不误读）；run_id 空间天然不冲突（sha1[:12] vs vectorbt id）。
- **诚实覆盖（BT-08，34-02 报告字段同源）**：`coverage.symbols` = `{auction_symbol_count, enriched_symbol_count, symbol_coverage_ratio, auction_rows_present, auction_rows_expected}` + 每策略 `n_symbols_covered` / `n_symbols_hit`（字段名与验证报告一致）。今日真列宇宙 = **37 symbol（实测 8,951 行 × 248 日分区）**—— `coverage.symbols` = 37/5537（**0.67%**），`auction_rows_present` 8,951 / expected 1,373,176 → **诚实部分态**（rows_present < expected，绝不插值、绝不谎报 ≥0.94；口径恒为 backfilled/5537）。4 个真列策略（极速抢筹/竞价全面/T+1闪电/盘中确认）恒 `branch:"real"`，竞价阿尔法按湖有无取 `real|derived`，4 个 EOD 代理恒 `branch:"eod"`（分支互斥 BT-05，逐行落盘）。全量竞价回填（上游恢复后，命令见触发面节）解锁全宇宙真列分支。沙箱实测：**34-03 基线** —— Run A（4 EOD × 248 日 × 全市场）329,087 命中行、`auction_symbols=2`、`enriched_symbols=5537`、`ratio=0.04%`、耗时 **≈4s**（34-01 的 ~1-3min [INFERENCE] 估算已被实测取代）；Run B（真列 4 策略 × 248 日 × 2 symbol）诚实 `auction_symbol_count==2`、12 命中行、幂等重跑 `reused`。**37-02 当前湖态重跑（2026-08-07，证据 RUN-EVIDENCE-37-02.md）**：全市场 9 策略 × 248 日 → coverage 0.036% → **0.67%**（37/5537）、rows_present 496 → **8,951**，4 列门控真列 hits **12 → 720 [实测]**（allround 214 / alpha 336 / fast_grab 31 / t1_flash 139），EOD 4 策略 **329,087 不变**、auction_intraday_confirm **52,591 不变**，runtime **5.2s wall（≤10s）**，同命令二次重跑 `reused` 幂等（同一 run_id `298d743e8083`）。
- **前瞻口径（BT-04）**：与验证报告逐字一致（`next_day_open_ret = open_{T+1}/open_T − 1` 等三公式 + 全局日历结果日 + `outcome_missing` 计数，绝不 0 填/前向填充）；34-03 沙箱抽查 3 日 × 2 symbol 手核 `kline_daily` 通过。
- **BT-10 分钟限制（确认维度诚实受限）**：`kline_minute` 历史 **CLOSED**（0 分区；xyz 1m ≈ 21 交易日、ifzq/sina 仅尾随窗口、TickFlow 分钟档位 gated at pro+）；`_minute_loader` 未接线 → `auction_intraday_confirm` 恒空（engine.py:376-390 短路）；回测行/报告恒 `minute_confirm:"not_applied"`，manifest `minute_note` 承载说明；auction_intraday_confirm `branch=real` 但日线初筛仅消费 `open_gap`（enriched 派生列，非竞价列，intraday_confirm.py:38-43）—— hits 不随湖覆盖增长（52,591 恒定，2026-08-07 实测），manifest minute_note 承载（RC-03）。**全量分钟 248 日回填 CLOSED**（BT-10 P2 验收 = 注解诚实，非实现分钟）。**Phase 38 接线落地（2026-08-07）**：`_minute_loader` 已由 `make_minute_loader(data_dir)` 工厂接线（main.py + governed_runner.py 双构造点，engine.py 零改动）；空湖行为逐字节保持（required → 空池 / optional → 跳过确认，fail-closed）；**点亮前置 = live 日湖写** —— `kline_minute/date={T}/part.parquet` 需在同步后（15:30 EOD 管道或手动同步）落盘，**绝非盘中 09:45 即时**；证据：`.planning/phases/38-minute-wiring/38-03-SUMMARY.md`。

### 📥 竞价历史回填（Auction History Backfill）

运营触发端点 `POST /api/kline/auction/backfill`，把 `kline_auction` 湖从 0 分区回填到与 `kline_daily` 对齐（竞价列是日 K 的补充面）。body：`{"symbols": ["000001.SZ", ...] | null(全量), "start"/"end": "YYYY-MM-DD" | null, "rpm": 1..60 | 30}`；立即返回 `{"status": "started"|"reused", "job_id"}`（单飞：已有同类任务在跑 → `reused`）。进度/终态/取消复用既有 `GET /api/pipeline/jobs/{id}`（轮询）与 `POST /api/pipeline/jobs/{id}/cancel`（合作式，每 symbol 检查）；与 pool backfill / EOD 重任务槽互斥（`已有数据任务在运行` 失败记录）。

- **诚实闸门（AQ-03）**：探针 `available` + 预检可达才写 —— 源不可达 → 0 写 fail-closed（`reason: "source_unavailable"`）；**只写 kline_daily 已对齐日期**（范围 = kline_daily 分区 ∩ [start,end]，写边界再过滤一次），绝不 phantom-write 日 K 没有的日期；per-symbol 失败台账 `failed_symbols: [{"symbol", "reason"}]`，`reason` 二选一 —— `"empty_response"`（上游空但有 kline_daily 覆盖，如 BJ 标的 R8）或截断异常消息（≤200 字），终态如实反映部分失败，**绝不伪造成功/0 填缺失**。
- **诚实 provenance（AQ-04）**：`origin="backfill"` 只存在于 job 终态 dict —— 湖无 provenance 列（回填与实时 EOD 同分区写，provenance 即分区存在性，per-分区 provenance 是 seam 变更，不在 Phase 32 范围）；`auction_unmatched_volume`/`auction_unmatched_amount` 上游无此字段 → 列缺席**永不 0 填**，派生 `auction_unmatched_amount` 仅当输入列可得时由读路径计算。
- **操作指引（AQ-05）**：rpm 1..60，默认 30（≈2s/码）；全 5537 码全量 ≈ 3-5.5h（rpm≈37 自然节流 ≈ 3h）；建议按子集 `symbols` 分批运行；重跑幂等（分区 merge-upsert 只填缺口）；出现 429 → 降 rpm 重跑；BJ 标的若上游无覆盖 → 诚实 `empty_response` 记录，不预填。触发示例：

  ```bash
  # 全量回填（默认 rpm=30）
  curl -X POST http://localhost:8000/api/kline/auction/backfill -H 'Content-Type: application/json' -d '{}'
  # 子集 + 日期范围 + 慢速（限流友好）
  curl -X POST http://localhost:8000/api/kline/auction/backfill -H 'Content-Type: application/json' \
       -d '{"symbols": ["000001.SZ", "600519.SH"], "start": "2026-07-01", "end": "2026-08-05", "rpm": 10}'
  # 响应: {"status": "started", "job_id": "..."} → GET /api/pipeline/jobs/{id} 轮询终态;
  # 取消: POST /api/pipeline/jobs/{id}/cancel (合作式)
  ```
- **AQ-06 注记（P2，doc-only）**：分钟历史回填已**正式关闭（CLOSED）** —— xyz 1m ≈ 21 交易日覆盖（实测）、ifzq/sina 仅尾随窗口、TickFlow 分钟档位 gated at pro+；`kline_minute` 保持增量 ≤30 日同步（`sync_and_persist_minute` 零改动）；证据：`research/v2.3-data-depth/AUCTION-BACKFILL.md` §4/§6。
- **R3 注记（probe 缓存）**：`capabilities.auction=True` 后 `resolve_auction_probe()` 每次调用一次实时 HTTP（1.6s 名义 / 8s 超时）——影响 `GET /api/kline/auction/history` 与 EOD 闸门延迟；短 TTL probe 缓存是**后续可选守卫**，不在 Phase 32 内实现。

- **AQ-07 全量回填实测规模（Phase 36, FA-04）**：宇宙 5537 码（SZ 2894 / SH 2310 / BJ 333，`_lake_distinct_symbols` 同源；kline_daily 1,326,996 行）× 248 交易日 → `kline_auction` 湖终态 ≈ **1,290,592 行** / 248 个 `date=` 分区（实测满分区 ~45 KiB → 全湖 ≈ **11-13 MB**）。实测 pilot 延迟 mean 0.96s / median 0.82s / p95 1.24s / max 2.49s（n=20 live，**0×429**）；rpm 30 全量 ≈ 3.4-3.8h，含裕量 **3.5-5.5h**（工作量主导，rpm 30/60 无差）。429 → 指数退避 2s→4s ×2。证据：`research/v2.3-data-depth/AUCTION-BACKFILL.md` + Phase 36 回填台账。
- **AQ-08 断点续跑 / only-missing（FA-02）**：`--only-missing` / API body `only_missing: true` —— 开工前覆盖预扫描（`SELECT symbol, COUNT(*) … GROUP BY symbol`，对齐窗口内行数 == 交易日数 ⇒ 已全覆盖跳过；部分残差整窗重拉 merge-upsert 幂等补齐）；中断的 run 用同一命令**顶补而非重跑**（验收口径：连续两次 `--only-missing` **0 新增**）。BJ 333 恒 `empty_response` → 每次全量顶补仍请求 333 并如实记失败（幂等、0 新行，属预期噪声非异常，`requested>0` 正常）。
- **AQ-09 长任务豁免（FA-01）**：回填 job 经 `job_store.create(timeout_s=21600)` 持久化 **6h 豁免**；`reap_stale` 按 per-job `timeout_s` 优先（`j.get("timeout_s", STALE_JOB_TIMEOUT_S)`，缺省仍 600s）——全量 3.5-5.5h 跑不再被 600s 陈旧回收误杀；取消仍为合作式（每 symbol 检查 job 状态）。
- **AQ-10 运营 CLI（FA-03）**：`backend/scripts/auction_backfill.py`（`--all|--symbols --start --end --rpm 1..60 --only-missing --out <json>`，`--all` 为缺省行为，`DATA_DIR` 环境变量覆盖）；`job_id=None` 独立进程、**零 job_store**（无单飞/无超时回收/无 run 槽，重启中断安全）——detached 全量跑的载体；终态 dict（成功 8 键 `{requested, backfilled_symbols, rows, dates, failed, failed_symbols, origin, rpm}` / fail-closed +`reason` 9 键）+ `failed_symbols` 台账原子落盘 `--out`；退出码 0 = 无 reason 键（成功或部分成功含 BJ 失败，台账诚实存在），1 = fail-closed 或未捕获异常。
- **AQ-11 诚实覆盖上限（FA-05）**：BJ 333 上游**恒空**（6 只 920xxx 实测 0 行；5 种替代代码格式 BJ920016 / 920016.BJ / bj920016 等全部 `请求参数错误`）→ 覆盖天花板 **94.0%**（5204/5537，SZ/SH 全量、BJ 逐 symbol `empty_response` 台账），**从不宣称 100%**、不预填、不假装覆盖；完整 stance 见 `FA-05-BJ-STANCE.md`。
- **AQ-12 回填验证**：`backend/scripts/verify_auction_backfill.py` 只读输出检查清单（248 分区 / ~5204 行 / ≥3 日 × ≥3 码 `auction_virtual_price == kline_daily.open` 交叉验证 / BJ 920 号段 empty_response 集合 / 无 `.tmp` 残留）。
- **调度纪律（EOD 交织, Phase 36）**：
  1. 全量回填调度在 EOD `run_all` 窗口**之外**——跨进程 `kline_auction` 写**无锁**（read-modify-write + 原子 rename，last-rename-wins），窗口纪律是唯一保护；
  2. 进程内 run-slot 串行（`try_acquire_run_slot`）不变，覆盖服务端并发（backfill API vs EOD vs pool backfill 同一进程）；EOD 侧双闸门（`daily_pipeline.py:699-708`：`auction_sync_enabled` 偏好 + probe 可达）默认关闭；
  3. CLI（`job_id=None`）是独立进程、**不共享槽位**——EOD 窗口规则是唯一保护，**文档化而非工程化消除**（零新增依赖守卫）；
  4. 交错写不会损坏湖（每分区原子 rename + merge-upsert），最坏 = 同日分区 last-rename-wins，纪律避免之。

### 🗄️ 股池回填 (Pool Backfill)

运营触发端点 `POST /api/pipeline/backfill`，把 `screener_results` 湖的历史缺口（有 enriched 数据但缺冻结快照的交易日，`GET /api/pool/dates` 的 `backfill_needed` 计数）逐日补齐。body：`{"start"/"end": "YYYY-MM-DD" | null, "max_days": 1..500 | null}`；立即返回 `{"status": "started"|"reused", "job_id"}`（单飞：已有同类任务在跑 → `reused`）；与 EOD / 手动 run_all / 竞价回填共用一个**重任务执行槽**（并发 → 失败记录 `已有数据任务在运行`）。**全量 248 缺口一次调用即可覆盖**：`max_days` 上限 500 ≥ 248（248 个交易日 2025-07-29..2026-08-05），**无需分块**。

- **触发示例**：

  ```bash
  # 全量回填（覆盖全部缺口日, 248 个交易日）
  curl -X POST http://localhost:3018/api/pipeline/backfill -H 'Content-Type: application/json' -d '{}'
  # 可选显式日期界（幂等差集 — 已快照日自动跳过, 绝不重算）
  curl -X POST http://localhost:3018/api/pipeline/backfill -H 'Content-Type: application/json' \
       -d '{"start":"2025-07-29","end":"2026-08-05"}'
  # 响应: {"status": "started", "job_id": "..."} → GET /api/pipeline/jobs/{id} 轮询终态;
  # 取消: POST /api/pipeline/jobs/{id}/cancel (合作式, 当前日完成后停)
  ```
- **轮询/取消**：`GET /api/pipeline/jobs/{id}` → status/progress/stage；终态 6 键 `{requested, backfilled, failed, failed_dates, origin: "backfill"}`；`POST /api/pipeline/jobs/{id}/cancel` 合作式取消（每日期检查 job 状态，当前日完成后停）。
- **失败处理**：终态 `failed_dates` 列表即剩余缺口 → 直接重跑同端点（幂等只补缺口差集）。
- **跑后验证（步骤 7）**：

  ```bash
  ls data/screener_results | wc -l                                 # == 248 (分区数 = 缺口全清)
  jq -r '.snapshot_origin' data/screener_results/date=2026-08-05/part.json   # == backfill
  curl -s localhost:3018/api/pool/dates | jq '{count, backfill_needed}'      # count==248, backfill_needed==0
  curl -s "localhost:3018/api/pool/history?as_of=2025-07-29"                 # 渲染: snapshot_origin=="backfill", strategies 非空
  ```
  **provenance 在分区 payload 内**：`snapshot_origin` 键（`eod`=盘后归档 / `backfill`=事后回填重算 / `manual`）+ `strategy_version` 策略集指纹随快照 JSON 落盘（**无独立 manifest、无文件系统元数据**）；历史视图经 `GET /api/pool/history` 透传。旧快照缺该字段按 `eod` 读。
- **前置检查**：`df -h data/`（余量 ≥ 1 GiB）；`ls data/kline_daily_enriched | wc -l` == 248（enriched 全量就位）；`ls data/screener_results 2>/dev/null | wc -l` == 当前缺口（记下基线，完成后应归零）；确认网络（probe 每日常量 1 次 live HTTP，8s 超时）。
- **预期（实测锚点, Phase 33 沙箱子集）**：8 个交易日真实回填耗时 **13 秒（~1.6s/日）** → 全量 248 ≈ **6-7 分钟**（`_refresh_enriched` 启动全历史预计算摊销了 150 日 warmup；早期 20-120 分钟 [INFERENCE] 估算已为实测取代）；存储实测 **21 MiB/8 日 ≈ 2.6 MiB/日** → 全量 248 ≈ **650 MiB**（早期 79-693 MiB [INFERENCE] 估算区间，实测落其上沿；磁盘余量实测 1012 GiB 非阻塞）；`strategy_version` = 回填时刻策略集指纹 —— **后续改策略需重跑**（诚实重算语义）。
- **premarket_results 诚实缺口（PB-04）**：`premarket_results/` 的唯一创建方是工作日 09:26 盘前预览 job（`premarket_pool_preview`，见上「盘前预览」），**双重门禁** —— ① 部署门禁：scheduler 仅非 `fixture_mode` 启动（沙箱从不跑 cron）；② 数据门禁：需实时 09:15-09:25 集合竞价 feed，盘前无 live 缓存 → 诚实 `available:false` 空帧不落盘。**沙箱无任何路径产生该目录（实测不存在）**；股池回填 / 手动 run_all 只写 `screener_results/`，绝不触碰 premarket root（结构门测试锁定，见 `test_pool_backfill_never_creates_premarket_root`）。部署后由真实 09:26 job 按日产生；前端空态已诚实（`GET /api/pool/premarket` → 200 `available:false`）。**无沙箱路径，绝不伪造产物**。
- **Probe 网络注记（Phase 32 联动）**：竞价能力解锁后每次 `_attach_auction` 触发一次 live probe HTTP（PROBE_SYMBOL `000001` → 最新 kline_daily 分区，8s 超时）——回填**逐日一次**；源挂时全量 248 最坏 **+~33 分钟纯超时**。诚实双峰期望（行数网络相关，Phase 33 实测）: probe fail-closed → `requires_auction_data` 策略 total=0（引擎短路，竞价列缺席），`auction_alpha` 走派生分支；probe available → 竞价列注入，真列族最多命中稀疏湖 2 个标的（实测 0 行，000001/000002 未过阈值），派生族（竞价多头 / 早盘之星 / 盘前强势量化）全市场正常（实测 50/50/43，display_limit 封顶）——**绝不产生全市场规模结果**；total=0 策略保留在快照（如实记录）。

---

## 📊 指标流水线(Indicators)

原生 Polars 向量化,全 A 股一次扫表落盘 enriched Parquet:

- **均线 / 趋势**:MA(5-60) · EMA · MACD · 动量 · 布林带
- **震荡 / 波动**:RSI · KDJ · ATR · 年化波动率 · 振幅
- **量能 / 涨跌停**:量比 · 量均线 · 涨停信号 · 连板数
- **原子信号**:MA / MACD 金叉死叉 · N 日新高新低 · 布林突破
- **复权**:基于除权因子自动前复权,回测与指标口径一致

盘后管道(15:30 CST 自动触发)会重新拉日 K + 重算 enriched 表。

---

## 🧪 回测引擎(Backtest)

基于 vectorbt(**三种模式**):

| 模式 | 说明 |
| :--- | :--- |
| 个股回测 | 单标的 + 策略,看个股历史表现 |
| 策略组合 | 一个策略扫描全市场,按组合约束回测 |
| 自由信号组合 | 多个自定义信号组合,自定义权重 |

**真实约束**:T+1 · 手续费 · 滑点 · 止损 · 最大持仓天数。

**组合管理**:最大持仓数 · 敞口控制 · 等权 / 自定义仓位。

输出净值曲线 · 夏普 · 最大回撤 · 胜率 · 交易明细。SSE 流式进度支持切页重连,不会丢失回测任务。

**ETF 支持**:三种模式的后端与 API 均支持 `asset_type=etf`,回测面板改从 `kline_etf_enriched` 读取(单次回测为单一资产类型,不混合股票与 ETF)。策略组合与因子回测页均有 `股票 / ETF` 切换,ETF 模式下策略列表与标的搜索跟随资产。需先开启 ETF 拉取并跑盘后管道。

---

## 📡 监控中心(Monitor)

统一规则引擎,一个页面管理**五类监控**:

| 类型 | 场景 |
| :--- | :--- |
| 策略监控 | 策略扫描结果有变化时触发(如新增符合标的) |
| 个股信号监控 | 特定个股的指标条件(如 `RSI > 80`) |
| 价格涨跌监控 | 涨跌幅 / 价格突破阈值 |
| 全市场异动 | 全市场异动(如快速拉升/跌停) |
| 盘前监控 | 09:26 盘前预览帧上的竞价白名单字段条件 (`open_gap` / `auction_*`), 事件带「盘前·非最终」标注 |

**ETF 支持**:规则可选资产类型 `股票 / ETF`。监控引擎按规则 `asset_type` 分轮评估——ETF 规则用 ETF enriched 快照评估(`engine.evaluate(..., asset_type="etf")`),策略型规则走 ETF 历史加载器(读 `kline_etf_enriched`)。盘中触发需开启 ETF 实时行情(`realtime_pull_etf`),使 ETF 报价进入 enriched 快照。

**特性:**

- 多条件 AND/OR + 冷却期去重 + 严重级别(info / warn / critical)
- 多入口配置:监控中心新建 / 个股详情页「加监控」/ 策略卡片一键开启
- 命中后右下角弹窗(可配声效)+ 持久化到 `alerts.jsonl`,菜单未读徽标
- **触发记录详情**:每条记录展示命中的具体条件(如 `RSI>80`)与当前价位,一眼看清为何触发
- **盘前监控 (preopen)**:规则字段仅限竞价白名单 (`open_gap` / `auction_volume` / `auction_amount` / `auction_volume_ratio` / `auction_unmatched_amount`),配置期即拒绝 EOD 列 (`change_pct` / `close` 等)——杜绝建出必失败的规则
- 盘前告警带「盘前·非最终」(provisional)标注;竞价数据源降级时竞价列规则 fail-closed 0 告警(绝不 0 填),并加「数据降级」(degraded)徽标
- 盘前评估挂在 09:26 预览 job 尾段,与盘中连续竞价告警互斥(盘中 `evaluate` 显式跳过 preopen 规则)

### 飞书 Webhook 推送

全局一处配置飞书群机器人地址,启用推送的规则命中即推送到飞书群(支持签名校验)。可在设置页设「默认推送渠道」,新建规则自动预填。

---

## 📈 个股分析(Beta)

以「行情 + 关键价位」为主体的单标的决策页:

- **专用日 K 图表**:主图 + 成交量 + 滑块,默认近 6 个月
- **9 类关键价位**(纯函数实时计算,毫秒级):压力支撑 · 成交密集区 · 枢轴点 · 前高前低 · Keltner 通道 · ATR 止损 · 缺口位 · 斐波那契 · 整数关口
- **AI 四维分析**:技术 / 基本面 / 财务 / 消息面流式生成,实战派交易员视角

---

## 🏆 连板梯队 & 概念分析

- **连板梯队**:实时统计各连板层级(首板 / 2 连板 / 3 连板...)的标的与封单,捕捉市场情绪与题材热度
- **概念涨幅轮动**:基于 ths 概念 / 行业,统计概念板块涨幅与 RPS 轮动,AI 分析资金主线
- **盘后 AI 复盘**:盘后自动生成市场复盘,可推送至飞书群

### 📊 竞价复盘 (Auction Recap)

确定性竞价复盘面板(REV-01..05):与 AI 复盘流内嵌面板共用同一装配函数
(`build_auction_recap`),**确定性数据,非 AI 生成** — 基于三类冻结资产的只读聚合,
不触发任何计算/同步/回填,绝不写任何存储(POOL-03 零执行权限)。

- **三块面板**:
  - **真实竞价活跃度**:集合竞价湖分区(`kline_auction`,09:15-09:25 窗口末行,09:30+
    连续竞价 bar 永不入列)的竞价总额 / 标的总数 / 金额 Top 10 / 竞价量比;
  - **开盘涨幅快照**:enriched 读时计算的 `open_gap` 高开分布(≥2% / ≥5%)、均值、
    Top 10(open_gap 基于 enriched 复权口径);
  - **盘前信号质量**:盘前预览(`premarket_results`)∩ 竞价族策略的信号命中统计 —
    平均 open_gap、**EOD 口径**收盘兑现率/收阳率(预览行绝不直接用作收盘兑现率;
    预览有行而 EOD 缺行计 `n_missing`,不填充)。
- **诚实性**:`data_completeness` 枚举 `{full, no_auction_lake, no_premarket_preview,
  pre_eod, partial}`;缺失块省略 + 显式注记;**pre_eod**(15:30 竞价同步完成前)诚实标注
  「盘后竞价同步未完成,建议 15:35 后重跑」;无数据日 → 诚实空态,绝不 0 填/404。
- **复盘集成**:面板 delta 在 done 前(事件序 meta → AI delta* → 面板 delta → done),
  经 delta 机制归档 / SSE / 飞书三跳全收;面板全缺席 → 退化为纯 AI 报告;默认调度
  **15:40**(15:30 竞价同步 + 15:35 股池持久化之后)。
- **可选 AI 点评**:`recap_auction_commentary` 默认关闭(设置 API 切换),开启时 AI
  仅可引用确定性切片中给出的数值(护栏:禁止编造,与面板冲突以面板为准)。
- **只读端点 (REV-05)**:`GET /api/market-recap/auction?as_of=YYYY-MM-DD` —
  独立只读端点,`as_of` 严格校验(非法 → 400),缺省取最新交易日;无数据 → 200
  `available:false` 诚实空态;**guest 会话 → 掩码视图**(逐标的身份 `******` + 竞价值
  剥离,聚合统计与状态标注保留);与复盘流内嵌面板同源。
- 零新增依赖;端点/服务受 POOL-03 AST 守卫锁定(GET-only、零写路径、零执行族 import、
  import 白名单)。
- 派生列口径（估算标注常态 / 诚实缺列 / tier-2 重开 gate）见下文「竞价列与派生列」节。

### 🧮 竞价列与派生列（Auction Columns & Derived Estimates）

竞价相关列分**真实竞价列**（集合竞价撮合成交，外部源接入后存在）与**派生列**（虚拟成交估算，委托量输入可得时存在）两类，CHART-04 立场如下：

- **估算标注为常态（Standing stance）**：派生列（虚拟成交）以「估算」标注已双处固定 —— UI 分组表头 title「由竞价量与历史均量、委托量输入派生的估算值，非真实成交。」（`StockListTable.tsx:319`）、组头「派生 · 虚拟成交」（`:321`）、「虚拟未匹配金额（元·估算）」列 title「虚拟未匹配量 × 虚拟参考价的估算值，非真实成交金额。」（`:335`）；API 类型注释 `PoolHubRow.auction_unmatched_amount`「元·估算, 派生」（`api.ts:741-742`）。**任何新 UI 混排派生列必须沿用此标注纪律**（服务端先例：`indicators/pipeline.py:160` 与 `api/data.py:776` 的列注册描述「派生未匹配金额 (估算, 非真实成交…)」，`auction_columns.py:43`「派生估算列, 非真实成交; 只与真实竞价列分列共存, 永不求和/混排」）；湖空（0 分区）→ 列**永不出现**（诚实缺列而非 0 填/null-as-present，`attach_auction_columns` probe×分区双闸门 `auction_columns.py:110-118` + keep-list 裁剪「缺列即不注入」`:134-139`）。
- **CHART-04 defer**：「实时虚拟成交列」正式 defer —— 连续竞价实时行情无竞价字段，盘中实时虚拟成交列需 live 竞价流；湖实数据 248 日已由 Phase 32 回填，但**派生列仍为估算**，与真实竞价列严格区分（BT-05 分支互斥：真列策略恒 `branch:"real"`，湖空时 `n_dates==0` 诚实报告，绝不降级为派生）。
- **Re-eval gate（tier-2 重开条件）**：外部实时竞价源提供 `auction_unmatched_volume` + `auction_virtual_price` 两输入列 → tier-2 盘前真实竞价列 gate 重开（部署清单 **D3**，见 [deploy-verification.md](./deploy-verification.md)）；判定条件 = 源返回窗口内行且含两列（`auction_probe` available，`kline_auction` 分区 6 列）；未提供 → 维持现状，不伪造、不 0 填。

---

## 🧰 数据与扩展

### TickFlow 多源数据

日 K / 分钟 K / 指数 / 财务 / 实时行情,基于 [TickFlow](https://tickflow.org) 官方 SDK。

### 🔌 第三方数据接入(重点)

支持将自有量化项目的数据并入,与内置数据同台分析:

| 方式 | 说明 |
| :--- | :--- |
| HTTP 定时拉取 | Tushare 等 API,定时拉取并入库 |
| CSV / Excel 上传 | 页面直接上传文件 |
| JSON 写入 | 程序化写入 |

接入后自动 schema 发现 + 符号归一,页面可视化配置,最终并入 DuckDB 同台分析。

### 盘后定时管道

APScheduler 15:30 CST 自动:拉日 K → 重算 enriched 表 → 跑监控规则。

### 令牌桶限流

适配各档位 rpm / batch 限制,批量合并 + 增量拉取,避免触发数据源限流。
