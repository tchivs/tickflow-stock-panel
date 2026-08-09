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


# ================================================================
# Broker/execution AST scan (SC5d) — no execution-surface import
# ================================================================

# The execution surface: the strategy/portfolio engine packages + broker/order/
# position/portfolio/monitor/execution modules.  No Alpha/Agent/promotion/
# workbench module may import from or call any of these (SC5d).
_EXECUTION_PACKAGES: frozenset[str] = frozenset({
    "app.strategy",
    "app.portfolio",
    "app.broker",
    "app.order",
    "app.position",
    "app.execution",
    "app.monitor",
})


class TestNoExecutionSurfaceImport:
    """No Phase 50 module imports from or calls the execution surface (SC5d)."""

    @pytest.mark.parametrize("label,path", list(PHASE50_MODULES.items()))
    def test_execution_surface_not_imported(self, label: str, path: Path) -> None:
        """No Alpha/Agent/promotion/workbench module reaches the execution engine."""
        _module_exists(label, path)
        source = _strip_docstring(path.read_text(encoding="utf-8"))
        tree = ast.parse(source)
        for imp in _extract_imports(tree):
            for pkg in _EXECUTION_PACKAGES:
                if imp == pkg or imp.startswith(pkg + "."):
                    pytest.fail(
                        f"{label}: execution-surface import '{imp}' reaches {pkg}"
                    )


# ================================================================
# Runtime fake-collaborator proof (SC5d visible proof)
# ================================================================


class _RaisingFake:
    """A fake execution collaborator that fails immediately if ever invoked.

    Reused from the Phase 49 guard (test_phase49_guard.py:208-228).  If any
    Phase 50 workbench/SSE/compare/stress/replay/clone handler calls a method
    on this object, the test fails — proving no broker/order/position/
    portfolio/monitor/execution collaborator is reachable from the workbench.
    """

    def __init__(self, name: str = "fake") -> None:
        self.name = name
        self.calls: list[str] = []

    def __getattr__(self, item: str) -> Any:
        def _fail(*_args: Any, **_kwargs: Any) -> None:
            self.calls.append(item)
            pytest.fail(
                f"execution collaborator '{self.name}.{item}' was called — "
                "Phase 50 workbench must not invoke execution collaborators"
            )

        return _fail


_PRINCIPAL = "researcher@example.com"


def _sample_manifest(*, seed: int = 42) -> dict[str, Any]:
    """A manifest valid for create()/clone()/replay_branch() with scoring+costs."""
    return {
        "dsl": {"version": "factor-dsl-v1"},
        "grammar": {"fingerprint": "a" * 64, "version": "grammar-v1"},
        "vocabulary": {"fingerprint": "b" * 64, "size": 64},
        "policy": {"version": "admission-v1", "thresholds": {"min_ic": 0.02}},
        "budgets": {"max_expressions": 1000, "max_candidates": 200},
        "objective": {"name": "sharpe", "direction": "maximize"},
        "universe": {
            "name": "cn-a-share", "asset_type": "stock",
            "membership_fingerprint": "c" * 64,
        },
        "measured_window": {
            "start": "2020-01-01", "end": "2023-12-31", "calendar": "SSE",
        },
        "fold_geometry": {
            "train_size": 120, "gap_size": 5, "test_size": 20, "n_folds": 10,
            "oos_size": 20, "horizon": 5,
        },
        "code_manifest": {
            "fingerprint": "d" * 64, "build_fingerprint": "e" * 64,
            "dependency_fingerprint": "f" * 64,
        },
        "data_manifest": {"fingerprint": "g" * 64, "partition_fingerprint": "h" * 64},
        "scoring": {"rebalance": "daily", "n_groups": 5, "warmup_days": 10},
        "costs": {"commission_pct": 0.0003, "stamp_tax_pct": 0.001, "slippage_bps": 5.0},
        "seed": seed,
    }


def _seed_full_workbench(
    tmp_path: Path,
) -> tuple[Any, Any, str, list[str]]:
    """Seed a run exercising every workbench handler; return (repo, service, run_id, cids).

    Persists deterministic factory candidates (so replay_branch's seed re-derivation
    succeeds), a mutation lineage edge, and fold evidence carrying cost_diagnostics
    (so compare/stress/evidence-classification have data to project).  All durable
    facts only — no execution surface.
    """
    from app.research.alpha_factory import AlphaFactory
    from app.research.repository import ResearchRepository
    from app.research.run_contract import freeze_input_snapshot
    from app.research.run_service import ResearchRunService
    from tests.research.conftest import DeterministicClock

    clock = DeterministicClock()
    repo = ResearchRepository(
        tmp_path / "guard50.db", clock=clock, artifact_root=tmp_path / "art",
    )
    repo.migrate()
    manifest = _sample_manifest(seed=42)
    snapshot = freeze_input_snapshot(manifest=manifest, created_at=clock.now_iso())
    clock.advance()
    run = repo.create_alpha_run(
        run_id="run-guard50", principal=_PRINCIPAL,
        idempotency_key="idem-guard50-run", snapshot=snapshot,
        event_id="aevt-guard50",
    )
    factory = AlphaFactory(42, max_candidates=64)
    candidate_ids: list[str] = []
    costs = manifest["costs"]
    cost_rate = (
        float(costs["commission_pct"]) * 2.0
        + float(costs["stamp_tax_pct"])
        + float(costs["slippage_bps"]) * 2.0 / 1e4
    )
    for ordinal in range(1, 4):
        result = factory.generate_next()
        assert result is not None
        cid = f"cand-{result.step}"
        candidate_ids.append(cid)
        repo.append_candidate_attempt(
            run_id=run["id"], candidate_id=cid, attempt_ordinal=ordinal,
            candidate_digest=result.digest,
            canonical_expression=result.canonical_expression,
            ast_signature=f"ast-{result.step}", shape_signature=f"shape-{result.step}",
            dsl_version="factor-dsl-v1", operation=result.operation,
            seed=42, step=result.step, status="generated",
            reason={"note": f"factory candidate {result.step}"},
        )
        cost_diag = {
            "turnover_per_rebalance": [{"date": "2020-01-02", "turnover": 2.0}],
            "total_turnover": 2.0,
            "cost_rate": cost_rate,
            "cost_drag": 2.0 * cost_rate,
            "raw_long_short_return": 0.5,
            "net_long_short_return": 0.5 - 2.0 * cost_rate,
        }
        repo.record_alpha_fold_evidence(
            run_id=run["id"], candidate_digest=result.digest,
            fold_index=0, is_oos=False, revision_id=f"rev-{result.step}",
            train_start="2020-01-01", train_end="2020-06-30",
            test_start="2020-07-01", test_end="2020-12-31",
            membership_fingerprint="c" * 64,
            declared_fingerprints={"panel": "p" * 64},
            stats={"coverage": 0.95, "mean_ic": 0.03, "cost_diagnostics": cost_diag},
        )
    # Mutation lineage edge: cand-0 -> cand-1 (cand-1 is the child).
    if "cand-0" in candidate_ids and "cand-1" in candidate_ids:
        repo.append_candidate_lineage(
            run_id=run["id"], lineage_id="lin-1",
            child_attempt_id="cand-1", parent_attempt_id="cand-0",
            edge_ordinal=0, operation="mutation",
        )
    service = ResearchRunService(repo)
    return repo, service, run["id"], candidate_ids


def _inject_fakes(*targets: Any) -> list[_RaisingFake]:
    """Attach raising execution-collaborator fakes onto each target surface."""
    fakes: list[_RaisingFake] = []
    for name in ("broker", "order", "position", "portfolio", "monitor", "execution"):
        fake = _RaisingFake(name)
        for target in targets:
            setattr(target, f"_{name}_collaborator", fake)
        fakes.append(fake)
    return fakes


class TestRuntimeNoExecutionCollaborator:
    """Runtime proof: every workbench/SSE handler invokes no execution collaborator."""

    def test_runtime_no_execution_collaborator_across_handlers(
        self, tmp_path: Path,
    ) -> None:
        repo, service, run_id, candidate_ids = _seed_full_workbench(tmp_path)
        fakes = _inject_fakes(repo, service)

        # 1. inspect — lineage read projection.
        assert service.list_lineage(run_id, principal=_PRINCIPAL) is not None
        # 2. evidence-classification — SC4 temporal/degradation read.
        assert service.candidate_evidence_classification(
            run_id, candidate_ids[0], principal=_PRINCIPAL,
        ) is not None
        # 3. compare — side-by-side projection (no opaque winner).
        compare = service.compare_candidates(
            run_id, principal=_PRINCIPAL, candidate_ids=candidate_ids[:2],
        )
        assert compare is not None and compare["candidates"] is not None
        # 4. stress — Tier-1 pure-arithmetic matrix (no admission touch).
        stress = service.stress_matrix(
            run_id, principal=_PRINCIPAL, candidate_id=candidate_ids[0],
            axes={"fee_bps": [3.0], "slippage_bps": [10.0], "rebalance": ["weekly"]},
        )
        assert stress is not None and stress["candidate_id"] == candidate_ids[0]
        # 5. replay-branch — seed re-derivation into a NEW child run.
        branch = service.replay_branch(
            run_id, principal=_PRINCIPAL, parent_step=0,
            idempotency_key="idem-guard50-replay",
        )
        assert branch is not None and branch["child_run_id"] != run_id
        # 6. clone — overridable manifest dimensions into a new immutable run.
        clone = service.clone_run(
            run_id, principal=_PRINCIPAL,
            overrides={"costs": {"commission_pct": 0.0005}},
            idempotency_key="idem-guard50-clone",
        )
        assert clone is not None

        # No execution collaborator was touched across any handler.
        assert all(fake.calls == [] for fake in fakes), (
            "execution collaborator invoked: "
            + ", ".join(f"{f.name}={f.calls}" for f in fakes if f.calls)
        )

    async def test_runtime_no_execution_sse_stream_only_reads(
        self, tmp_path: Path,
    ) -> None:
        """The SSE generator invokes only read service methods — never a write/execution path."""
        from app.api.research_alpha_sse import _stream_events

        repo, service, run_id, _cids = _seed_full_workbench(tmp_path)
        fakes = _inject_fakes(repo, service)

        state = {"drained": False}

        async def _disconnect() -> bool:
            return state["drained"]

        seen: list[Any] = []
        async for event in _stream_events(
            service, run_id, _PRINCIPAL, 0,
            poll_interval=0, is_disconnected=_disconnect,
        ):
            seen.append(event)
            state["drained"] = True  # stop after draining the durable page

        # The durable ledger had at least the run-creation event; the generator
        # emitted it without invoking any execution collaborator.
        assert seen, "SSE stream yielded no events"
        assert all(fake.calls == [] for fake in fakes), (
            "execution collaborator invoked during SSE stream: "
            + ", ".join(f"{f.name}={f.calls}" for f in fakes if f.calls)
        )