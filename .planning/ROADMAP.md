# Roadmap: AthenaQuant

## Milestones

### v1.0 MVP — shipped 2026-07-27

Five phases delivered the governed data and portfolio loop, deterministic decision safety, reproducible factor and strategy research, evidence-grounded AI analysis, controlled advanced workflows, and independently activatable Shadow, Thesis, and Forecast modules.

Archive:

- [v1.0 roadmap](./milestones/v1.0-ROADMAP.md)
- [v1.0 requirements](./milestones/v1.0-REQUIREMENTS.md)
- [v1.0 milestone audit](./milestones/v1.0-MILESTONE-AUDIT.md)
- [v1.0 phase artifacts](./milestones/v1.0-phases/)

---

### v1.1 Operational Hardening — shipped 2026-07-29

Four phases hardened the shipped MVP: reproducible release evidence, validation hygiene (zero application-code warnings), verified optional-model supply path, and visual regression baselines.

Archive:

- [v1.1 roadmap](./milestones/v1.1-ROADMAP.md)
- [v1.1 requirements](./milestones/v1.1-REQUIREMENTS.md)

---

### v1.2 End-to-End Factor Portfolio Pipeline — shipped 2026-08-03

Six phases extended the research platform from single-factor evaluation into an auditable factor → portfolio → risk → walk-forward → rebalance-suggestion pipeline with zero execution authority.

Archive:

- [v1.2 roadmap](./milestones/v1.2-ROADMAP.md)
- [v1.2 phase artifacts](./milestones/v1.2-phases/)

---

### v1.3 竞价选股引擎 — shipped 2026-08-04

Four phases add 集合竞价-driven quantitative stock selection to the shipped screener engine: an auction data layer, an auction strategy family, a pool hub with cross-resonance, and guest/VIP masking plus the frontend pool page — all research-only, zero execution authority.

### v2.0 竞价深度与历史股池 — planning

四个阶段深化已落地的 v1.3 竞价选股引擎：probe 门控的真实集合竞价数据列（竞价量/金额）作为受管增强列落盘到按日分区数据湖、六策略竞价/尾盘策略族、按交易日浏览历史股池的冻结式点快照与独立只读日期端点、以及 DateNavigator 前端——数据优先构建顺序，全部研究建议零执行权。

## Phases

**Phase Numbering:**

- v1.2 ended at Phase 15; v1.3 continues at Phase 16 (`phase_naming: sequential`)
- v1.3 ended at Phase 19; v2.0 continues at Phase 20

- [x] **Phase 16: 竞价数据层 (Auction Data)** - Enable minute-K sync, land the governed open-gap factor, and probe true 集合竞价 match data behind a capability gate — DATA-01..03
- [x] **Phase 17: 竞价策略族 (Auction Strategy Family)** - Author ≥3 auction strategies (竞价多头/盘前强势量化/早盘之星) as builtin strategy files with factor-hit tagging — STRAT-01..03 (completed 2026-08-04)
- [x] **Phase 18: 股池 Hub (Pool Hub)** - Strategy cards with pool counts, drill-down stock lists, concept filter, 交叉共振 multi-hit highlight — POOL-01..03 (completed 2026-08-04)
- [x] **Phase 19: 游客/VIP 脱敏 + 前端 (Guest Access & Frontend)** - Server-authoritative guest masking, VIP plaintext, frontend pool page — GUEST-01..02 (completed 2026-08-04)
- [ ] **Phase 20: 竞价数据层 (Auction Data)** - Probe 门控的真实集合竞价列（竞价量/金额）作为受管增强列 + `kline_auction/date=*/` 湖 + 派生未匹配金额 proxy — DATA-04..06
- [ ] **Phase 21: 竞价策略族 (Auction Strategy Family)** - 六个第一性原理竞价/尾盘策略（极速抢筹/竞价阿尔法/金色两点半/竞价全面/T+1闪电/盘中确认）作为 builtin 内置策略、诚实命名与时间窗 — STRAT-04..09
- [ ] **Phase 22: 股池日期导航 (Pool Hub Date Navigation)** - 冻结式点快照按日股池 + 独立只读日期/as_of 端点 + 盘后 EOD 持久化 job — POOL-04..06
- [ ] **Phase 23: 前端 (Frontend)** - DateNavigator 按交易日浏览 + 竞价列展示（真实 vs 派生）与诚实 probe/窗口状态 — FRONT-01..02

## Phase Details

### Phase 16: 竞价数据层 (Auction Data)

**Goal**: Researchers can sync minute-K without corrupting the daily lake, compute and persist a governed open-gap factor, and know — via an honest capability probe — whether true 9:15–9:25 集合竞价 match data is available before committing strategy breadth.
**Depends on**: v1.2 completion (Phase 15)
**Requirements**: DATA-01, DATA-02, DATA-03
**Success Criteria** (what must be TRUE):

  1. Researcher can enable minute-K sync and verify 1m bars land in `kline_minute` Parquet with correct 09:30+ timestamps; existing daily-K partitions are unchanged.
  2. Researcher can compute 开盘涨幅 (`open / prev_close − 1`) as a governed column, unit-tested on a known fixture and consumed by strategy filters.
  3. Researcher can run the auction-data probe and observe the verdict (available / fail-closed to derived factors); when unavailable, no UI or strategy labels the 09:30 bar as auction data.

**Plans:** 2/2 plans complete

Plans:

- [x] 16-01-PLAN.md — Minute-K sync enable + verify, symbol scoping, 09:30 timestamp convention (DATA-01)
- [x] 16-02-PLAN.md — Governed open-gap factor + auction-data probe & honest fail-closed labels (DATA-02, DATA-03)

### Phase 17: 竞价策略族 (Auction Strategy Family)

**Goal**: Researchers can run at least 3 first-principles auction strategies (竞价多头, 盘前强势量化, 早盘之星) as builtin strategy files auto-discovered by the engine, each reporting per-stock factor hits without adding a third registration track.
**Depends on**: Phase 16 (open-gap factor)
**Requirements**: STRAT-01, STRAT-02, STRAT-03
**Success Criteria** (what must be TRUE):

  1. At least 3 auction strategies exist in `strategy/builtin/`, appear in the screener strategies API, and return stock pools with 开盘涨幅/涨跌幅.
  2. Each strategy exposes factor-hit tags so a results row can report 关联因子 (which strategies hit it).
  3. No new strategy registry exists; auction strategies are discovered from the builtin dir and the strategies API dedups against `PRESET_STRATEGIES`.

**Plans:** 2/2 plans complete

Plans:

- [x] 17-01-PLAN.md — 3 first-principles auction strategies (竞价多头/盘前强势量化/早盘之星) as builtin files + engine discovery + PRESET_STRATEGIES dedup (STRAT-01, STRAT-03)
- [x] 17-02-PLAN.md — 关联因子 factor-hit tagging contract + screener run_all wiring (STRAT-02)

### Phase 18: 股池 Hub (Pool Hub)

**Goal**: Users can open a pool hub showing strategy cards with per-day pool counts, drill into each strategy's stock list (code, 开盘涨幅, 涨跌幅, 概念板块, 关联因子), filter by 概念, and highlight 交叉共振 — all research-only.
**Depends on**: Phase 17 (strategy results)
**Requirements**: POOL-01, POOL-02, POOL-03
**Success Criteria** (what must be TRUE):

  1. User can open the pool hub and see strategy cards with当日 pool counts and drill into a per-strategy stock list backed by `screener_results/` persistence with a single as_of source of truth.
  2. User can filter the pool by 概念 and see 交叉共振 (stocks hit by multiple auction strategies) highlighted.
  3. No execution authority exists anywhere in the pool feature — no API endpoint, UI affordance, or service path can push a pool to a live broker.

**Plans:** 2/2 plans complete

Plans:

- [x] 18-01-PLAN.md — pool hub projection service + read-only GET /api/pool/hub + concept filter + 交叉共振 + zero-execution guard (POOL-01, POOL-02, POOL-03)
- [x] 18-02-PLAN.md — 股池 PoolHubPage: strategy cards, drill-down stock list, concept filter, 交叉共振 highlight, POOL-03 no-execution UI guard (POOL-01, POOL-02, POOL-03)

### Phase 19: 游客/VIP 脱敏 + 前端 (Guest Access & Frontend)

**Goal**: Guests see only 涨跌幅 and 概念板块 with stock code/name masked server-authoritatively; VIP sessions see明文; the frontend pool page composes cards, lists, filtering, and resonance into one workspace.
**Depends on**: Phase 18 (pool hub API)
**Requirements**: GUEST-01, GUEST-02
**Success Criteria** (what must be TRUE):

  1. Guest session responses mask stock code/name (`******`) at the API DTO boundary and expose only 涨跌幅/概念板块; VIP responses are明文. No client-side masking is trusted.
  2. Masking is display-only — underlying factor computation and strategy results remain unmasked and correct for all sessions.

**Plans:** 2/2 plans complete

- [x] 19-01-PLAN.md — server-authoritative guest masking at the GET /api/pool/hub DTO boundary: guest session → masked code/name/symbol + `mode` field + guest read-only access path; VIP 明文; display-only GUEST-02 (GUEST-01, GUEST-02)
- [x] 19-02-PLAN.md — PoolHubPage guest presentation: GuestModeBanner, masked-cell rendering verbatim, 名称 column, guest column set hides 开盘涨幅, no client-side masking (grep guard) (GUEST-01, GUEST-02)

### Phase 20: 竞价数据层 (Auction Data)

**Goal**: 研究者可以把真实 09:15–09:25 集合竞价撮合数据（竞价量/竞价金额）作为受管增强列持久化，经 `auction_sync` 落盘到 `kline_auction/date={d}/` 分区湖；整条生产路径以 auction probe 判定为前置——不可用时缺列并 fail-closed 回退到派生 `open_gap`，绝不静默填充，也绝不把 09:30 连续竞价 bar 标为集合竞价数据。
**Depends on**: v1.3 completion (Phase 19)
**Requirements**: DATA-04, DATA-05, DATA-06
**Success Criteria** (what must be TRUE):

  1. probe 判定 `available` 时，研究者能在日线帧上看到受管增强列 `auction_volume`（竞价量）与 `auction_amount`（竞价金额，canonical 单位股/元）；probe 非 `available` 时这些列缺席，功能 fail-closed 回退到派生 `open_gap`，从不静默填充。
  2. `auction_sync` 服务把真实 09:15–09:25 竞价窗口行按 `date=` hive 分区写入 `kline_auction/` 湖；湖内只存真实竞价窗口行，09:30 连续竞价 bar 被结构上排除（回归锁死）。
  3. 委托量输入可得时，研究者能查看派生的竞价未匹配金额（unmatched-order proxy）列；输入不可得时策略回退到量比 + 金额强度。
  4. probe 非 `available` 时，研究者无论在策略还是 UI 上都看不到竞价列，只能看到派生列与 `open_gap`；没有任何 UI 或策略把 09:30 bar 标为集合竞价数据。
**Plans**: TBD
**Research flag**: 需要 `--research-phase` — DATA-04 数据源可用性探测与虚拟成交（`auction_virtual_fill`）字段语义是本期最大不确定项，规划前先做 probe 探测。

### Phase 21: 竞价策略族 (Auction Strategy Family)

**Goal**: 研究者可以运行六个第一性原理策略族——极速抢筹、竞价阿尔法、金色两点半、竞价全面策略、T+1闪电、盘中确认——全部作为 `strategy/builtin/` 内置策略自动发现，诚实命名、声明可计算时间窗，缺列时整池 fail-closed 为空。
**Depends on**: Phase 20 (auction columns)
**Requirements**: STRAT-04, STRAT-05, STRAT-06, STRAT-07, STRAT-08, STRAT-09
**Success Criteria** (what must be TRUE):

  1. 研究者可以运行极速抢筹（STRAT-04）——竞价量比 + 竞价金额 + 盘前涨幅甜点区（2.8%–3.5%、>7% 风险带）过滤，作为 `strategy/builtin/` 内置策略且命名诚实。
  2. 研究者可以运行竞价阿尔法（STRAT-05）——probe `available` 时消费真实竞价列，否则 fail-closed 回退到派生因子（`open_gap` + 量比/金额强度）。
  3. 研究者可以运行金色两点半（STRAT-06），命名/描述诚实归类为尾盘/隔夜策略（T 日涨幅 3%–5% + 14:30 尾盘分钟确认、次日持有），从不混入竞价窗口。
  4. 研究者可以运行竞价全面策略（STRAT-07）、T+1闪电（STRAT-08，次日早盘分钟 K 卖出确认）与盘中确认（STRAT-09，09:30–10:00 分钟帧截断到 `evaluation_time`，绝不 lookahead）(P2)。
  5. 每个策略声明可计算时间窗（pre_open/intraday/post_close）且所需列缺席时返回空池（fail-closed）；策略仅经 `strategy/builtin/` 自动发现，无第三条注册轨道（STRAT-03 不变）。
**Plans**: TBD
**Research flag**: 中等 — 第一性原理因子阈值（量比/甜点区/金额强度）需按 A 股历史校准；STRAT-09 的 `eval_time` 截断与 `time_factor` 折算规约需要规划研究。

### Phase 22: 股池日期导航 (Pool Hub Date Navigation)

**Goal**: 用户可以按交易日浏览历史股池——每次 `run_all` 的行集以冻结式点快照（`as_of` + `computed_at` + 策略版本指纹）持久化到 `screener_results/date={as_of}/`，经独立只读端点列出日期与按 as_of 取池，并由盘后 EOD job 预生成保证自给自足；绝不落 `today_ever_rows` union，也不破坏既有 single-as_of 契约。
**Depends on**: Phase 21 (per-day strategy run_all)
**Requirements**: POOL-04, POOL-05, POOL-06
**Success Criteria** (what must be TRUE):

  1. 用户能打开任意历史交易日的股池并看到该日 `run_all` 的精确冻结行集——快照携带 `as_of` + `computed_at` + 策略版本指纹并落 `screener_results/date={as_of}/`；`today_ever_rows` union 永不作为点快照被持久化或展示。
  2. 用户能经 `GET /api/pool/dates` 列出可用股池日期，并经独立只读端点以 `as_of=YYYY-MM-DD` 取回当日股池；既有 `GET /api/pool/hub` 的 single-as_of 契约保持原样（回归锁死）。
  3. 每个交易日股池由盘后定时 `run_all` job 自动持久化，历史浏览自给自足——首个历史日请求不会被请求内重算阻塞。
  4. 全部 `/api/pool/*` 保持只读且零执行权（POOL-03 AST 守卫扩展），无任何端点/job 能把股池推向实盘。
**Plans**: TBD
**Research flag**: 需要 `--research-phase` — 历史回填策略（EOD 预生成 job vs 首日一次性后台回填）与概念板块 PIT 的历史 ext 分区缺口需要细化。
**UI hint**: yes

### Phase 23: 前端 (Frontend)

**Goal**: 用户可以用 DateNavigator 按交易日浏览股池（‹ › 步进 + 日期列表 + as_of 重取 + 非交易日禁用 + 无数据日诚实空态），并在股池钻取中查看竞价列——真实集合竞价 vs 派生虚拟成交分开标注（股/元单位），盘前/空态诚实展示 probe/窗口状态。
**Depends on**: Phase 22 (pool dates + as_of API)
**Requirements**: FRONT-01, FRONT-02
**Success Criteria** (what must be TRUE):

  1. 用户能用 DateNavigator 的 ‹ › 步进与日期列表（数据源 `GET /api/pool/dates`）逐交易日浏览股池，每次步进触发 as_of 重取并刷新卡片计数与钻取明细。
  2. 非交易日被禁用且不静默跳日；无快照的日期显示诚实的空态/状态文案，而非误导性的零池。
  3. 用户在股池钻取中能看到竞价列（竞价量/金额），真实集合竞价列与派生/虚拟成交列明确分开展示并标注单位（股/元）。
  4. probe 非 `available` 或盘前时，UI 诚实展示 probe/窗口状态（fail-closed 空态或派生标注），绝不暗示存在真实竞价数据。
**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 16 → 17 → 18 → 19 → 20 → 21 → 22 → 23

| Phase | Requirements | Status |
|-------|-------------|--------|
| 16. 竞价数据层 | DATA-01..03 | Complete    |
| 17. 竞价策略族 | STRAT-01..03 | Complete    |
| 18. 股池 Hub | POOL-01..03 | Complete    |
| 19. 游客/VIP 脱敏 + 前端 | GUEST-01..02 | Complete    |
| 20. 竞价数据层 | DATA-04..06 | Not started |
| 21. 竞价策略族 | STRAT-04..09 | Not started |
| 22. 股池日期导航 | POOL-04..06 | Not started |
| 23. 前端 | FRONT-01..02 | Not started |

---
*Last updated: 2026-08-04 — v2.0 roadmap created (Phases 20-23), continuing from v1.3 Phase 19*
