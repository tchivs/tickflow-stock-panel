# 40-02-SUMMARY — 注册 (config 键 + 链/白名单/settings 接线)

**Phase**: 40 本机 stockdb 通道接入 (LOCAL stockdb local channel) — wave 2 注册
**Executed**: 2026-08-07 (ExecP4002, wave 2)
**Commits (本 wave, 3 个原子提交)**: `8655a57` (T1 config 键 + 分支/单例) · `1ee1979` (T2 链首+白名单+health+settings builtin 四处同波) · `f468c7f` (T3 注册回归测试)。同行 wave: 40-01 (适配器, ExecP4001, 测试文件 `test_stockdb_provider.py` 已落盘) · 40-03 (集成, ExecP4003, 进行中)。
**来源纪律**: 本文件只记录本 wave 的可观测验证证据; 判决以实际 pytest 输出为准。

## 交付清单 (LOCAL-02 全项)

| 面 | 改动 | 提交 |
|---|---|---|
| config 键 | `local_stockdb_url` (默认 `http://127.0.0.1:8000`) + `local_stockdb_api_key` (默认 `""`), env `LOCAL_STOCKDB_URL` / `LOCAL_STOCKDB_API_KEY` 经 pydantic-settings 既有接线覆盖 | `8655a57` |
| .env.example | 两行注释占位 (`LOCAL_STOCKDB_URL=` / `LOCAL_STOCKDB_API_KEY=`), 真实 key 只进 .env (与 TICKFLOW_API_KEY 同纪律) | `8655a57` |
| chain.py 单例+分支 | `local_stockdb_provider()` lazy 单例 (缓存面 `_provider_cache["local_stockdb"]`), `_get_provider("local_stockdb")` 分支 | `8655a57` |
| chain.py 链首 | `_BUILTIN_CHAIN` daily/minute 链首插 `local_stockdb` (adj_factor/financial/instruments 不动) | `1ee1979` |
| preferences.py 白名单 | `_ALLOWED_DATA_PROVIDERS` 追加 `local_stockdb` (静默回退陷阱开关) | `1ee1979` |
| chain.py health | `health_check("local_stockdb")` 并入 probe 分支, 探针 `get_daily(["SH600519"])` 前缀形态 (裸码会 400); 401/429 typed 异常 → "error" | `1ee1979` |
| api/settings.py builtin | `{"name": "local_stockdb", "display_name": "Local StockDB (本机)", "datasets": ["daily", "minute"], "health": health_check(...), "base_url": settings.local_stockdb_url}` | `1ee1979` |
| 注册回归测试 | `backend/tests/test_local_stockdb_registration.py` (10 用例) | `8655a57` (4) + `f468c7f` (6) |

**T2 单次原子提交防半完成态**: 链首插槽 + 白名单 + health + settings builtin 四处同波 `1ee1979` — 避免「链首已加而白名单未加 → `_sanitize_chain` 静默过滤回 tickflow」的假成功态 (Pitfall 4, preferences.py:155-158 文档化陷阱)。

## Test Plan 证据

```
$ cd backend && .venv/bin/python -m pytest tests/test_local_stockdb_registration.py tests/test_data_source_selection.py tests/test_provider_chain.py -q
.........................................                                [100%]
41 passed in 1.75s
```

- **新增用例 10 个, 全绿** (test_local_stockdb_registration.py):
  1. `test_config_defaults` — 默认 `http://127.0.0.1:8000` / `""`
  2. `test_config_env_override` — `LOCAL_STOCKDB_URL` / `LOCAL_STOCKDB_API_KEY` 覆盖新 Settings 实例
  3. `test_get_provider_local_stockdb_returns_singleton` — 两次调用**同 id** + 构造 kwargs 捕获断言
  4. `test_singleton_uses_settings_defaults` — 单例构造参数来自 settings 缺省回退面
  5. `test_local_stockdb_in_whitelist` — `_clean_whitelist` 隔离后白名单 ⊇ {local_stockdb} (陷阱锁)
  6. `test_set_provider_chain_keeps_local_stockdb_first` — 保存链首 local_stockdb + tickflow 兜底在末
  7. `test_builtin_chain_heads_local_stockdb` — `chain_for("daily")[0]` / `chain_for("minute")[0]` == local_stockdb
  8. `test_user_chain_override_position_wins` — 用户 `provider_chains` 保持原顺序 (位置配置化, 不自动插链首)
  9. `test_health_check_local_stockdb_ok_warn_error` — 非空帧→ok / 空帧→warn / `StockDBAuthError`→error
  10. `test_settings_builtin_lists_local_stockdb` — builtin 条目 datasets==["daily","minute"] / health / base_url==settings.local_stockdb_url
- **既有回归零破坏**: test_data_source_selection.py (白名单可切换: free_stockdb/xyz/tencent + 未知源回退) + test_provider_chain.py 全绿 — 41 passed 含二者。
- **T1 红转绿路径**: 初始运行 3 pass + 1 fail (测试自身 kwargs 捕获 lambda 缺陷) → 修正后 4 pass (T1 提交前); 再追加 T3 用例 → 41 pass。

## 约束合规

- **零新增依赖**: pyproject.toml / uv.lock 在 HEAD~3..HEAD 区间 **0 改动**。
- **kline_sync.py 零改动**: 本 wave 提交集不含 backend/app/tickflow/kline_sync.py。
- **Watchlist.tsx 零触碰**: 最终 `git status --short` 中 `M frontend/src/pages/Watchlist.tsx` 为唯一非本 wave 未暂存改动 (未读未触, 保持 orchestrator 契约); 本 wave 其余未暂存项 (test_data_source_selection.py / test_provider_chain.py / test_stockdb_provider.py / test_local_stockdb_write_path.py) 为 40-01/40-03 并行 wave 的在途改动, 未纳入本 wave 提交。
- **单例同 id 断言**: `test_get_provider_local_stockdb_returns_singleton` 中 `a is b` 显式断言。
- **漏白名单陷阱已锁**: 用例 5/6 在 `_clean_whitelist()` 隔离后断言白名单含源 + 保存链不被过滤; 若白名单缺 local_stockdb, `_sanitize_chain` 会过滤回 tickflow → 用例红。

## 遗留

无本 wave 遗留。40-03 集成 (链级 gap-merge / AST 守卫 / 全量回归) 由 ExecP4003 承接; 全量 hermetic 回归由 orchestrator 统一在 wave 3 后跑 (本 wave 按契约跳过)。
