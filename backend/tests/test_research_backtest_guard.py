"""BT-09 POOL-03 零执行权限守卫 — ``api/research_backtest.py`` + ``services/auction_backtest.py``。

镜像 test_auction_validation.py (BT-06) 六项 + E2 根隔离 (镜像 28-01 concept_history
'writes only ext_history' 测试与 test_auction_backtest.py 写根测试的静态变体)。

守卫目标 = 竞价回测结果查询端点 + 回测服务 (独立 AST 守卫面, 不与 research.py 混入):

1. 两文件存在且非空 (防守卫悬空);
2. 无执行族 import + 无禁 import token (竞价同步/快照/回填/盘前快照/选股触发面;
   api 面另禁 pool_snapshot; 服务面豁免 pool_snapshot —— fingerprint 共源白名单例外);
3. API 仅 ``@router.get`` (GET-only, 任何 POST/写触发引入即红);
4. API 零写路径 (写模式 open / write_parquet / os.replace / unlink / mkdir 全集) +
   无禁调用 token (批量执行/缓存写/点快照持久化); 服务面写 token 豁免但受守卫 5 约束;
5. E2 根隔离: 服务面全部写调用点的目标路径表达式 (含赋值/实参绑定闭包展开) 均含
   ``backtest_results`` 字面量, 且不含 strategy_cache / screener_results /
   kline_auction / kline_daily_enriched 字面量 (写目标级, 非源码级 —— 34-01 服务
   docstring 以散文形式声明 E2 纪律, 属文档非引用, 实际契约由写目标闭包断言锁死);
6. 无「单 as_of 运行期缓存指针」「选股结果湖」字面量引用: api 面 import 与源码均查;
   服务面 import 面查 (34-01 docstring 散文豁免, 见守卫 5 注);
7. import 白名单: api ⊆ {fastapi, polars, stdlib, app.config}; 服务 ⊆
   {polars, stdlib, app.services.auction_columns, app.services.auction_validation,
   app.services.pool_snapshot} (纯助手/fingerprint 共源)。

守卫为源码级静态分析 (只读, 不 import 守卫目标); 目标模块 docstring/注释用概念词
表述 (如「单 as_of 运行期缓存指针」「选股结果湖」), 绝不出现禁 token 字面串。
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

# api 面禁 import token (全量): 竞价同步/快照/回填/盘前快照/选股触发面 + 服务助手
_API_FORBIDDEN_IMPORT_TOKEN = re.compile(
    r"auction_sync|pool_snapshot|pool_backfill|premarket_snapshot|screener"
)
# 服务面禁 import token (pool_snapshot 豁免 — fingerprint 共源白名单例外)
_SERVICE_FORBIDDEN_IMPORT_TOKEN = re.compile(
    r"auction_sync|pool_backfill|premarket_snapshot|screener"
)

# 禁调用 token: 批量执行/缓存写/点快照持久化触发面 (镜像 test_pool_hub E5)
_FORBIDDEN_CALL_TOKENS = ("run_all", "run_preset", "write_cache", "persist_point_snapshot")

# import 白名单: api 面 (fastapi/polars/stdlib/app.config) 与服务面 (镜像
# test_auction_validation.py 白名单形; 服务面例外 = auction_validation/pool_snapshot
# 纯助手/fingerprint 共源, 34-01 冻结契约)
_API_IMPORT_PREFIXES = ("app.config",)
_API_IMPORT_EXACT = {
    "polars", "fastapi", "__future__", "json", "re", "datetime", "pathlib",
}
_SERVICE_IMPORT_PREFIXES = (
    "app.services.auction_columns",
    "app.services.auction_validation",
    "app.services.pool_snapshot",
)
_SERVICE_IMPORT_EXACT = {
    "polars", "__future__", "hashlib", "json", "logging", "os",
    "collections.abc", "datetime", "pathlib",
}

# E2 根隔离: 服务写目标闭包禁湖字面量 (写目标级)
_WRITE_FORBIDDEN_LITERALS = ("strategy_cache", "screener_results", "kline_auction", "kline_daily_enriched")


def _feature_sources() -> tuple[str, str]:
    """守卫目标源码: (api, service) 两文件全文 (镜像 test_pool_hub.py:873-879 形)。"""
    backend = Path(__file__).resolve().parents[1]
    api_src = (backend / "app" / "api" / "research_backtest.py").read_text(encoding="utf-8")
    service_src = (backend / "app" / "services" / "auction_backtest.py").read_text(encoding="utf-8")
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


def _bindings(source: str) -> dict[str, str]:
    """写目标解析绑定闭包: 简单赋值 (name -> RHS 源码段) + 模块级函数调用实参 -> 形参。"""
    tree = ast.parse(source)
    binds: dict[str, str] = {}
    defs: dict[str, list[str]] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            defs[node.name] = [arg.arg for arg in node.args.args]
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            seg = ast.get_source_segment(source, node.value)
            if seg:
                binds.setdefault(node.targets[0].id, seg)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in defs:
            for pname, arg in zip(defs[node.func.id], node.args):
                seg = ast.get_source_segment(source, arg)
                if seg:
                    binds.setdefault(pname, seg)
    return binds


def _write_targets(source: str) -> list[str]:
    """AST 提取全部写调用点的目标对象源码段:

    - ``x.mkdir(...)`` → x (被创建目录);
    - ``df.write_parquet(path, ...)`` → 首个位置实参 (目标路径);
    - ``x.write_text(...)`` → x (被写文件);
    - ``os.replace(tmp, out)`` → 第 2 实参 (目标路径); ``tmp.replace(out)`` →
      首个位置实参 (目标路径);
    - ``unlink(x)`` → x。"""
    tree = ast.parse(source)
    targets: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not isinstance(fn, ast.Attribute) or fn.attr not in {
            "mkdir", "write_parquet", "write_text", "replace", "unlink",
        }:
            continue
        if isinstance(fn.value, ast.Name) and fn.value.id == "os" and fn.attr == "replace":
            seg = ast.get_source_segment(source, node.args[1]) if len(node.args) >= 2 else None
        elif fn.attr == "write_parquet" or fn.attr == "replace":
            seg = ast.get_source_segment(source, node.args[0]) if node.args else None
        elif fn.attr in {"mkdir", "write_text"}:
            seg = ast.get_source_segment(source, fn.value)
        else:  # unlink
            seg = ast.get_source_segment(source, node.args[0]) if node.args else None
        if seg:
            targets.append(seg)
    return targets


def _resolve_write_target(target: str, binds: dict[str, str]) -> str:
    """沿赋值/实参绑定闭包展开目标表达式 (每名最多替换一次, 上限 12 轮)。"""
    seen: set[str] = set()
    expanded = target
    for _ in range(12):
        if "backtest_results" in expanded:
            return expanded
        replaced = False
        for name, rhs in binds.items():
            if name in seen or name == "_BACKTEST_ROOT":
                continue
            pattern = re.compile(rf"\b{re.escape(name)}\b")
            if pattern.search(expanded):
                expanded = pattern.sub("( " + rhs + " )", expanded)
                seen.add(name)
                replaced = True
                break
        if not replaced:
            break
    # 最后一轮: 展开 _BACKTEST_ROOT 常量 (34-01 唯一 backtest_results 字面量源)
    if "_BACKTEST_ROOT" in expanded:
        expanded = re.sub(r"\b_BACKTEST_ROOT\b", ' "backtest_results" ', expanded)
    return expanded


def test_backtest_modules_exist():
    """守卫目标两文件存在且非空 (防守卫悬空, BT-09)。"""
    backend = Path(__file__).resolve().parents[1]
    for rel in ("app/api/research_backtest.py", "app/services/auction_backtest.py"):
        p = backend / rel
        assert p.exists(), f"守卫目标缺失: {rel}"
        assert p.stat().st_size > 0, f"守卫目标为空: {rel}"


def test_backtest_no_execution_imports():
    """守卫目标不得 import 执行族模块 (E1 形); api 面另禁竞价同步/快照/回填/选股
    触发面 (含 pool_snapshot); 服务面豁免 pool_snapshot (fingerprint 共源)。"""
    api_src, service_src = _feature_sources()
    for module in _imported_module_names(api_src):
        assert not _EXECUTION_TOKEN.search(module), f"查询端点引入了执行族模块: {module}"
        assert not _API_FORBIDDEN_IMPORT_TOKEN.search(module), f"查询端点引入了禁 import 模块: {module}"
    for module in _imported_module_names(service_src):
        assert not _EXECUTION_TOKEN.search(module), f"回测服务引入了执行族模块: {module}"
        assert not _SERVICE_FORBIDDEN_IMPORT_TOKEN.search(module), f"回测服务引入了禁 import 模块: {module}"


def test_backtest_api_is_get_only():
    """research_backtest.py 只允许 GET 路由 (E4 形, BT-09); 写触发独立于 CLI (O1)。"""
    api_src, _service_src = _feature_sources()
    methods = re.findall(r"@router\.(get|post|put|delete|patch)\b", api_src)
    assert methods and set(methods) == {"get"}, f"竞价回测查询 API 出现了非 GET 路由: {methods}"


def test_backtest_no_write_path():
    """查询端点纯读者: 无写模式 open / write_parquet / os.replace / unlink / mkdir
    (E3/E4 形), 且无禁调用 token (批量执行/缓存写/点快照持久化, BT-09)。"""
    api_src, _service_src = _feature_sources()
    for pattern in _WRITE_PATTERNS:
        assert not pattern.search(api_src), f"查询端点出现写路径: {pattern.pattern}"
    for token in _FORBIDDEN_CALL_TOKENS:
        assert token not in api_src, f"查询端点出现了计算触发调用: {token}"


def test_backtest_service_writes_only_backtest_results():
    """E2 根隔离: 服务面全部写调用点的目标路径 (含绑定闭包) 均含 backtest_results
    字面量, 且不含 strategy_cache / screener_results / kline_auction /
    kline_daily_enriched 字面量 (镜像 28-01 'writes only ext_history' 测试)。"""
    _api_src, service_src = _feature_sources()
    binds = _bindings(service_src)
    targets = _write_targets(service_src)
    assert targets, "服务面应存在写调用点 (守卫悬空)"
    for target in targets:
        resolved = _resolve_write_target(target, binds)
        assert "backtest_results" in resolved, (
            f"服务写目标越出 backtest_results 根: {target!r}"
        )
        for forbidden in _WRITE_FORBIDDEN_LITERALS:
            assert forbidden not in resolved, (
                f"服务写目标触碰禁湖字面量 {forbidden!r}: {target!r}"
            )


def test_backtest_no_strategy_cache_reference():
    """守卫目标不得引用「单 as_of 运行期缓存指针」「选股结果湖」字面量 (E3 形)。

    api 面 import 与源码均查; 服务面 import 面查 (34-01 服务 docstring 以散文形式
    声明 E2 纪律, 属文档非引用 —— 实际契约由 E2 写目标闭包断言锁死, 见守卫 5)。"""
    api_src, service_src = _feature_sources()
    for module in _imported_module_names(api_src):
        assert "strategy_cache" not in module, f"查询端点引入了运行时缓存模块: {module}"
    assert "strategy_cache" not in api_src, "查询端点源码引用了 strategy_cache"
    assert "screener_results" not in api_src, "查询端点源码引用了 screener_results"
    assert "write_cache" not in api_src, "查询端点源码引用了 write_cache"
    for module in _imported_module_names(service_src):
        assert "strategy_cache" not in module, f"回测服务引入了运行时缓存模块: {module}"
        assert "write_cache" not in service_src, "回测服务源码引用了 write_cache"


def test_backtest_import_whitelist():
    """守卫目标 import 面 ⊆ 白名单 (api: fastapi/polars/stdlib/app.config;
    服务: polars/stdlib/app.services.{auction_columns,auction_validation,pool_snapshot})。"""
    api_src, service_src = _feature_sources()
    for module in _imported_module_names(api_src):
        assert (
            module in _API_IMPORT_EXACT or any(module.startswith(p) for p in _API_IMPORT_PREFIXES)
        ), f"查询端点 import 越出白名单: {module}"
    for module in _imported_module_names(service_src):
        assert (
            module in _SERVICE_IMPORT_EXACT
            or any(module.startswith(p) for p in _SERVICE_IMPORT_PREFIXES)
        ), f"回测服务 import 越出白名单: {module}"
