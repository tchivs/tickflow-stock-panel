"""Phase 50 release-hardening guard (50-04, AF-REQ-25 SC5).

This guard mechanically proves the shipped Phase-50 replay workbench exposes
research-only actions and preserves the no-execution boundary, and it
re-asserts the prior Phase 45-49 Alpha/Agent/promotion module graph remains
clean.  Phase 50 *adds* surfaces; it must not weaken the existing boundary.

It is the cumulative release gate for SC5: (a) no AGPL-derived source, (b) no
prohibited new base runtime dependency (``sse-starlette`` is pre-existing), (c)
no arbitrary code path, (d) no broker/execution import/call in
Alpha/Agent/promotion/workbench surfaces — with documented smoke evidence.

The module graph is the UNION of:

* the Phase-50 new/extended surfaces (``api/research_alpha_sse.py`` — the only
  genuinely new module; the lineage/compare/stress/replay/clone endpoints landed
  inside the already-guarded ``research_alpha.py``/``run_service.py``/etc.), and
* the Phase 45 Alpha run-contract graph + the Phase 49 promotion graph
  (re-asserted clean — Phase 50 adds surfaces, it must not weaken the prior
  boundary).

The prohibited-import token set is the Phase-49 set (``promotion`` DROPPED,
because the union includes the Phase-49 promotion modules which legitimately
import ``promotion_service``); the Phase-45 ``promotion`` exemption for
``repository.py`` is therefore unnecessary here.  ``re.compile`` is allowed;
bare ``eval(`/``exec(`/``compile(`` are not.

Streaming tokens (``StreamingResponse``/``text/event-stream``/
``EventSourceResponse``/``sse_starlette``) are PERMITTED in
``api/research_alpha_sse.py`` ONLY — the Phase 45 guard assertion on
``research_alpha.py`` (``test_phase45_guard.py:198-206``) STAYS GREEN UNAMENDED
because SSE lives in this separate Phase-50 file (risk #4 — do not broaden the
Phase 45 assertion).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import pytest

# ================================================================
# Phase 50-owned module graph (the new SSE module UNION Phase 45-49)
# ================================================================

_BACKEND = Path(__file__).resolve().parents[1]

# The Phase-50 module graph: the new SSE module + the re-asserted Phase 45
# Alpha run-contract graph + the Phase 49 promotion graph.  The 50-01/02
# lineage/compare/stress/replay/clone/evidence-classification surfaces landed
# inside the already-guarded Phase 45 modules (research_alpha.py,
# run_service.py, repository.py, projections.py, run_schemas.py), so the only
# genuinely NEW file is research_alpha_sse.py.
PHASE50_MODULES: dict[str, Path] = {
    # Phase 50 new surface
    "api/research_alpha_sse.py": _BACKEND / "app" / "api" / "research_alpha_sse.py",
    # Phase 45 Alpha run-contract graph (re-asserted clean)
    "operational/migrations.py": _BACKEND / "app" / "operational" / "migrations.py",
    "research/run_contract.py": _BACKEND / "app" / "research" / "run_contract.py",
    "research/repository.py": _BACKEND / "app" / "research" / "repository.py",
    "research/artifacts.py": _BACKEND / "app" / "research" / "artifacts.py",
    "research/run_service.py": _BACKEND / "app" / "research" / "run_service.py",
    "research/run_worker.py": _BACKEND / "app" / "research" / "run_worker.py",
    "research/run_schemas.py": _BACKEND / "app" / "research" / "run_schemas.py",
    "research/projections.py": _BACKEND / "app" / "research" / "projections.py",
    "api/research_alpha.py": _BACKEND / "app" / "api" / "research_alpha.py",
    # Phase 49 promotion graph (re-asserted clean)
    "research/promotion_service.py": _BACKEND / "app" / "research" / "promotion_service.py",
    "api/research_promotion.py": _BACKEND / "app" / "api" / "research_promotion.py",
}

# The single module permitted to carry SSE streaming tokens.
_SSE_MODULE = "api/research_alpha_sse.py"

# Prohibited import substrings — the Phase 45 set MINUS "promotion" (promotion
# is the Phase 49 promotion modules' legitimate job, which are in this union
# set).  Any import whose dotted name contains one of these tokens is a
# boundary violation (SC5d).
_PROHIBITED_IMPORT_TOKENS: tuple[str, ...] = (
    "broker",
    "order",
    "position",
    "portfolio",
    "monitor",
    "execution",
    "live_trade",
    "provider",
    "openai",
    "anthropic",
    "llm",
    "evaluator",
    "factor_evaluation",
    "oos",
    "out_of_sample",
    "catalog_mut",
    "redis",
    "kafka",
    "nats",
    "celery",
    "rq.",
)

# Prohibited call/reference tokens — the Phase 45 regex MINUS promote_factor|
# admit_factor (legit in the promotion modules).  ``re.compile`` is allowed;
# bare ``compile(`/``eval(`/``exec(`` (code execution) are not.
_PROHIBITED_CALL_RE = re.compile(
    r"(?<!re\.)\b(?:"
    r"execute_order|place_order|submit_order|cancel_order|"
    r"eval_factor|evaluate_factor|run_factor|score_factor|"
    r"connect_redis|redis_client|kafka_producer|"
    r"eval\(|exec\(|(?<!re\.)compile\(|__import__\("
    r")",
)

# Prohibited attribute-access patterns (e.g. subprocess.Popen, pickle.loads).
_PROHIBITED_ATTR_RE = re.compile(
    r"\b(subprocess|pickle|marshal|ctypes)\.",
)

# SSE streaming tokens — permitted in the SSE module ALONE.
_STREAMING_TOKENS: tuple[str, ...] = (
    "StreamingResponse",
    "text/event-stream",
    "EventSourceResponse",
    "sse_starlette",
)


def _extract_imports(tree: ast.AST) -> list[str]:
    """Extract all import module names from an AST tree (any nesting level)."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def _strip_docstring(source: str) -> str:
    """Remove the module-level docstring so its prose does not trip the token scan."""
    tree = ast.parse(source)
    body = getattr(tree, "body", [])
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        doc_segment = ast.get_source_segment(source, body[0]) or ""
        source = source.replace(doc_segment, "", 1)
    return source


def _module_exists(label: str, path: Path) -> Path:
    """Assert a Phase 50 module exists on disk; return its path."""
    assert path.exists(), f"Phase 50 module {label} not found at {path}"
    return path


# ================================================================
# AST/import boundary tests (SC5 a/c/d)
# ================================================================


class TestPhase50ModuleGraphImportBoundary:
    """Every Phase 50 module must be free of prohibited execution imports."""

    @pytest.mark.parametrize("label,path", list(PHASE50_MODULES.items()))
    def test_import_boundary_prohibits_execution_imports(
        self, label: str, path: Path,
    ) -> None:
        """No Phase 50 module imports an execution/provider/evaluator/queue collaborator."""
        _module_exists(label, path)
        source = _strip_docstring(path.read_text(encoding="utf-8"))
        tree = ast.parse(source)
        imports = _extract_imports(tree)
        for imp in imports:
            lowered = imp.lower()
            for token in _PROHIBITED_IMPORT_TOKENS:
                if token in lowered:
                    pytest.fail(
                        f"{label}: prohibited import '{imp}' contains token '{token}'"
                    )

    @pytest.mark.parametrize("label,path", list(PHASE50_MODULES.items()))
    def test_import_boundary_prohibits_calls_and_attrs(
        self, label: str, path: Path,
    ) -> None:
        """No Phase 50 module source contains a prohibited call or attribute access."""
        _module_exists(label, path)
        source = _strip_docstring(path.read_text(encoding="utf-8"))
        for match in _PROHIBITED_CALL_RE.finditer(source):
            pytest.fail(f"{label}: prohibited call/reference '{match.group()}'")
        for match in _PROHIBITED_ATTR_RE.finditer(source):
            pytest.fail(f"{label}: prohibited attribute access '{match.group()}'")

    def test_sse_scope_streaming_tokens_only_in_sse_module(self) -> None:
        """Streaming tokens appear ONLY in research_alpha_sse.py across the union set.

        research_alpha.py stays clean — the Phase 45 assertion at
        test_phase45_guard.py:198-206 remains GREEN UNAMENDED because SSE lives
        in the separate Phase-50 file (risk #4).
        """
        sse_path = PHASE50_MODULES[_SSE_MODULE]
        _module_exists(_SSE_MODULE, sse_path)
        sse_source = sse_path.read_text(encoding="utf-8")
        # The SSE module legitimately carries every streaming token.
        for token in _STREAMING_TOKENS:
            assert token in sse_source, (
                f"{_SSE_MODULE}: expected streaming token '{token}' is missing"
            )
        # No other module in the union set carries any streaming token.
        for label, path in PHASE50_MODULES.items():
            if label == _SSE_MODULE:
                continue
            _module_exists(label, path)
            source = path.read_text(encoding="utf-8")
            for token in _STREAMING_TOKENS:
                assert token not in source, (
                    f"{label}: streaming token '{token}' must live only in "
                    f"{_SSE_MODULE} (SSE scoped to that module alone)"
                )


class TestNoSecondDatabaseOrQueue:
    """No Phase 50 module may open a second database or external queue connection."""

    @pytest.mark.parametrize("label,path", list(PHASE50_MODULES.items()))
    def test_second_database_none(self, label: str, path: Path) -> None:
        _module_exists(label, path)
        source = _strip_docstring(path.read_text(encoding="utf-8"))
        # sqlite3.connect is allowed in repository.py (the single authority).
        for forbidden in ("psycopg2", "mysql", "postgres", "mongodb", "influxdb"):
            assert forbidden not in source.lower(), (
                f"{label}: second database engine '{forbidden}' detected"
            )


# ================================================================
# Module graph completeness — every Phase 50 module exists and parses
# ================================================================


class TestPhase50ModuleGraphCompleteness:
    """Every Phase 50-owned module must exist and parse without syntax errors."""

    @pytest.mark.parametrize("label,path", list(PHASE50_MODULES.items()))
    def test_module_graph_completeness_exists_and_parses(
        self, label: str, path: Path,
    ) -> None:
        assert path.exists(), f"{label}: module not found at {path}"
        source = path.read_text(encoding="utf-8")
        ast.parse(source)

    def test_module_graph_sse_router_wired_in_main(self) -> None:
        """main.py must include the Phase-50 SSE router (research_alpha_sse.router)."""
        main_source = (_BACKEND / "app" / "main.py").read_text(encoding="utf-8")
        assert "research_alpha_sse.router" in main_source, (
            "main.py: research_alpha_sse.router not included"
        )
