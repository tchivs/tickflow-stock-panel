"""BT-06 POOL-03 零执行权限守卫 — ``api/research_auction.py`` + ``services/auction_validation.py``。

镜像 test_pool_hub.py:857-963 (E1/E3/E4/E5 形) 与 test_auction_history.py 单文件变体;
守卫目标 = 竞价策略历史验证端点 + 报告服务 (独立 AST 守卫面, 不与 research.py 混入)。

6 项守卫:
1. 守卫目标两文件存在且非空 (防守卫悬空);
2. 无执行族 import (``_EXECUTION_TOKEN``) 且无禁 import token (竞价同步/快照/回填/
   盘前快照/选股触发面模块名);
3. API 仅 ``@router.get`` (GET-only);
4. 无写路径 (``_WRITE_PATTERNS`` 全集) 且无禁调用 token (批量执行/缓存写/点快照持久化);
5. 无「单 as_of 运行期缓存指针」字面量引用 (import 面与源码均查) 且无缓存写调用;
6. import 白名单 ⊆ {polars, fastapi, app.services.auction_probe, app.tickflow.repository,
   app.strategy.engine, app.services.auction_columns, app.services.auction_validation}
   ∪ {__future__} ∪ stdlib (datetime/typing/logging/pathlib/re/ast)。

守卫为源码级静态分析 (只读, 不 import 守卫目标), 目标模块 docstring/注释用概念词
表述 (如「单 as_of 运行期缓存指针」「批量执行触发面」), 绝不出现禁 token 字面串。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

# 执行族 token: 出现在守卫目标 import 中即失败 (镜像 test_pool_hub.py:857-863)
_EXECUTION_TOKEN = re.compile(
    r"broker|order|execution|trade|portfolio|watchlist|position|account|transaction|下单|委托",
    re.IGNORECASE,
)

# 写路径 pattern: 出现在守卫目标源码中即失败 (镜像 test_pool_hub.py:865-872)
_WRITE_PATTERNS = (
    re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']w"),
    re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']wb"),
    re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']a"),
    re.compile(r"write_parquet"),
    re.compile(r"os\.replace"),
    re.compile(r"unlink\s*\("),
    re.compile(r"mkdir\s*\("),
)

# 禁 import token (RESEARCH §5 BT-06): 竞价同步/快照/回填/盘前快照/选股触发面模块
_FORBIDDEN_IMPORT_TOKEN = re.compile(r"auction_sync|pool_snapshot|pool_backfill|premarket_snapshot|screener")

# 禁调用 token: 批量执行/缓存写/点快照持久化触发面 (镜像 test_pool_hub E5 + Phase-29 扩展)
_FORBIDDEN_CALL_TOKENS = ("run_all", "run_preset", "write_cache", "persist_point_snapshot")

# import 白名单 (RESEARCH §5 BT-06): app 面逐前缀, 外部/stdlib 面逐名
_IMPORT_PREFIXES = (
    "app.services.auction_probe",
    "app.tickflow.repository",
    "app.strategy.engine",
    "app.services.auction_columns",
    "app.services.auction_validation",
)
_IMPORT_EXACT = {
    "polars", "fastapi", "__future__", "datetime", "typing", "logging", "pathlib", "re", "ast",
    "collections.abc",  # stdlib (29-02 服务层 Callable 注入点; 29-02-SUMMARY 白名单前置声明)
}


def _feature_sources() -> tuple[str, str]:
    """守卫目标源码: (api, service) 两文件全文 (镜像 test_pool_hub.py:873-879 形)。"""
    backend = Path(__file__).resolve().parents[1]
    api_src = (backend / "app" / "api" / "research_auction.py").read_text(encoding="utf-8")
    service_src = (backend / "app" / "services" / "auction_validation.py").read_text(encoding="utf-8")
    return api_src, service_src


def _imported_module_names(source: str) -> list[str]:
    """AST 提取全部 import 模块名 (镜像 test_pool_hub.py:881-889 逐字)。"""
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_validation_modules_exist():
    """守卫目标两文件存在且非空 (防守卫悬空, BT-06)。"""
    backend = Path(__file__).resolve().parents[1]
    for rel in ("app/api/research_auction.py", "app/services/auction_validation.py"):
        p = backend / rel
        assert p.exists(), f"守卫目标缺失: {rel}"
        assert p.stat().st_size > 0, f"守卫目标为空: {rel}"


def test_validation_no_execution_imports():
    """守卫目标不得 import 执行族模块 (E1 形) 或竞价同步/快照/回填/选股触发面模块 (BT-06)。"""
    for src in _feature_sources():
        for module in _imported_module_names(src):
            assert not _EXECUTION_TOKEN.search(module), (
                f"竞价验证特性引入了执行族模块: {module}"
            )
            assert not _FORBIDDEN_IMPORT_TOKEN.search(module), (
                f"竞价验证特性引入了禁 import 模块: {module}"
            )


def test_validation_api_is_get_only():
    """research_auction.py 只允许 GET 路由 (E4 形, BT-06)。"""
    api_src, _service_src = _feature_sources()
    methods = re.findall(r"@router\.(get|post|put|delete|patch)\b", api_src)
    assert methods and set(methods) == {"get"}, f"竞价验证 API 出现了非 GET 路由: {methods}"


def test_validation_no_write_path():
    """守卫目标纯读者: 无写模式 open / write_parquet / os.replace / unlink / mkdir
    (E3/E4 形), 且无禁调用 token (批量执行/缓存写/点快照持久化, BT-06)。"""
    for src in _feature_sources():
        for pattern in _WRITE_PATTERNS:
            assert not pattern.search(src), f"竞价验证特性出现写路径: {pattern.pattern}"
        for token in _FORBIDDEN_CALL_TOKENS:
            assert token not in src, f"竞价验证特性出现了计算触发调用: {token}"


def test_validation_no_strategy_cache_reference():
    """守卫目标不得引用「单 as_of 运行期缓存指针」字面量 (E3 形, import 面与源码均查)
    且无缓存写调用 (write_cache, BT-06)。"""
    for src in _feature_sources():
        for module in _imported_module_names(src):
            assert "strategy_cache" not in module, (
                f"竞价验证特性引入了运行时缓存模块: {module}"
            )
        assert "strategy_cache" not in src, "竞价验证特性源码引用了 strategy_cache"
        assert "write_cache" not in src, "竞价验证特性源码引用了 write_cache"


def test_validation_import_whitelist():
    """守卫目标 import 面 ⊆ 白名单 (polars/fastapi/app 面 5 前缀) ∪ __future__ ∪ stdlib (BT-06)。"""
    for src in _feature_sources():
        for module in _imported_module_names(src):
            assert (
                module in _IMPORT_EXACT
                or any(module.startswith(prefix) for prefix in _IMPORT_PREFIXES)
            ), f"竞价验证特性 import 越出白名单: {module}"
