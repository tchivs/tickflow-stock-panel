---
phase: 44-deploy-day
plan: 02
subsystem: [infra, api]
tags: [deploy-verification, 200-body, auth, backfill, python-stdlib]

# Dependency graph
requires:
  - phase: 44-01
    provides: 预检镜像 athenaquant-app:preflight (HEAD, md5 4/4) + :3020 沙箱配方 + 401 门基线
provides:
  - deploy_verify_endpoints.py — 3 新端点 200-body 键形状验证脚本 (401 先验 3/3 → login → validation/backtest/backfill → job 轮询 W-5, JSON 台账 + 退出码 0/1/2/3)
  - 部署日运行说明 (docstring): DEP_PASSWORD 从 .env 注入, 重建后 3018 全流程, human-check 记录面
affects: [44-03 (runbook/rebuild), 44-verify, deploy-day]

# Actuals
actuals:
  tokens: 5533
  tasks: 3
  commits: 1

# Tech tracking
tech-stack:
  added: [python3 stdlib urllib.request + http.cookiejar (零新依赖)]
  patterns:
    - 部署脚本惯例: 401 先验硬门 → 认证 → 键形状断言 (锁形状不锁值) → JSON 台账 → 退出码语义
    - fail-closed 验证触发: 远未来窗 body → no_scope/source_unavailable 零上游, 全量回填脚本拒绝
    - 凭证纪律: env 注入单次尝试, 不回显, 台账无凭证

key-files:
  created: [backend/scripts/deploy_verify_endpoints.py]

key-decisions:
  - "window 键契约以 live 沙箱为准: requested_start/requested_end/effective_start/effective_end (RESEARCH 表 'requested/effective' 为简写, 实测修正)"
  - "coverage.symbols 5 键断言作用于 symbols 子 dict (首版误作用于 coverage 顶层, 沙箱实测捕获并修复)"
  - "fail-closed 终态 requested=0 即为零上游放大最强证明 (计划 done 措辞 'requested 恰为 1 symbol' 指 POST 体 symbols 恰 1 项)"
  - "台账 auth_401 键用完整端点路径 (可读性优先于计划 verify 的短键 jq 表达式, 校验语义等价)"

patterns-established:
  - 验证脚本模式: 无 cookie 先验 3/3 (任一非 401 中止) → 单次 login → 逐端点键集合断言 + 值集断言 → 后台 job 轮询至终态 → 原子 JSON 台账
  - 安全触发模式: 默认 fail-closed 触发体 + 显式三参数 (--symbols/--start/--end) 齐全才允许真实小范围; 缺参数/全量一律拒绝

requirements-completed: [DEP-02]

coverage:
  - id: D-DEP02
    description: "deploy_verify_endpoints.py — 401 先验 3/3 → 真实登录 (tf_session cookie) → validation/backtest/backfill 200-body 键形状断言 → backfill job 轮询至终态 (W-5 9 键含 reason) → JSON 台账 + 退出码 0/1/2/3; 沙箱 :3020 全流程通过"
    requirement: DEP-02
    verification:
      - kind: integration
        ref: "backend/scripts/deploy_verify_endpoints.py — py_compile + 沙箱 :3020 正例 (exit 0, 台账全 PASS)"
        status: pass
      - kind: integration
        ref: "沙箱负例: 错密码 exit 2 且 login 恰 1 次请求 (docker logs delta=1); refused exit 3; grep 凭证守卫 == 0"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_backfill_full_universe.py — 14 passed (W-5/401/backfill 形状回归)"
        status: pass
    human_judgment: false
  - id: D-DEP02-deployday
    description: "部署日对重建后 3018 的真实 200-body 全流程 (44-01 preflight green → 44-03 --apply → 本脚本 --base-url http://127.0.0.1:3018) — human-check: data_gate/coverage 真实值如实记录, 绝不回填假值"
    requirement: DEP-02
    verification: []
    human_judgment: true
    rationale: "部署日真实事件 = 脚本交付 + human-verify 记录; 沙箱证脚本逻辑与 DTO 形状, 重建后真实环境值 (data_gate 可能翻转 available, coverage 真实行数) 只能由 operator 在 3018 上执行并记录 (Phase 44 记录纪律: 不伪造部署日事件)"

# Metrics
duration: 45min
completed: 2026-08-07
status: complete
---

# Phase 44-02: DEP-02 部署日 200-body 验证脚本 Summary

**deploy_verify_endpoints.py — 3 新端点 200-body 键形状验证脚本 (python3 stdlib 零新依赖): 401 先验 3/3 → 真实登录 → validation 8 键 / backtest {runs,count}+详情 / backfill fail-closed + job 轮询 W-5 9 键 → JSON 台账 + 退出码, 沙箱 :3020 全流程实测通过**

## Performance

- **Duration:** ~45 min (含沙箱 boot/cleanup 与 44-01 的 :3020 交接等待)
- **Started:** 2026-08-07T17:30Z
- **Completed:** 2026-08-07T17:55Z
- **Tasks:** 3 (Task 1 认证流+validation/backtest 断言; Task 2 backfill fail-closed+job 轮询; Task 3 错误分类+负例+部署日说明)
- **Files modified:** 1 (backend/scripts/deploy_verify_endpoints.py)

## Accomplishments
- **401 先验 3/3 硬门**: validation/backtest/backfill 无 cookie 均 401 (沙箱实测), 任一非 401 立即中止 exit 1 — 认证门失效不再继续误判 200-body
- **真实登录 + tf_session**: DEP_PASSWORD env 注入, 单次尝试; 错密码 → exit 2 且容器日志证明 login 恰 1 次 POST (不触发 auth.py 5 次/300s 锁)
- **200-body 键形状断言全绿** (沙箱实测): validation 8 顶层键 (data_gate=available) + coverage.symbols 5 键 + minute_stats 11 键 (caliber=statistical_minute_0930) + window 4 键 + strategies 9; backtest {runs,count} count==len(runs) + run 8 键 (run_id ^[0-9a-f]{12}$) + 详情 {manifest,stats,sample} sample=20≤20; backfill {status:started, job_id ^[0-9a-f]{10}$} → job succeeded → W-5 9 键含 reason=source_unavailable, requested=0 (fail-closed 零上游放大)
- **安全触发**: 默认远未来窗 fail-closed 体 (零上游消耗); --symbols/--start/--end 三参数齐全才允许真实小范围 (格式校验+上限 6000); 缺参数 warning + 强制 fail-closed; 全量回填脚本拒绝 (36-02 配额纪律, docstring+台账双明示)
- **退出码 + 台账**: 0 全过 / 1 断言失败 (含缺键明细) / 2 认证失败 / 3 运行错误; JSON 台账原子落盘 (tmp+os.replace); 429 尊重 Retry-After 仅重试 1 次 (Phase 40 契约)

## Task Commits

单文件交付, 3 任务合成一次原子提交 (拆分同文件为多提交属人为碎片化):

1. **Task 1+2+3: deploy_verify_endpoints.py** - `73f082d` (feat)

## Files Created/Modified
- `backend/scripts/deploy_verify_endpoints.py` - DEP-02 200-body 验证脚本 (401 先验 → login → 3 端点键断言 → backfill job 轮询 → JSON 台账 + 退出码; docstring 含部署日运行说明与 human-check 记录面)

## Decisions Made
- window 键契约以 live 沙箱实测为准 (requested_start/effective_start/requested_end/effective_end), 修正 RESEARCH 简写表 — 脚本锁真实契约
- fail-closed 终态 requested=0 是零上游放大的诚实最强证明 (POST 体 symbols 恰 1 项, 终态 requested=0 说明 scope 未放大)
- 台账 auth_401 键用完整端点路径 (信息量优先; 计划 verify 的短键 jq 表达式适配为方括号访问, 语义等价)
- 三任务合一原子提交 — 同一文件交付物, 人为拆分无价值

## Deviations from Plan

### Auto-fixed Issues

**1. coverage.symbols 断言层级错误 (脚本自身编码缺陷)**
- **Found during:** Task 1 沙箱正例 (首次运行)
- **Issue:** 5 键集合断言作用于 coverage 顶层 dict, 而非 coverage["symbols"] 子 dict → 断言失败 (顶层只有 7 键: auction_enabled_dates/…/symbols/minute_stats)
- **Fix:** 先断言 coverage["symbols"] 为 dict, 再对其断言 5 键
- **Files modified:** backend/scripts/deploy_verify_endpoints.py
- **Verification:** 沙箱重跑 exit 0, 台账 symbols_keys 5 键
- **Committed in:** 73f082d

**2. window 键集合与实测契约不符 (RESEARCH 简写表误导)**
- **Found during:** Task 1 沙箱正例
- **Issue:** 计划/RESEARCH 记 "window 含 requested/effective", 实测键为 requested_start/requested_end/effective_start/effective_end (auction_validation.py 回夹双字段, live 沙箱为 ground truth)
- **Fix:** 断言 4 键 {requested_start, requested_end, effective_start, effective_end}, 台账记录 4 值
- **Files modified:** backend/scripts/deploy_verify_endpoints.py
- **Verification:** 沙箱重跑 exit 0, window 4 键断言过
- **Committed in:** 73f082d

**3. 台账键集合序列化 (set → string)**
- **Found during:** Task 1 台账 jq 校验
- **Issue:** json.dumps default=str 把 set 字段 (top_keys 等) 序列化成字符串, 台账不可结构化消费
- **Fix:** 全部转 sorted(list) 落台账
- **Files modified:** backend/scripts/deploy_verify_endpoints.py
- **Verification:** jq '.validation.top_keys | length == 8' 通过
- **Committed in:** 73f082d

---

**Total deviations:** 3 auto-fixed (1 编码缺陷, 1 契约修正, 1 序列化)
**Impact on plan:** 全部为正确性与可消费性修复, 无 scope creep; 计划自动化 verify 的 jq 表达式因台账键名差异 (完整端点路径) 与集合序列化修正后语义等价通过

## Issues Encountered
- **:3020 沙箱交接**: 44-01 与 44-02 均需 :3020 — 经 hub 协调, 44-01 先完成 gate check 并全清理后交棒, 零冲突 (预检镜像 9e27032406ba 复用, 未重复 build)
- **首次正例失败根因**: 上述 deviation 1/2 (脚本侧), 非沙箱/应用侧 — 应用 DTO 与 RESEARCH 实测一致 (coverage.symbols 5 键 / window 4 键 / minute_stats 11 键全对)

## User Setup Required
None - 无外部服务配置; 部署日 operator 按 docstring 执行 (DEP_PASSWORD 从 .env AUTH_PASSWORD 注入)

## Next Phase Readiness
- 脚本交付且沙箱等价验证通过; 部署日对重建后 3018 的全流程 = human-check (记录在 44-03 重建配方之后, 键形状断言 + 真实值如实记录)
- [安全观察, 供 operator 知悉] 沙箱 temp 副本 auth.json 以 Command_123 实测登录成功 → 生产 auth.json 对应密码很可能即为 Command_123 (RESEARCH A2 确认); 部署日若实际密码已改, login 401 → 脚本 exit 2, 按 docstring 注入正确密码单次重试即可, 不触发限流锁
- 44-03 可复用本脚本于部署日 (:3018), 及预检镜像 athenaquant-app:preflight (HEAD, md5 4/4)

---
*Phase: 44-deploy-day*
*Completed: 2026-08-07*
