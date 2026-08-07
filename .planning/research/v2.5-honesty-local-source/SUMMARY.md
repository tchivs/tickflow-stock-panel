# Project Research Summary

**Project:** AthenaQuant v2.5 — 诚实加固与本机数据源接入
**Domain:** 受管数据源通道（本机 stockdb 本地源）+ 数据诚实性加固 + 部署日观测
**Researched:** 2026-08-07
**Confidence:** HIGH

## Executive Summary

AthenaQuant 是自托管的 A 股个人量化研究平台；v2.5 里程碑要做三件事：(A) 接入本机 stockdb 数据源（服务已在 :8000 运行，SDK 位于 `../stockdb/src/stockdb/sdk/`）作为受管通道——若其提供竞价撮合明细则解除上游 xyz MCP ~2h 配额窗 gate，否则至少为日 K/实时行情提供本地旁路；(B) 修复两个记录在案的诚实性缺口（上游 403 源块与 BJ 真空无法区分 → `source_blocked` 标签；空帧批量失败进度冻结 → 逐 symbol 进度 emit）；(C) 把 D1..D8 真实交易日观测窗口 runbook 化。**研究结论：本机 stockdb 没有任何竞价端点**（openapi 41 个 `/v1/*` 路径无 auction，源码 grep "auction" 仅 9 处注释语义，09:26 撮合行被重标 09:30 折入分钟 bar）→ **竞价源仍只能是 xyz 配额窗，FA-04 全量回填不能立即解锁**（历史逐笔不可得，分钟湖仅 16 文件）；stockdb 通道的真实价值是**日 K 深度+复权（读取时计算）与分时/实时本地旁路，零配额**，以及 T-day 竞价窗口快照（09:15-09:25 逐秒，超越 xyz 单行）。

推荐做法：**通道形态 = HTTP 适配器（零新增运行时依赖），不做进程内 SDK import**。AthenaQuant 运行时是 CPython 3.11（backend/.venv 实测），stockdb `requires-python >=3.12` 且 `sdk/stream.py:30` 用 PEP 695 `type` 别名 → `import stockdb` 在 3.11 直接 SyntaxError（已实测）；且 `StockDBClient` 本身就是 httpx HTTP 客户端，进程内嵌入零数据面收益。新 provider 镜像 `free_stockdb_provider.py` 的 httpx 模式，命名 `local_stockdb`（`free_stockdb` 已被远端 C++ 服务占用）注册进 `data_providers/chain.py` 的 `_BUILTIN_CHAIN`。诚实性修复是纯 AQ 内两处小改动（xyz_provider 三态化 + backfill fail-closed 路径补 emit），与通道接入互相独立、可并行。

关键风险按序：**P1 [CRITICAL] 双源归一化漂移**（symbol 格式 `SH600519` vs `600519.SH`、量单位手→股 ×100、时区 aware vs naive，三者任一漏归一 → 分区键分裂/值失真 100×）；**P2 [CRITICAL] 403-vs-真空不可区分**（吞错链把 timeout/策略块/真真空全塌缩为 `empty_response`，36-03 事故模式）；**P4 [HIGH] 部署日观测遗漏**（3018 陈旧容器、数据卷 root 属主、新端点只验状态码不验 body、分钟点亮时间窗误判、stockdb 凭证/连通性未配）。缓解：适配器单点归一化 + 契约测试锁死三差异（Phase A 硬验收）；provider 层三态化 + `source_blocked` 台账标签（Phase B 硬验收）；D 系 runbook 逐项脚本化（Phase C）。

## Key Findings

### 通道形态与栈（STACK.md）

- **HTTP 适配器零新增依赖**：httpx 0.28.1 / pydantic 2.13.4 已在 backend deps，SDK import 面（httpx+pydantic+websockets）其余重型服务端依赖不触碰；**不裸装 stockdb、不写进 pyproject dependencies / `[tool.uv.sources]`**。
- **Python 3.11 vs 3.12 是唯一硬阻断**：SDK `stream.py:30` PEP 695 语法 + `sdk/__init__.py` 无条件 import → `import stockdb` 于 3.11 实测 SyntaxError。若里程碑坚持「接入 SDK 本体」而非 HTTP 适配器，须先升级 3.12（重建 venv、Dockerfile `python:3.12-slim`、dev.sh/CI 同步、解除 scipy `<1.18` 上限说明），并以 `uv pip install -e ../stockdb --no-deps` 安装；拒绝升级 → 只能 vendoring/薄 client 备选，且需声明「未接入 SDK 本体」。
- **集成 seam 已定位**：`MarketDataProvider` protocol（base.py:24-48）+ `_BUILTIN_CHAIN`（chain.py:22-27）+ `_get_provider` 单例工厂；能力声明 `ProviderCapabilities(auction=False, ...)` **诚实声明无竞价能力**，不进 auction_probe 链；不走 custom-source YAML（那是 GenericHTTPProvider 的 HTTP JSON 形态）。
- **鉴权/限频**：stockdb 全端点 X-API-Key 必选（无 key/假 key 均实测 401，无 loopback 豁免），常数时间比较 + key_hash 审计；限频 slowapi + 内核 token bucket：quotes 300/min、**daily/minute/intraday 120/min、ticks 60/min**，429 带 Retry-After。
- **部署日栈需求 = 零**：诚实修复（三态标签 + 空帧 emit）与部署日脚本均基于现有 polars/httpx/stdlib。

### 能力面（FEATURES.md）

**竞价可得性（核心问题①）——三层结论：**
- **T-day 可用**：tick 湖含 `09:25:00` 真实撮合行（price/vol_hand/num_trades，对账闭合 17300×1308.66=22,639,818=intraday 09:30 bar amt）；09:15-09:24 为 3s 快照级**虚拟匹配量**（num_trades=0），非逐笔。
- **历史部分可用**：分钟 `09:30 bar` = 集合竞价统计（量/额），但分钟湖极稀疏（16 文件，600519 仅 2026-08-05）→ 解锁历史竞价需先扩分钟湖（`backfill-minute`，Tushare stk_mins）。
- **历史逐笔不可得**：tick 无历史回填（免费源历史分笔不可得，TDX 仅交易时段）→ **FA-04 全量回填不能立即解锁**；解锁路径 = 自 T-day 逐日累积或先扩分钟湖。DATA-06 派生输入（unmatched_volume/virtual_price）语义映射 UNKNOWN，需 probe 不猜测。

**Table stakes（通道必备）**：鉴权+限频纪律（X-API-Key + slowapi，429 语义完整）；诚实缺失语义（空=本地无非异常、adjust 因子缺失显式 ValueError）；历史日 K+复权（600519=4024 行 ≈2005 起，qfq/hfq 读取时纯函数）；实时快照/分时；SDK 类型化客户端（连接复用/ETag 304/重试）。

**Differentiators（相对 xyz）**：T-day 竞价窗口快照（09:15-09:24 + 09:25 撮合，多 num_trades，需 sidecar 盘中定时采集）；分钟 09:30 bar = 历史竞价统计路径；复权读取时计算（湖不被污染）；本地旁路零配额（解除 xyz 2h 窗依赖）；回填节奏估算：5537 标的走 minute 09:30 bar 路径 120/min ≈46min（远优于 xyz 数周 campaign）。

**Anti-features（显式不建）**：09:15-09:24 委托统计入 canonical 湖（虚拟量非成交，湖只收 09:25 撮合行）；分钟 09:30 bar 标为「逐笔」（是聚合统计）；宣称 stockdb 解锁全量历史竞价回填；daily amount=null 当错误；伪造 tick 历史回填；BJ 缺口与 403 配额吞同标签（即 HON-1 待修）。

### 架构落点（ARCHITECTURE.md）

**新组件（2 个）**：
1. `backend/app/data_providers/stockdb_provider.py` — HTTP 适配器（镜像 FreeStockDBProvider）：`name = "local_stockdb"`；capabilities 按服务端真实能力声明、`auction=False` 诚实声明；X-API-Key header-only（禁 URL 传参，镜像 CR-02 纪律）；复用 `sleep_between_batches` 对齐服务端限频档位。
2. `backend/app/config.py` — 新 settings：`local_stockdb_url`（默认 `http://127.0.0.1:8000`，镜像 free_stockdb_url）+ `local_stockdb_api_key`（env 注入，不入 git；**建议专用 AthenaQuant key** → 限频桶隔离 + 审计归因）。

**修改（5 处）**：
1. `chain.py` — `_get_provider` 新增 `local_stockdb` 分支 + lazy singleton + `_BUILTIN_CHAIN` 插槽（daily/minute 链首，受管源优先，位置可配置为决策点）。
2. `xyz_provider.py:189-198 / :228-250` — 把 HTTP 403/配额窗 markers 分类为 policy-block 信号（typed 异常或带 reason 空帧），其余网络错误保持「空帧不抛」契约（test_xyz_provider.py:126-137 依赖）。
3. `services/auction_backfill.py` — 台账 reason 第三类 `"source_blocked"`（两键形状 {symbol,reason} 不变，与 empty_response / str(e)[:200] 互斥）；**所有 fail-closed 提前返回（行 200/224/228/266/268）补终态 emit** —— 这是「进度冻结」的真因（逐 symbol emit 自 733b650e 起已在循环内 :308-313，勿重复实现；里程碑所指 283-296 行号已过期）。
4. `services/auction_probe.py` — preflight 遇 policy-block → verdict fail_closed + detail="source_blocked"。
5. `scripts/auction_backfill.py` — CLI 接 on_progress 打 stderr（现零进度输出）。

**数据流**：竞价流不变（源仍 xyz，变更仅在失败分类与终态 emit）；daily/minute 流新增通道进链首 gap-merge 走既有 `kline_sync` 写路径；湖仍无 provenance 列（铁律），通道身份进台账/终态 dict。**双源分区守卫现有机制已覆盖**（单源选择 `_first_auction_provider` + run-slot 互斥 + merge-upsert 幂等 + 原子 rename），本轮竞价零新守卫。

### 风险与陷阱（PITFALLS.md）

1. **P1 [CRITICAL] 双源混写：symbol 格式/量单位/时区三者漂移** → 分区键分裂（同股两键）+ 值失真 100×。预防：适配器单点归一化（`SH600519→600519.SH` 映射 + volume×100 + 统一 naive/aware 并写前断言，镜像 `kline_sync.py:93-132 _normalize_daily`），契约测试锁死三差异；写湖唯一经 `write_auction_partitions`。
2. **P2 [CRITICAL] 403-vs-真空不可区分（吞错链）** → 36-03 事故模式：5537 标的 2h 窗逐请求 403 全记 `empty_response`，与 BJ 永久缺口不可区分；且 provider 吞空使 R1 重试变死代码。预防：provider 层三态化（传输错误/HTTP 4xx 含 retry_after/业务真空）+ `source_blocked` 标签 + 连续 N symbol 全 blocked 告警；R1 重试只对可重试态生效；stockdb 适配器窄捕获类型化异常，严禁复制 catch-all 模式。
3. **P3 [HIGH] 空帧批量失败进度冻结 + 取消=done/100 误导**。预防：fail-closed 提前返回路径补终态 emit（真冻结点）；取消路径独立 stage（cancelled/实际 pct）而非 done/100；回归锁：全空帧批量 → 断言每 symbol 进度行 + 终态 failed 计数。
4. **P4 [HIGH] 部署日观测遗漏**：3018 容器落后 HEAD（4 运行时文件 md5 全 DIFFER，root-owned）；数据卷权限（compose 不强制 DATA_DIR 时重建丢数据）；新端点只验 401 门不验 200-body；分钟点亮误判（真点亮 = 15:30 EOD 后分区存在 **且** auction_intraday_confirm 非空，非盘中 09:45）；v2.5 新增：容器内 127.0.0.1:8000 loopback 不通 + 无 key 全 401 → 凭证/连通性前置项。
5. **P5 [MEDIUM] 回测 run_id 指纹内容级空洞**：digest 仅 (auction_symbol_count, auction_enabled_dates)，行值变化被 `reused=True` 静默吞。预防：digest 升级内容级（分区行数/内容 hash）或来源变更强制新 run_id。
6. **P6 [MEDIUM] SDK 上游变更/日历投影**：并行演进无版本锚；2027 交易日历是未核对投影，绝不消费。预防：接入锁 stockdb 修订号（manifest 记录，镜像 UPSTREAM-SYNC 纪律）+ 响应 schema 校验 fail-closed；日历一律用 AthenaQuant 物理分区。

## Implications for Roadmap

### Phase A: 本机 stockdb 通道接入（P0 受管通道）
**Rationale:** 通道是 v2.5 核心交付，所有下游（回填节奏、部署日）依赖它先落地；能力声明 `auction=False` 使范围明确为日 K/复权/分时旁路，无竞价歧义。
**Delivers:** `stockdb_provider.py`（HTTP 适配器，命名 `local_stockdb`）+ config settings（url/api_key）+ `_BUILTIN_CHAIN` 注册 + hermetic 测试 + live 冒烟；归一化契约测试（symbol 映射/手→股 ×100/时区 aware 断言）作为**硬验收**。
**Addresses:** FEATURES table stakes（日 K+复权、分时/实时旁路）+ differentiators（本地旁路零配额、复权读取时计算）。
**Avoids:** P1（归一化单点+契约测试）、P5（接入后回测复验 RC-02 重跑）、P6（版本锚+契约测试）。
**Notes:** 适配器 symbol/单位映射细节 UNKNOWN，须本 phase 探测确认；`backfill-minute` 扩分钟湖是否纳入本 phase 为范围决策点（若历史竞价在范围内）。

### Phase B: 诚实性修复（HON-1 source_blocked + HON-2 进度 emit）
**Rationale:** 纯 AQ 内两处独立小改动，**不依赖 Phase A**，可与 A 并行；P2/P3 是记录在案的事故模式（36-02/36-03），修复收益独立成立。
**Delivers:** xyz_provider 三态化（403/配额窗 markers → policy-block 信号，其余保持空帧不抛）+ 台账第三类 reason `"source_blocked"`（verify_auction_backfill.py:187-217 区分门）+ probe verdict detail + **fail-closed 提前返回路径补终态 emit**（真冻结点，非 283-296）+ CLI on_progress 接线；回归测试（全空帧批量进度断言 + 第三类 reason 断言）。
**Avoids:** P2（三态化是硬验收）、P3（emit 修复 + 取消 stage 语义 + 回归锁）。
**Notes:** xyz 403 配额窗真实响应体结构 UNKNOWN（窗口未触发无法复现）——分类器以 HTTP 403 + 文案 markers 双信号设计，2h 窗复现时回填定稿；stockdb 适配器在 Phase A 即按三态写，避免二次返工。

### Phase C: 部署日执行（D1..D8 观测 runbook）
**Rationale:** 依赖 Phase A 全绿（凭证/连通性前置）；把「容器起来了」升级为「系统对了」。
**Delivers:** D 系 runbook 脚本化（D1 09:26 盘前 / D2 15:30 EOD / D3 竞价源接入 / D4 监控 / D5 复盘 / D6 R13 / D7 概念 drift ≥5 交易日 / D8 立场）；3 新端点 curl 断言 **200 + body 键形状**（镜像空态契约 `{available:false}`，只验状态码会放过错误体 200）；**3018 容器 rebuild 对齐**（重建前 md5 基线 → 重建后 parity 4/4）；分钟点亮门（15:30 EOD 后 `kline_minute/date={T}` 分区存在 **且** `auction_intraday_confirm` 非空）；stockdb 凭证/连通性前置（容器内 host 网关 + API key env 注入 + 401→`source_blocked` 语义映射）；数据卷权限（compose user/chown）。
**Avoids:** P4 全部五类遗漏。

### 前置门（仅当范围含「竞价源切换/并行」）
stockdb 无竞价端点是跨仓 blocker——若 v2.5 意图 stockdb 当竞价源，须先开 stockdb 侧新增 09:26 撮合行端点的可行性门（独立 phase，阻塞 A）。**研究建议：v2.5 不设此门**，竞价源维持 xyz，stockdb 只作旁路，避免范围膨胀。

### Phase Ordering Rationale
- **A ∥ B 并行、C 收口**：P1 两件（source_blocked、进度 emit）与 P0 通道零依赖；P2 部署日依赖 P0 全绿；A 与 B 都完成后 C 才有意义。
- **分组依据架构**：A = 新组件（2 个）+ chain 修改；B = 纯 AQ 内修改（xyz_provider/auction_backfill/auction_probe/scripts/tests）；C = 运营面（runbook/脚本/对齐），三类工作边界清晰、互不干扰。
- **陷阱绑定**：A 扛 P1/P5/P6，B 扛 P2/P3，C 扛 P4——每个 phase 的硬验收即对应陷阱的预防措施落地。

### Research Flags
Needs deeper research during planning（`/gsd-plan-phase --research-phase`）：
- **Phase A:** 适配器 symbol/单位/时区映射细节 UNKNOWN（须 live probe 定稿）；Docker 构建上下文不含 `../stockdb` 的部署形态（本 phase 若含 `backfill-minute` 扩分钟湖，需调研 Tushare stk_mins 接入）；SDK 修订号锚定。
- **Phase C:** 部署日 runbook 需对照真实容器/卷状态细化（3018 容器 root-owned 处置、compose 凭证注入方式）；若需 `uv pip install -e --no-deps` 进镜像，首次构建走 build isolation 需网络的调研。

Standard patterns（可跳过 research-phase）：
- **Phase B:** 三态化 + 台账第三类 reason + emit 补全均为既有代码模式的小幅扩展，证据锚点与行号已齐（xyz_provider.py:189-198/228-250、auction_backfill.py:200/224/228/266/268、verify_auction_backfill.py:187-217），直接 plan。

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | 本地实测 `import stockdb` 3.11 SyntaxError + uv.lock/源码核实；唯一推断项 = 里程碑上下文「Python 3.12」与实测 3.11.2 冲突，需里程碑显式确认 |
| Features | HIGH | 竞价 T-day/历史部分/日 K/鉴权限频均 live 实测 + 对账闭合；DATA-06 输入映射与逐笔级 = UNKNOWN |
| Architecture | HIGH | 双仓源码 + live 探测双证据（openapi 41 路径无 auction、全端点 401 实测、emit 行号 blame 核实） |
| Pitfalls | HIGH | 全部证据锚点为实测/源码；SD 通道 symbol/单位映射细节标 UNKNOWN |

**Overall confidence:** HIGH（仅两处 UNKNOWN：xyz 403 响应体结构、DATA-06 派生输入语义——均为 Phase A/B 探测可闭合项，不阻塞 roadmap）。

### Gaps to Address
- **Python 3.11 vs 3.12 冲突**：STACK 方案 A（3.12 升级）与架构结论（HTTP 适配器规避）并存——需里程碑显式确认 v2.5 是否升级 3.12；HTTP 适配器形态下无需升级，零风险。
- **xyz 403 配额窗真实响应体 UNKNOWN**：分类器双信号设计（HTTP 403 + 文案 markers），2h 窗复现时回填定稿。
- **DATA-06 派生输入（unmatched_volume/virtual_price）语义映射 UNKNOWN**：Phase A probe，不猜测。
- **W-5 终态 dict 是否加 `source` 键（决策点）**：加则需测试矩阵同步（test_auction_backfill_honesty.py:213, 284-305）。
- **命名决策**：任务/STACK 定 `local_stockdb`（ARCHITECTURE.md 曾写 `stockdb_local`）——以 `local_stockdb` 为准，plan 时锁定。
- **历史逐笔不可得**：FA-04 全量回填不立即解锁，需在里程碑验收标准中明确「诚实缺口声明」而非承诺解锁。

## Sources

### Primary（HIGH，本地实测 + 源码核实）
- stockdb 源码：pyproject.toml（requires-python >=3.12）、sdk/{client,models,errors,stream,`__init__`}.py、contracts/schemas.py（426-441）、providers/eastmoney.py（724-745）、api/auth.py、api/audit.py、api/app.py:134
- stockdb 文档：docs/DATA_CONTRACTS.md（§7/§12/§21；132, 146, 330, 356-363, 382-387, 449-459, 492-494, 686-691, 709-713, 1042-1046, 1163-1169）、API.md（§2/§4/§7；37-49, 80-127, 568-572, 647-649）、README.md
- 运行时探测：curl 127.0.0.1:8000 openapi.json（41 个 `/v1/*` 路径、无 auction）；无 key/假 key 访问 health/quotes → 401；`import stockdb` 于 3.11 venv → SyntaxError（stream.py:30）；tick/minute 湖 parquet 对账闭合
- AthenaQuant 源码：backend/pyproject.toml、uv.lock（952/2488）、Dockerfile:42、app/config.py:77-83、data_providers/{base,chain,registry}.py、data_providers/{xyz,ifzq,tencent}_provider.py、services/{auction_backfill,auction_probe,auction_sync,auction_backtest}.py、scripts/{auction_backfill,verify_auction_backfill}.py、backend/.venv/pyvenv.cfg
- AthenaQuant 文档：docs/deploy-verification.md（16-190, 206-215）、docs/features.md（42, 49-50, 84-89）、.planning/phases/36-auction-full-backfill/36-02/36-03-SUMMARY.md、FA-05-BJ-STANCE.md、.planning/milestones/v2.4-MILESTONE-AUDIT.md:70、docker-compose.yml:25-36

### Secondary（MEDIUM）
- 项目上下文：.planning/PROJECT.md（v2.5 里程碑目标与验收）、.planning/ROADMAP.md:130、docs/UPSTREAM-SYNC.md（版本锚纪律参照）
- 测试契约：test_xyz_provider.py:126-137、test_auction_backfill_honesty.py:213, 284-305、test_ifzq_provider.py:112（归一化断言参照）

### Tertiary（LOW / 需探测）
- xyz 403 配额窗真实响应体结构（UNKNOWN，窗口未触发无法复现）
- DATA-06 派生输入（unmatched_volume/virtual_price）语义映射（UNKNOWN，需 probe）
- 里程碑上下文「AthenaQuant 是 Python 3.12」与实测 3.11.2 的冲突（[INFERENCE]，需显式确认）

---
*Research completed: 2026-08-07*
*Ready for roadmap: yes*
