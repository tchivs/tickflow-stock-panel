# 领域 B 研究:全市场真列回测重跑 + 竞价活跃度表面 (Real-Column Backtest Rerun & Auction Activity Surfaces)

**Research domain:** v2.4 全量数据解锁 (Full-Universe Unlock) — 领域 B 竞价回填完成后全市场真列回测重跑可行性
**Researched:** 2026-08-07
**Researcher:** ResearcherV24B
**Confidence:** HIGH (实测:2 次全市场运行 + 1 次 50-symbol 试点 + 幂等重跑验证 + 合成分区磁盘实测;代码 seam 逐行核验) / MEDIUM (回填后真列命中行数 X 为投影推断,非实测)

---

## 0. Verdict

**FEASIBLE — 全市场真列回测重跑是秒级本地向量化作业(实测全市场 9 策略 248 日 compute=2.3s),回填后重跑为一次性 CLI 操作;唯一结构性阻断 = run_id 指纹不含湖覆盖态 → 回填后同命令重跑会 reused=True 静默保留旧数据,需 ~5 行指纹增量修复。**

- 实测:全市场 5537 symbols × 248 日 × 9 策略(4 real + 4 eod + auction_alpha)compute=**2.3s**(CLI 总 5.3s,含 3.5s 全量 enriched 预载);50-symbol 试点 compute=0.8s。回填只增加湖读取(248 分区全量扫 0.31s)与真列 mask 计算,全市场重跑预算 **5-10s/次**。
- 磁盘:合成 5537-symbol 单分区 142 KB → 全市场 kline_auction 248 分区 ≈ **36 MB**(26 B/行);backtest_results ~10 MB/run。data/ 所在盘 1007G 空闲,无虞。
- 覆盖诚实翻转:现状 2/5537 = **0.036%**(实测 manifest be4ce9bc coverage.symbols ratio=0.000361)→ 回填全成后 ~100%(诚实口径 = 回填成功 symbol 数/5537,部分失败如实 partial)。
- **关键缺口(本研究会话实测)**:`_compute_run_id`(auction_backtest.py:614-640)指纹 = strategy_ids|start|end|params|strategy_version|symbols,不含湖覆盖态;`_persist_run`(auction_backtest.py:712-743)fingerprint 相同 → reused=True 跳过重写。已实测:回填前运行 1cbb901a5637,同命令重跑 → `reused=True wrote=False`,新计算结果在内存但**旧 part.parquet/manifest 保留**。回填后同命令重跑将计算新真列统计但**拒绝落盘** → 重跑前必须给指纹加湖覆盖摘要(先例:`symbols 纳入哈希`注释已声明同一理由,auction_backtest.py:624-628)。

---

## 1. 目标 (Scope)

全量竞价回填(R1,领域 A 兄弟研究)完成后,把竞价族策略回测从「2-symbol 稀疏湖真列」升级为「全市场真列」:

1. **重跑机械**:`run_full_backtest`(auction_backtest.py:426)分区存在性闸门在 5537-symbol 湖下的行为;CLI(--range/--symbols/--strategies)是否直接支持全市场重跑。
2. **运行时/磁盘投影**:真列分支(real)在全市场规模下的 compute 时间与 part.parquet 行数/体积。
3. **覆盖报告**:coverage.symbols 双块(auction_validation.py:260-292 系同构)在规模下的语义与诚实翻转 0.04%→X%。
4. **BT-04 前瞻语义**:全市场 hits(38 万→可能 40-60 万行)下公式与 n_missing 口径不变。
5. **AST 守卫 E3**(test_pool_hub mirror)与真列重跑 delta 的相容性。
6. **竞价活跃度表面**:recap Block 1 / pool_hub auction_columns / 前端消费在回填后的行为。
7. **诚实 0.04%→X% 框架**与最小代码 delta。

**非目标**:回填 job 本身(R1 领域 A)、API 触发面(现状 CLI-only,零 API 面,维持)。

---

## 2. 背景

### 2.1 现状:稀疏 2-symbol 湖与三次既有运行

| run_id | 时间 | 窗口 | 策略 | branch | 行数 | 说明 |
|---|---|---|---|---|---|---|
| `be4ce9bc038b` | 08-06 18:36:22 | 248d (2025-07-29..08-05) | bullish, early_star, preopen_quant, golden_230 | eod×4 | **329,087** | Run A — 全市场 eod 上界;part.parquet 8.9 MB |
| `191642f83b2d` | 08-06 18:36:35 | 248d | allround, alpha, fast_grab, t1_flash | real×4 | **12** | Run B — 真列稀疏 12 行 (3+6+1+2),sym_covered=2, sym_hit≤2 |
| `0f2b91e93975` | 08-06 18:36:14 | 5d | auction_bullish | eod | 0 | 5 日窗 0 命中(验证窗口解析) |

**湖现状**(实测):`data/kline_auction/` = 248 分区 × 2 symbols (000001.SZ/000002.SZ) = 496 行 = 0.49 MB。覆盖 = 2/5537 = **0.036%**。enriched 宇宙:kline_daily 1,326,996 行 = 5537 symbols (SZ 2894 / SH 2310 / BJ 333) × 248 日。

### 2.2 本研究会话新增运行(全部实测,2026-08-07)

| run_id | 范围 | 策略 | 行数 | compute | CLI 总 | part.parquet |
|---|---|---|---|---|---|---|
| `45fb75b65731` | **50 symbols** × 248d | 9 全 | 2,221 | **0.8s** | 4.5s | 56.7 KB |
| `1cbb901a5637` | **全市场** × 248d | 9 全 | **381,690** (eod 329,087 + real 52,603) | **2.3s** | 5.3s | 10.33 MB |
| `808be6bb00e1` | 全市场 × 248d | bullish only | 32,686 | 0.9s | 3.6s | — |
| (重跑) `1cbb901a5637` | 同左 | 9 全 | 381,690 (内存) | 1.9s | 4.8s | **reused=True,未落盘** |

---

## 3. 证据 (Evidence)

### 3.1 分区存在性闸门(④ 注入)在全市场规模的行为

`run_full_backtest`(auction_backtest.py:426)步骤 ④:

```python
panel, enabled_dates = attach_auction_columns_range(panel, eff_start, eff_end, repo)
```

- `attach_auction_columns_range`(auction_columns.py:146-217):历史闸门 = **分区存在性主闸门**(D-03),零 live probe;逐分区 `pl.read_parquet` + symbol 级去重 + 左联注入。湖有行但某 symbol 缺席 → 该行竞价列 null(诚实按标的缺席,非整日 null-as-present)。
- **规模行为**:注入按 (symbol,date) 左联,分区行数从 2 → 5537 只影响每个分区的读入体积。实测 248 个 5537-行分区的逐文件读(**模拟 kline_daily 形状**)= **0.31s** → 全市场注入+覆盖扫在秒内,不构成瓶颈。
- warmup 契约(auction_columns.py:151-155):面板须含 start 前 ≤5 交易日行作分母;CLI 已按 `_WARMUP_DAYS=14` 自然日回夹。

### 3.2 真列分支语义:谁真正吃竞价列

`_evaluate_strategy_rows`(auction_backtest.py:284-372)branch 互斥(BT-05):
- 4 个 `requires_auction_data` 恒 real(eval_panel = 面板 ∩ auction_enabled_dates);
- `auction_alpha` real|derived;4 个 EOD 代理恒 eod。
- mask 经 `_build_candidate_mask`(auction_validation.py:85-108)调策略 `filter_fn`,`fill_null(False)` fail-closed。

**实测拆分(全市场运行 1cbb901a5637 的 real 分支 52,603 行)**:

| 策略 | 列门控 | 实测 hits (2-symbol 湖) | 回填后预期 |
|---|---|---|---|
| auction_fast_grab | ✅ auction_volume_ratio/amount 列守卫(fast_grab.py:36) | 1 | 数千级 [投影] |
| auction_allround | ✅ 同上(allround.py:37) | 3 | 千-万级 [投影] |
| t1_flash | ✅ 同上(t1_flash.py:36) | 2 | 数千级 [投影] |
| auction_alpha | ✅ real 分支列存在互斥(alpha.py:54) | 6 | 千-万级 [投影] |
| **auction_intraday_confirm** | ❌ **filter 仅用 open_gap**(intraday_confirm.py:42-45) | **52,591** | **不变** (52,591) |

- **关键语义事实(代码+测试双重确认)**:`auction_intraday_confirm` 的日线初筛 `filter()` 只消费 `open_gap`(EOD 列),不引用任何 auction 列;测试显式声明其不在列门控约束内(test_auction_backtest.py:186-188 `_AUCTION_COL_GATED = {fast_grab, allround, t1_flash}` + 注释「auction_intraday_confirm 日线初筛仅用 open_gap → 不在此约束内」)。因此其 52,591 行「real」hits 在**稀疏湖下就已经是全市场规模**(enabled_dates=248 全量,分区存在即放行),回填后 hits 不变,仅 n_symbols_covered 2→5537。
- 引擎侧双保险(engine.py:345-348):`requires_auction_data` 且面板无 auction_volume 列 → 空结果;回测注入路径列恒在(null),该短路不触发,由 mask fill_null(False) 兜底。

### 3.3 运行时实测与投影

| 阶段 | 实测 | 说明 |
|---|---|---|
| 全量 enriched 预载(CLI `_preload_full_enriched`, scripts/auction_backtest.py:134-157) | ~3.5s | 全宇宙 scan+indicators+signals,与 symbol 过滤无关(恒载) |
| 全市场 9 策略 compute(run_full_backtest) | **2.3s** | 含注入+9 mask+前瞻 join+覆盖扫+381,690 行落盘 |
| 50-symbol compute | 0.8s | 面板行数线性缩放的下界验证 |
| 248 分区全量读(symbol 列) | 0.31s | 覆盖扫/注入的规模上限 |
| 幂等重跑(同指纹) | 1.9s compute | 计算仍全量执行,仅跳过写盘 |

**全市场真列重跑投影(回填后)**:eod 4 策略 hits 不变(329,087);intraday_confirm 不变(52,591);列门控 4 策略 12 行 → 千-万级(投影,阈值依赖);总行数 ≈ 40-60 万 → part.parquet ~11-20 MB。compute ≈ 2.5-4s + 预载 3.5s + 落盘 ≈ **5-10s/次**,绝非小时级。

### 3.4 磁盘投影

- 合成 5537-symbol 单分区(5 canonical 列)= 142 KB(26 B/行)→ **248 分区 ≈ 36 MB**。现 0.49 MB(2-symbol)几乎全是每文件 parquet 头开销,规模下每行边际成本极小。
- 现状 data/:kline_auction 0.49 MB / kline_daily 30 MB / kline_daily_enriched 52 MB;backtest_results 每次 ~10 MB。
- `df -h`: /home/orca/source 2.0T,906G 用,1007G 空闲(48%)→ 回填 36 MB + 重跑产物 数十 MB 无虞。

### 3.5 覆盖报告在规模下(0.04%→X% 诚实框架)

coverage.symbols(`_coverage_symbols`,auction_backtest.py:376-415;validation 侧同构 auction_validation.py:260-292):

```
auction_symbol_count   : 窗口分区 symbol 去重数 (2 → 回填后 5537×回填成功率)
enriched_symbol_count  : 面板 symbol n_unique (恒 5537)
symbol_coverage_ratio  : 0.000361 → ~1.0
auction_rows_present   : 496 → ≤1,373,176 (= 5537×248)
auction_rows_expected  : 1,373,176 (恒)
```

- 诚实口径:**X% = 回填成功 symbol 数 / 5537**。R1 回填的 failed_symbols 台账直接决定 X;部分失败 → rows_present < expected,ratio < 100%,如实呈现(同 _empty_report 同键形状,D-02)。
- 每策略 `n_symbols_covered`(auction_backtest.py:196-200,auction_volume 非空 symbol 去重):eod 与 real 全部 2→5537;这是「竞价列可用性」度量,非命中覆盖——eod hits 不变但 covered 翻转,报告语义正确(诚实标注列可得性)。
- dates 块:auction_enabled_count 恒 248(enabled_dates 由分区存在性决定,现湖已全 248 分区)。
- 规模成本:248 分区读 0.31s/次,每次回测固有,可接受。

### 3.6 BT-04 前瞻语义不变

- `_forward_stats` 是 `AuctionValidationService` 的 unbound 方法,回测逐字共用(auction_backtest.py:340 `AuctionValidationService._forward_stats(None, hits, ...)`),BT-04 共源零漂移。
- 结果日 = 全局日历 next-date(auction_validation.py:474-478),绝不 per-symbol shift;三公式;结果日缺行 → n_missing_outcomes 排除,绝不 0 填。hits 从 12 → 40-60 万只放大 join 输入,向量化 polars 秒级(已实测 381,690 行 hits 的 full run 2.3s 内完成)。
- test_full_backtest_forward_outcomes_bt04_formulas(test_auction_backtest.py:223)手算锁定公式,与规模无关。

### 3.7 AST 守卫 E3(test_pool_hub mirror)相容性

- E3 = pool_snapshot 永不写运行时缓存(test_pool_hub.py:1005-1011);preopen 守卫镜像同源(test_preopen_ast_guard.py:22-24,39-52)。
- 真列重跑 delta 只触碰:CLI 触发面(只读)+ 可能 `_compute_run_id`/`_persist_run`(backtest_results 写根,非 strategy_cache)。不触碰 pool/strategy_cache/执行族。
- 实测:**16 passed**(test_research_backtest_guard + test_preopen_ast_guard + test_auction_recap_guard)+ **48 passed**(test_pool_hub + test_auction_backtest + test_auction_validation),全绿。

### 3.8 竞价活跃度表面(回填后行为)

| 表面 | 位置 | 回填后变化 |
|---|---|---|
| 复盘 Block 1 真实竞价活跃度 | auction_recap.py:539-543 `_build_real_auction_activity`;渲染 :624-643;今日 probe×分区双闸门,历史分区存在性 | 历史日:2-symbol → 5537-symbol 的 total_amount/n_symbols/Top10/ratio_subblock 全量真实 |
| 复盘头标签 | auction_recap.py:558-569 | lake_ok 判定,今日仍 probe 门控(当日 09:26 实时行依赖当日 sync 链路) |
| pool_hub auction_columns 声明 | pool_hub.py:12-13,177-185 (real/derived 列存在性, OQ-2) | real 列非空范围 2→5537 标的 |
| 前端池表主徽标 | frontend/src/components/pool-hub/StockListTable.tsx:116-138 (real 列驱动) | 徽标从「2 标的有真列」→ 全市场真列 |
| 竞价历史图 | frontend/src/components/AuctionHistoryChart.tsx;API backend/app/api/auction_history.py:41 (_OPTIONAL_COLS) | 历史区间全市场可查 |
| MON 规则 schema | monitor_rules.py:51-52 (auction 列允许) | 不变(列存在性驱动) |
| enriched 管道列描述 | indicators/pipeline.py:158-184;data.py:772-779 | 不变(列 schema 静态) |
| 确定性复盘 API | market_recap_auction.py:84-138 GET /api/market-recap/auction | 历史日真实竞价聚合(非 PII 聚合保留) |
| watchlist 后端 | api/watchlist.py:无 auction 引用 | 无变化(前端 Watchlist.tsx 本域外) |

### 3.9 回填写侧已就绪的证据

`xyz_provider.py:221` 已把上游 `current` 映射 `auction_virtual_price`(R1 的 provider seam 已存在);现有湖分区列 = symbol/datetime/auction_volume/auction_amount/auction_virtual_price,与 `auction_sync.py:41` canonical 列一致 → 回填后湖结构不变,读路径零改动。

---

## 4. 结论 (Findings)

1. **重跑机械 FEASIBLE**:CLI `backend/scripts/auction_backtest.py --range 248`(缺省 9 策略全市场)直接支持;`--symbols`/`--strategies` 已就绪。回填后一条命令完成全市场真列重跑。
2. **运行时**:全市场 9 策略 compute 2.3s(实测),回填后投影 5-10s/次(含 3.5s 预载)。**不是长作业,无需 hub/进程模型/单飞**。
3. **磁盘**:kline_auction 全量 ≈ 36 MB;backtest_results ~10-20 MB/run。无虞。
4. **结果变化面**(回填后 vs 现 2-symbol 湖):
   - 变化:列门控 4 策略(fast_grab/allround/t1_flash/alpha real 分支)12 行 → 千-万级;coverage.symbols 0.04%→~100%;n_symbols_covered 2→5537(全策略)。
   - **不变**:eod 4 策略 hits(329,087);auction_intraday_confirm hits(52,591,filter 不消费竞价列);BT-04 公式与 missing 口径。
5. **结构阻断(必须修)**:指纹不含湖覆盖态 → 回填后重跑 reused=True 静默保留旧数据。**已实测确认**。
6. **诚实框架**:0.04%→X% 中 X = 回填成功 symbol/5537;部分失败如实 partial;eod hits 不变但 covered 翻转是「列可得性」语义,非命中变化。

---

## 5. 建议 (Recommendations)

### 最小代码 delta(重跑侧,单 phase 可落地)

1. **[必做] 指纹加湖覆盖摘要** — `_compute_run_id`(auction_backtest.py:614-640)blob 追加湖覆盖态(如 `auction_symbol_count` + `len(auction_enabled_dates)`,或 coverage.symbols 的 JSON 摘要),使回填后重跑得到新 run_id 并正常落盘。先例就在同函数注释:624-628「symbols 纳入哈希…防幂等跳过遮蔽小宇宙运行」——同一理由扩展到湖覆盖。实现注意:run_id 在步骤 ⑤ 计算,湖 symbol 数在步骤 ⑦ 才扫;把 run_id 计算移到 coverage 之后(或步骤 ④ 后先算轻量湖摘要:enabled_dates 已知 + 分区 symbol 扫 0.31s)。
2. **[必做] 测试增量** — test_full_backtest_deterministic_run_id_idempotent(test_auction_backtest.py:357)补一条:同输入不同湖覆盖 → 不同 run_id;同湖重跑 → 仍幂等 reused。
3. **[可选] `--force` 逃生门** — CLI 加 `--force` 透传 `_persist_run(force=True)`(绕过指纹检查重写),作为操作员兜底;推荐与 1 并存(1 是主语义,force 是手动刷新)。

### 执行建议

- **顺序**:R1 回填完成 → 本 delta(指纹+测试)→ `python backend/scripts/auction_backtest.py --range 248` 全市场重跑(5-10s)→ 核对 coverage.symbols X% 与 4 个列门控策略新 hits。
- 重跑产物即 BT-07 全量真列底座,Phase 34 Run B(12 行)的语义升级版。
- 无需 API/job 面:CLI-only 现状维持(回测快,无单飞冲突;回填 job 的单飞是 R1 的事)。

---

## 6. 风险 (Risks)

| # | 风险 | 等级 | 缓解 |
|---|---|---|---|
| 1 | **指纹陈旧**:回填后重跑 reused=True 保留旧数据(已实测) | **高(阻断)** | 指纹加湖覆盖摘要(§5.1);测试锁定 |
| 2 | **intraday_confirm 语义误读**:52,591 行标 branch=real 但 filter 不消费竞价列,回填后 covered 翻转可能被误读为「竞价确认过」 | 中 | 文档+BT-10 minute_confirm=not_applied 注解已有;建议在 manifest/CLI 摘要加注「filter 未消费竞价列」 |
| 3 | **回填部分失败** → 覆盖 <100%,真列 hits 系统性偏低 | 中(诚实可控) | rows_present<expected 如实;失败 symbol 重试属 R1 职责 |
| 4 | 磁盘 | 低 | 36 MB 投影,1007G 空闲 |
| 5 | 上游(回填源)不稳定 → 湖质量 | 中(R1) | 回填 fail-closed 台账;重跑前核对 X% |
| 6 | AST 守卫漂移(delta 触碰 pool/strategy_cache) | 低 | delta 只动 backtest_results 写根;三守卫套件已实测全绿 |

---

## 7. 附录 (Appendix)

### 7.1 实测命令记录

```bash
# 宇宙/湖盘点
python -c "… kline_daily symbol n_unique = 5537 (SZ 2894/SH 2310/BJ 333); 1,326,996 rows"
python -c "… kline_auction 248 partitions, 2 symbols, 496 rows, 0.49 MB"

# 50-symbol 试点 (compute 0.8s / CLI 4.5s)
backend/.venv/bin/python backend/scripts/auction_backtest.py \
  --symbols 000001.SZ,…,920005.BJ --range 248    # → run 45fb75b65731, 2221 rows

# 全市场 9 策略 (compute 2.3s / CLI 5.3s)
backend/.venv/bin/python backend/scripts/auction_backtest.py --range 248
  # → run 1cbb901a5637, 381,690 rows (eod 329,087 + real 52,603), 10.33 MB

# 幂等重跑 (reused=True 未落盘 — 指纹缺口实证)
backend/.venv/bin/python backend/scripts/auction_backtest.py --range 248
  # → run_id 1cbb901a5637, wrote=False reused=True

# 合成分区磁盘 (142 KB @ 5537 rows → 248× ≈ 36 MB)
python -c "… write_parquet 5537-row auction partition → 142 KB (26 B/row)"

# 规模分区读 (248 × read_parquet symbol) = 0.31s
# 守卫套件: 16 + 48 passed
```

### 7.2 证据索引(核心 file:line)

- `backend/app/services/auction_backtest.py:426`(run_full_backtest)/ `:376-415`(覆盖扫)/ `:614-640`(_compute_run_id 指纹,624-628 symbols 哈希先例)/ `:712-743`(_persist_run 幂等,714-721 reused 判定)
- `backend/app/services/auction_columns.py:146-217`(attach_auction_columns_range 分区存在性主闸门)/ `:101-146`(单日双闸门)
- `backend/app/services/auction_validation.py:85-108`(_build_candidate_mask fill_null(False))/ `:255-292`(validation 侧覆盖同构)/ `:466-524`(_forward_stats BT-04 共源)
- `backend/scripts/auction_backtest.py:134-157`(全量 enriched 预载)/ `:103-113`(--strategies/--range/--symbols CLI)
- `backend/app/strategy/builtin/auction_intraday_confirm.py:42-45`(filter 仅 open_gap — 52,591 行未门控的根因)
- `backend/tests/test_auction_backtest.py:186-188`(列门控集 = fast_grab/allround/t1_flash 显式声明)/ `:357`(run_id 幂等测试,需增量)/ `:223`(BT-04 手算)
- `backend/tests/test_pool_hub.py:1005-1011`(E3)/ `backend/tests/test_preopen_ast_guard.py:22-52`(mirror)
- 消费面:`auction_recap.py:539-543,624-643` / `pool_hub.py:12-13,177-185` / `monitor_rules.py:51-52` / `indicators/pipeline.py:158-184` / `data.py:772-779` / `market_recap_auction.py:84-138` / `auction_history.py:41` / `xyz_provider.py:221`(回填 seam 已映射 `current`→`auction_virtual_price`)

### 7.3 投影标注

- 回填后列门控 4 策略 hits(千-万级)为 **[投影]**,依赖策略阈值(META 默认)与全市场竞价分布;回填完成后的实际重跑即验证。
- intraday_confirm「52,591 不变」基于其 filter 不消费竞价列(代码+测试双重确认),非推测。
