# 域陷阱:stockdb 本地源接入 + 诚实性修复 + 部署日

**项目:** AthenaQuant v2.5 · **日期:** 2026-08-07 · **模式:** 生态系统/可行性侦察(全部只读)
**范围:** (A) 接入本机 stockdb SDK 通道; (B) source_blocked 标签 + 空帧进度 emit 修复; (C) 部署日执行面
**置信度:** 高(证据锚点均为实测/源码; 仅 SD 通道 symbol/单位映射细节标 UNKNOWN)

---

## P1 [CRITICAL] 双源混写: symbol 格式 / 量单位 / 时区三者漂移 → 分区键分裂 + 值失真

**现象:** 同一 symbol+date 从两通道写入,merge-upsert 键不命中 → 同股两键行(分区"损坏"语义:读侧 fan-out、回测/选股重复计入);或同键但值口径不同 → 静默覆盖失真。

**证据链(三处已知差异,均实测/源码):**
- **symbol 格式:** stockdb 契约 `^(SH|SZ|BJ)\d{6}$`(`docs/DATA_CONTRACTS.md:146,330` normalize_symbol;实测 API 用 `SH600519`);AthenaQuant 湖为 `000001.SZ` 全后缀(xyz 回填已按此写,`backend/app/data_providers/xyz_provider.py:172-174` 明确 merge-upsert 键 [symbol,datetime] 要求后缀一致);前端自选/监控按全后缀精确匹配零归一化(`docs/features.md:42`)。SDK 通道适配器不做 `SH→.SH` 映射 → 全湖双键。
- **量单位 100×:** stockdb 日K/分钟K `volume_hand`=手(`DATA_CONTRACTS.md:132`、`API.md:277`);AthenaQuant canonical volume=股,既有 provider 显式 `×100 # 手→股`(`ifzq_provider.py:166`、`tencent_provider.py:177`、测试 `test_ifzq_provider.py:112`)。漏乘 → vol_ratio_5d / auction_volume_ratio 分母 / 换手率 / 回测成交额全面失真 100×。
- **时区:** stockdb 模型 pydantic `AwareDatetime` 拒收 naive,`bar_time` 强制 Asia/Shanghai aware(`DATA_CONTRACTS.md:356-363`);AthenaQuant 竞价湖 datetime 现为 naive(xyz `_parse_iso` 剥 `Z`,`xyz_provider.py:276-284`)。aware/naive 混写 → polars 比较/分区边界 `CAST(datetime AS DATE)` 漂移或报错。
- **09:30 bar 语义(分钟通道):** stockdb 分钟湖 09:30 bar = 集合竞价统计(09:26 撮合行重标 09:30,`eastmoney.py:741-745`、`DATA_CONTRACTS.md:384-387`);AthenaQuant 铁律"绝不把 09:30 bar 标为集合竞价数据"(`features.md:50`),BT-10 截断 `datetime.time() <= evaluation_time` 会把该 bar 计入盘中确认 → 竞价量重复计入。

**预警信号:** 湖内同 symbol 出现两种格式;日/竞价行数突增≈2×;回测 `auction_volume_ratio` 量级异常;适配器单测无「手→股 / 后缀归一 / naive 断言」用例。

**预防:** 适配器单点归一化(symbol 映射表 + volume×100 + datetime 统一 naive/aware 并写前断言),镜像 `kline_sync.py:93-132 _normalize_daily` 既有模式;写湖仍唯一经 `write_auction_partitions`(`auction_sync.py:33-35` canonical 4 列,`CHART-03` 旧4列/新6列 diagonal_relaxed 容忍);适配器契约测试锁死三差异;分钟回填仅作 09:30+ 补数,保留 bar 语义注记。

**处理 phase:** Phase A(SDK 通道接入)— 适配器归一化 + 契约测试;接入后 EOD 交互回归(`sync_and_persist_auction` 幂等 no-op)入 Phase A 验收。

---

## P2 [CRITICAL] 403-vs-真空不可区分:错误吞没链(timeout/策略块/真真空全塌缩为 empty)

**现象:** 上游 403 封锁窗内 5537 标的逐 symbol 快失败,台账全部记 `empty_response` — 与 BJ 永久缺口同标签,运维无法区分"源受阻"与"真无数据";2h 配额窗(~70-100 请求/窗,达额冷却 ~2h,实测见 `docs/deploy-verification.md` v2.4 小节)正是 36-03 事故模式。

**证据链:** `_call_tool` catch-all(`xyz_provider.py:243-247`,`raise_for_status` 抛的 httpx.HTTPStatusError 被吞)与 `get_auction` catch-all(`xyz_provider.py:192-196`)→ 空帧;`_fetch_auction` 的重试(R1)只对**异常**触发,而 provider 已把一切吞成空帧 → 重试路径对 xyz 是死代码(`auction_backfill.py:109-127`);36-03 事故实录"~symbol 33 起逐请求 403,199 条错误行,零湖写入,与 BJ 不可区分"(`.planning/phases/36-auction-full-backfill/36-03-SUMMARY.md:48-50,78`、`FA-05-BJ-STANCE.md:47-51`)。对照:本地 stockdb SDK 有类型化异常可区分(`sdk/errors.py` StockDBHTTPError.status_code / StockDBTransportError),REST 错误语义明确(`API.md:80-90`:401/403 保留/404/429+retry_after)。

**预警信号:** 全量 run 中某段连续 `empty_response` 且伴随 2-3s/请求节奏(非正常拉取耗时);`failed_symbols` 与 symbol 集合高度相关(非 BJ 号段也应失败)。

**预防:** provider 层三态化 — 传输错误 / HTTP 4xx(403 源块、429 限速带 retry_after) / 业务空(真空),各自独立标签;服务层 `failed_symbols.reason` 携带 `source_blocked` 且对"连续 N symbol 全 blocked"发告警;R1 重试改为对可重试态生效(403 配额窗不重试、只记账;429 按 retry_after 退避);新增 stockdb 通道适配器必须窄捕获类型化异常,严禁复制 `xyz_provider.py:192-196` 的 catch-all 模式。

**处理 phase:** Phase B(HON-1 source_blocked)— provider 三态 + 台账标签 + 连续失败告警;stockdb 适配器在 Phase A 即按三态写(避免二次返工)。

---

## P3 [HIGH] 空帧批量失败进度冻结 + 进度 emit 语义(取消=done/100 误导)

**现象:** 空响应分支 `continue` 在 per-symbol emit **之前**(`auction_backfill.py:286-291,295-299` 跳过 `:308` 的 emit)→ 批量失败段进度静止 0%,hub ready 探针/stall 检测误判为挂死;36-02/36-03 已实测记录该缺口(`36-02-SUMMARY.md:62`、`36-03-SUMMARY.md:79`,修复候选 = emit 移到 continue 前)。

**关联语义陷阱:**
- 取消路径 `emit("done", 100, "回填被取消")`(`auction_backfill.py:282`)— done 阶段 + 100% 进度对轮询端/探针表达"完成",与失败/取消状态矛盾(诚实性反模式)。
- `job_store.progress` 日志 200 条封顶(`pipeline_jobs.py:214-215`)— 5537 标的逐 symbol emit 只留最后 200 条,stage/progress 字段是可靠态,log 明细不可依赖。
- 幂等:`only_missing` 全跳过返回 8 键 requested=0(W-4 已修,`:245-252`);重复触发返回 `{"status":"reused"}` 无新进度 → 运营可能误判无响应(已有 job_id 轮询语义需文档化)。

**预警信号:** 任务 running 而 progress 长时间 0 且日志无异常行;或 cancelled 任务前端显示 100%。

**预防:** emit 移到 continue 之前(每 symbol 必发,含失败计数);取消路径 emit 独立 stage(如 `cancelled`/pct 保持实际进度)而非 done/100;修复加回归锁:构造全空帧批量 → 断言每 symbol 进度行出现且终态 failed 计数正确。

**处理 phase:** Phase B(HON-2 进度 emit)— 代码 + 回归测试;hub ready 探针语义随阶段同步修订。

---

## P4 [HIGH] 部署日观测遗漏:3018 容器重建 / 数据卷权限 / 200-body / 分钟点亮误判

**现象:** 部署日把"容器起来了"当"系统对了",四类遗漏:
1. **陈旧容器:** 运行中 3018 容器落后 HEAD(image 2026-08-04 vs HEAD 08-07,4 运行时文件 md5 全 DIFFER,root-owned 不可触碰 — `docs/deploy-verification.md:206-215`、`.planning/ROADMAP.md:130`)。重建后不验 md5 parity → 旧代码仍在服务。
2. **数据卷/权限:** `docker-compose.yml:25-36` 注释自证 — 不强制 `DATA_DIR=/app/data` 时 `up --build` 重建即丢数据;bind mount `./data` 若容器以 root 写 → host 文件 root 属主,后续清理/备份受阻(3018 现容器即 root-owned 先例)。
3. **新端点 200-body 验证遗漏:** v2.4 沙箱预检只证"路由在场 + 401 门"(`.planning/milestones/v2.4-MILESTONE-AUDIT.md:70`),200-body 明确 defer 到部署日;FastAPI 空态约定是 200 `{available:false}`(`features.md:49`)— 只验状态码会放过"错误体 200"。
4. **分钟点亮误判:** 真点亮 = 15:30 EOD 同步后 `kline_minute/date={T}/part.parquet` 存在 **且** `auction_intraday_confirm` 命中非空,**非盘中 09:45**(`deploy-verification.md` D8 bullet);盘中看或只看分区存在(空分区)都误判。
5. **新通道连通性/凭证(v2.5 新增):** 本地 stockdb 服务在 host `127.0.0.1:8000`,容器内 loopback 不通(compose 无 host 网络);实测所有请求 401(`{"error":"unauthorized"}`)— AthenaQuant `.env` 无 `STOCKDB_API_KEYS`。部署日不解决 → SDK 通道"配置好了但永远 401/拒连"。

**预警信号:** `docker exec <cid> md5sum` 与 HEAD 不符;data/ 下文件属主 root 且非预期;端点返回 200 但 body 为错误形状;分钟功能在盘中测出"未点亮"。

**预防:** D 系 runbook 逐项:重建前记 3018 容器 md5 基线 → 重建后 parity 4/4;卷内权限用 compose user/`chown` 明确;每个新端点部署日 curl 断言 200+body 键形状(镜像既有空态契约);分钟点亮观测时间窗写死 15:30 后;stockdb 通道连通性 = 容器内 curl host 网关 + API key 注入(env,不入 git)+ 401→`source_blocked` 语义。

**处理 phase:** Phase C(部署日 D1..D8)— runbook + 预检脚本化;凭证/网络两前置项须在 Phase A 的配置文档中先定。

---

## P5 [MEDIUM] 回测 run_id 指纹是内容级空洞:同 symbol 行值被覆盖 → digest 不变 → 幂等复用陈旧

**现象:** 湖覆盖 digest 仅 `(auction_symbol_count, auction_enabled_dates)`(`services/auction_backtest.py:549-555,676-690`)。stockdb 通道对**已覆盖 symbol** 补/改行值(symbol 数、日期数不变)→ 同 run_id → `reused=True` 静默保留旧结果(RC-01 只修了"数量变化"缺口,`:676-678` 自述)。

**预警信号:** 通道切换/回填后重跑回测返回 `reused=True`,而湖内行值已变;coverage 报告与 digest 分量恒等(symbol 数)但 row 内容不同。

**预防:** digest 升级为内容级(每分区行数总和 或 分区 parquet 内容 hash,扫描成本可控:248 分区 × 5.2k 行);或通道来源变更(origin=stockdb)时强制新 run_id;保留 `--force`(RC-04 escape hatch)但 provenance 记录 rewritten_at。

**处理 phase:** Phase A 验收内(通道首回填后回测复验,RC-02 重跑);digest 升级为独立小任务放 Phase B 或紧随接入后。

---

## P6 [MEDIUM] SDK 上游变更风险:活跃演进、无版本锚、零新增依赖约束

**现象:** stockdb 是并行演进项目(docs/data 今日 mtime),SDK 面(`sdk/client.py` 方法签名、`contracts/schemas.py` 字段、`sdk/errors.py` 异常类)变更即静默破坏适配器;AthenaQuant `backend/pyproject.toml:8-36` 无 stockdb 依赖 — "零新增运行时依赖"约束下需先定接入形态(REST-only 适配器经 httpx,或 editable 安装,或冻结快照 vendor)。另:stockdb 2027 交易日历为**未核对投影**(`DATA_CONTRACTS.md:30-35`,不得用于回测/时序)— 适配器/回填绝不能消费该日历做窗口对齐(AthenaQuant 现用 kline_daily 物理分区对齐,`auction_backfill.py:202-214`,保持)。

**预警信号:** stockdb 侧 commit/发布后 AthenaQuant 适配器测试红;REST 响应新增/改名 field 未被 schema 校验捕获;回填日期集与权威日历出现单日漂移。

**预防:** 接入 phase 锁定 stockdb 修订号(manifest 记录 identity/revision,镜像 `docs/UPSTREAM-SYNC.md` 纪律),适配器窄捕获类型化异常并做响应 schema 校验(未知字段 fail-closed,诚实缺列不 0 填);契约测试镜像 stockdb `contracts/schema_registry.py` 的 schema_version 语义;日历一律用 AthenaQuant 物理分区/权威源,不引 stockdb calendar。

**处理 phase:** Phase A(形态决策 + 版本锚 + 契约测试);日历纪律在 Phase A 文档与 Phase B 回填窗口对齐逻辑各守一次。

---

## 风险排序汇总

| 序 | 陷阱 | 等级 | 处理 phase | 关键证据 |
|---|---|---|---|---|
| P1 | 双源混写 symbol/单位/时区漂移 | CRITICAL | A(适配器) | DATA_CONTRACTS.md:146,330,132; ifzq_provider.py:166; xyz_provider.py:172-174,276-284 |
| P2 | 403-vs-真空不可区分(吞错链) | CRITICAL | B(HON-1) | xyz_provider.py:192-196,243-247; 36-03-SUMMARY.md:48,78 |
| P3 | 空帧进度冻结 + 取消=done/100 | HIGH | B(HON-2) | auction_backfill.py:286-299,282; pipeline_jobs.py:214-215 |
| P4 | 部署日观测遗漏(重建/卷/200-body/点亮/凭证) | HIGH | C(D 系) | deploy-verification.md:206-215; docker-compose.yml:25-36; MILESTONE-AUDIT.md:70 |
| P5 | 回测指纹内容级空洞 | MEDIUM | A 验收 | auction_backtest.py:549-555,676-690 |
| P6 | SDK 上游变更/日历投影 | MEDIUM | A(锚定) | pyproject.toml:8-36; DATA_CONTRACTS.md:30-35; UPSTREAM-SYNC.md |

## 建议给下游消费者(roadmap/synthesizer)
- Phase 结构: A(SDK 通道接入,含 P1/P5/P6 前置)→ B(两个诚实性修复,含 P2/P3)→ C(部署日,含 P4);P1 的归一化契约测试是 A 的**硬验收**,P2 三态化是 B 的**硬验收**。
- 新增观测项: stockdb 服务连通性(容器内 host 网关 + API key)+ 401 语义映射,须进 Phase C runbook 前置检查。
- 探测结论[实测]: 本地 stockdb 无独立竞价端点(openapi 37 路由无 auction;竞价仅以分钟 09:30 统计语义存在)→ SDK 通道是日K/分钟/实时旁路,竞价回填仍受 xyz 配额窗约束(campaign 40/5537 持续)。(适配器 symbol/单位映射细节 UNKNOWN,须 Phase A 探测确认。)
