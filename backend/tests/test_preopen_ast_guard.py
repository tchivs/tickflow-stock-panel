"""MON-05 — preopen 评估路径零执行 / 存储隔离 AST 守卫。

扫描面按模块拆分 (OQ-5 / RESEARCH §7; 镜像 tests/test_pool_hub.py E-guard):
- ``strategy/preopen_eval.py`` — 独立只读模块, **整文件**白名单扫描 (仅 stdlib +
  polars + PREOPEN_ALLOWED_FIELDS; monitor.py 本身含策略执行路径 _match_strategy,
  不能整文件扫, OQ-5 正是为此拆分);
- monitor.py ``evaluate_premarket`` / quote_service.py ``evaluate_premarket_alerts`` /
  daily_pipeline.py ``_premarket_pool_preview`` — ``ast.get_source_segment`` 提取函数段后
  同规则断言。

守卫断言 (对 docstring 剥离后的源码 — docstring 是禁令声明文本, 非调用面/写路径):
- import 面 (ast 解析) 无一匹配执行族 token (_EXECUTION_TOKEN, 镜像 test_pool_hub E1);
- 无写路径 pattern (open-w / write_parquet / os.replace / unlink / mkdir);
- 无 run_all / run_all_with_hits / persist_point_snapshot / strategy_cache / write_cache
  触发 token (写侧缺位即证存储隔离);
- monitor.py preopen 段不包含 _match_strategy 文本 (池基线污染点零触碰)。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

# 执行族 token: 出现在 preopen 评估路径 import 面即失败 (镜像 test_pool_hub E1, 逐字)
_EXECUTION_TOKEN = re.compile(
    r"broker|order|execution|trade|portfolio|watchlist|position|account|transaction|下单|委托",
    re.IGNORECASE,
)

_WRITE_PATTERNS = (
    re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']w"),
    re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']wb"),
    re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']a"),
    re.compile(r"write_parquet"),
    re.compile(r"os\.replace"),
    re.compile(r"unlink\s*\("),
    re.compile(r"mkdir\s*\("),
)

# 计算/存储触发 token (T19): preopen 评估路径绝不触发 (缺位即证)
_COMPUTE_TRIGGER_TOKENS = (
    "run_all", "run_all_with_hits", "persist_point_snapshot", "strategy_cache", "write_cache",
)


def _imported_module_names(source: str) -> list[str]:
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def _strip_docstring(src: str, container) -> str:
    """容器 (Module/FunctionDef) 源码, 去掉 docstring 段 (docstring 是禁令声明, 非调用面)。"""
    segment = ast.get_source_segment(src, container) or src
    body = getattr(container, "body", [])
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        doc = ast.get_source_segment(src, body[0]) or ""
        segment = segment.replace(doc, "", 1)
    return segment


def _preopen_sources() -> dict[str, str]:
    """preopen 评估路径源码: preopen_eval 整文件 + 三个函数段 (docstring 剥离)。"""
    backend = Path(__file__).resolve().parents[1]
    sources: dict[str, str] = {}

    eval_path = backend / "app" / "strategy" / "preopen_eval.py"
    eval_src = eval_path.read_text(encoding="utf-8")
    sources["strategy/preopen_eval.py (整文件)"] = _strip_docstring(eval_src, ast.parse(eval_src))

    for path, func_name, label in (
        ("app/strategy/monitor.py", "evaluate_premarket", "monitor.py::evaluate_premarket"),
        ("app/services/quote_service.py", "evaluate_premarket_alerts", "quote_service.py::evaluate_premarket_alerts"),
        ("app/jobs/daily_pipeline.py", "_premarket_pool_preview", "daily_pipeline.py::_premarket_pool_preview"),
    ):
        src = (backend / path).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
                sources[label] = _strip_docstring(src, node)
                break
        else:
            raise AssertionError(f"{path} 中找不到函数 {func_name}")

    return sources


def test_preopen_eval_whole_file_isolated():
    """T19 整文件 (preopen_eval.py): 无执行族 import / 无写路径 / 无计算存储触发。"""
    src = _preopen_sources()["strategy/preopen_eval.py (整文件)"]

    for module in _imported_module_names(src):
        assert not _EXECUTION_TOKEN.search(module), f"preopen_eval.py 引入执行族模块: {module}"
    for pattern in _WRITE_PATTERNS:
        assert not pattern.search(src), f"preopen_eval.py 出现写路径: {pattern.pattern}"
    for token in _COMPUTE_TRIGGER_TOKENS:
        assert token not in src, f"preopen_eval.py 出现计算/存储触发: {token}"


def test_preopen_function_segments_isolated():
    """T19 函数段: 三函数段统一断言 — 无执行族 import / 无写路径 / 无计算存储触发; monitor 段无 _match_strategy。"""
    sources = _preopen_sources()
    for label, src in sources.items():
        if "(整文件)" in label:
            continue
        for module in _imported_module_names(src):
            assert not _EXECUTION_TOKEN.search(module), f"{label} 引入执行族模块: {module}"
        for pattern in _WRITE_PATTERNS:
            assert not pattern.search(src), f"{label} 出现写路径: {pattern.pattern}"
        for token in _COMPUTE_TRIGGER_TOKENS:
            assert token not in src, f"{label} 出现计算/存储触发: {token}"
    assert "_match_strategy" not in sources["monitor.py::evaluate_premarket"], \
        "preopen 评估段触碰池基线污染点 _match_strategy"


def test_preopen_path_no_strategy_cache_or_snapshot_reference():
    """T19 存储隔离: 全部 preopen 评估路径段不含 strategy_cache/write_cache/persist_point_snapshot 引用。"""
    sources = _preopen_sources()
    for label, src in sources.items():
        assert "strategy_cache" not in src, f"{label} 引用 strategy_cache"
        assert "write_cache" not in src, f"{label} 引用 write_cache"
        assert "persist_point_snapshot" not in src, f"{label} 引用 persist_point_snapshot"
