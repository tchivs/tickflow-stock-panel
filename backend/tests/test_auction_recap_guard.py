"""REV-05 POOL-03 零执行权限守卫 — ``api/market_recap_auction.py`` + ``services/auction_recap.py``。

镜像 test_auction_validation.py 6 项结构 (BT-06 同族), 白名单按 REV 语义重订:

- 禁 import token 较 Phase 29 收窄: REV 必须 import ``premarket_snapshot`` (预览
  装载) 与 ``screener`` (enriched 读取/显示名解析), 故禁面只保留
  ``auction_sync|pool_snapshot|pool_backfill`` (执行/快照/回填触发面)。
- 禁调用 token 扩展 ``save_report``: REV 端点/服务绝不归档报告。
- import 白名单含 ``app.services.preferences``: 服务 pre_eod 判别懒 import
  ``get_pipeline_schedule()`` (只读配置 getter, 非执行族)。

6 项守卫:
1. 守卫目标两文件存在且非空 (防守卫悬空);
2. 无执行族 import (``_EXECUTION_TOKEN``) 且无禁 import token (竞价同步/快照/回填);
3. API 仅 ``@router.get`` (GET-only, 仅作用于新 api 模块);
4. 无写路径 (``_WRITE_PATTERNS`` 全集) 且无禁调用 token (批量执行/缓存写/点快照
   持久化/报告归档);
5. 无「单 as_of 运行期缓存指针」字面量引用 (import 面与源码均查) 且无缓存写调用;
6. import 白名单 ⊆ {polars, fastapi, app.services.* REV 前缀, app.tickflow.repository,
   app.strategy.engine, app.market_time} ∪ {__future__} ∪ stdlib。

守卫为源码级静态分析 (只读, 不 import 守卫目标), 目标模块 docstring/注释用概念词
表述 (如「单 as_of 运行期缓存指针」「批量执行触发面」), 绝不出现禁 token 字面串。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

# 执行族 token: 出现在守卫目标 import 中即失败 (镜像 test_auction_validation.py:21-27)
_EXECUTION_TOKEN = re.compile(
    r"broker|order|execution|trade|portfolio|watchlist|position|account|transaction|下单|委托",
    re.IGNORECASE,
)

# 写路径 pattern: 出现在守卫目标源码中即失败 (镜像 test_auction_validation.py:29-37)
_WRITE_PATTERNS = (
    re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']w"),
    re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']wb"),
    re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']a"),
    re.compile(r"write_parquet"),
    re.compile(r"os\.replace"),
    re.compile(r"unlink\s*\("),
    re.compile(r"mkdir\s*\("),
)

# 禁 import token (REV 版 — 较 Phase 29 收窄): 竞价同步/快照/回填触发面模块。
# 有意差异: REV 需 import premarket_snapshot (预览装载) + screener (enriched 读取/
# 显示名解析), 故不再禁二者 (Phase 29 的 test_auction_validation.py 禁面含二者,
# 守卫目标不同模块, 互不触碰; 差异原因注释于此, 单一事实源 = RESEARCH §7.2)。
_FORBIDDEN_IMPORT_TOKEN = re.compile(r"auction_sync|pool_snapshot|pool_backfill")

# 禁调用 token: 批量执行/缓存写/点快照持久化/报告归档触发面 (镜像
# test_auction_validation E5 + REV 扩展 save_report — 端点/服务绝不归档报告)
_FORBIDDEN_CALL_TOKENS = ("run_all", "run_preset", "write_cache", "persist_point_snapshot", "save_report")

# import 白名单 (RESEARCH §7.2 REV 版): app 面逐前缀, 外部/stdlib 面逐名。
# 含 app.services.preferences: 服务 pre_eod 判别懒 import get_pipeline_schedule()
# (只读配置 getter, 非执行族; RESEARCH §7.2 白名单的 REV 版扩展)。
_IMPORT_PREFIXES = (
    "app.services.auction_probe",
    "app.services.auction_columns",
    "app.services.auction_validation",
    "app.services.premarket_snapshot",
    "app.services.screener",
    "app.services.auction_recap",
    "app.services.guest_masking",
    "app.services.preferences",
    "app.tickflow.repository",
    "app.strategy.engine",
    "app.market_time",
)
_IMPORT_EXACT = {
    "polars", "fastapi", "__future__", "datetime", "typing", "logging", "pathlib", "re", "ast",
    "collections.abc",  # stdlib
}


def _feature_sources() -> tuple[str, str]:
    """守卫目标源码: (api, service) 两文件全文 (镜像 test_auction_validation.py:88-94)。"""
    backend = Path(__file__).resolve().parents[1]
    api_src = (backend / "app" / "api" / "market_recap_auction.py").read_text(encoding="utf-8")
    service_src = (backend / "app" / "services" / "auction_recap.py").read_text(encoding="utf-8")
    return api_src, service_src


def _imported_module_names(source: str) -> list[str]:
    """AST 提取全部 import 模块名 (镜像 test_auction_validation.py:96-104)。"""
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_recap_modules_exist():
    """守卫目标两文件存在且非空 (防守卫悬空, REV-05 验收 6)。"""
    backend = Path(__file__).resolve().parents[1]
    for rel in ("app/api/market_recap_auction.py", "app/services/auction_recap.py"):
        p = backend / rel
        assert p.exists(), f"守卫目标缺失: {rel}"
        assert p.stat().st_size > 0, f"守卫目标为空: {rel}"


def test_recap_no_execution_imports():
    """守卫目标不得 import 执行族模块 (E1 形) 或竞价同步/快照/回填模块 (REV 白名单)。"""
    for src in _feature_sources():
        for module in _imported_module_names(src):
            assert not _EXECUTION_TOKEN.search(module), (
                f"竞价复盘特性引入了执行族模块: {module}"
            )
            assert not _FORBIDDEN_IMPORT_TOKEN.search(module), (
                f"竞价复盘特性引入了禁 import 模块: {module}"
            )


def test_recap_api_is_get_only():
    """market_recap_auction.py 只允许 GET 路由 (E4 形, REV-05 验收 1)。"""
    api_src, _service_src = _feature_sources()
    methods = re.findall(r"@router\.(get|post|put|delete|patch)\b", api_src)
    assert methods and set(methods) == {"get"}, f"竞价复盘 API 出现了非 GET 路由: {methods}"


def test_recap_no_write_path():
    """守卫目标纯读者: 无写模式 open / write_parquet / os.replace / unlink / mkdir
    (E3/E4 形), 且无禁调用 token (批量执行/缓存写/点快照持久化/报告归档, REV)。"""
    for src in _feature_sources():
        for pattern in _WRITE_PATTERNS:
            assert not pattern.search(src), f"竞价复盘特性出现写路径: {pattern.pattern}"
        for token in _FORBIDDEN_CALL_TOKENS:
            assert token not in src, f"竞价复盘特性出现了计算触发调用: {token}"


def test_recap_no_strategy_cache_reference():
    """守卫目标不得引用「单 as_of 运行期缓存指针」字面量 (E3 形, import 面与源码均查)
    且无缓存写调用 (write_cache, REV)。"""
    for src in _feature_sources():
        for module in _imported_module_names(src):
            assert "strategy_cache" not in module, (
                f"竞价复盘特性引入了运行时缓存模块: {module}"
            )
        assert "strategy_cache" not in src, "竞价复盘特性源码引用了 strategy_cache"
        assert "write_cache" not in src, "竞价复盘特性源码引用了 write_cache"


def test_recap_import_whitelist():
    """守卫目标 import 面 ⊆ 白名单 (polars/fastapi/app 面 REV 前缀) ∪ __future__ ∪ stdlib。"""
    for src in _feature_sources():
        for module in _imported_module_names(src):
            assert (
                module in _IMPORT_EXACT
                or any(module.startswith(prefix) for prefix in _IMPORT_PREFIXES)
            ), f"竞价复盘特性 import 越出白名单: {module}"
