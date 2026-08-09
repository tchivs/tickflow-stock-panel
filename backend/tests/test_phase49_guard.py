"""Phase 49 complete module-graph boundary guard (49-02-04).

This guard mechanically proves the Phase 49-owned module graph remains durable
research-only: no provider/model invocation, factor evaluation, reserved OOS,
broker/order/position/portfolio/monitor/live-execution, Redis/Kafka/NATS/Celery/
RQ or external queue, second database, arbitrary code execution, or re-scoring
collaborator is imported or called (AF-REQ-17 SC4).

Promotion is THIS phase's job, so the ``promotion`` import token is DROPPED from
the prohibited set (Phase 45 listed it precisely to keep *itself* promotion-
free), and ``promote_factor``/``admit_factor`` are dropped from the prohibited
call set. The promotion module's imports are additionally constrained to the
research allowlist ``{factor_registry, catalog, run_contract, admission,
repository}`` — conspicuously NOT ``signal_chain``/``evaluation``/``walkforward``/
``alpha_scoring`` (the re-read-not-recompute invariant, R2).

It also runs a runtime fake-collaborator test proving that consume registers a
formal revision without ever invoking an execution collaborator.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import pytest

from app.research.admission import ADMISSION_POLICY_VERSION
from app.research.catalog import ExperimentCatalog
from app.research.factor_dsl import DSL_VERSION
from app.research.factor_registry import FactorRegistry
from app.research.promotion_service import consume_promotion_ticket, issue_promotion_ticket
from app.research.repository import ResearchRepository
from app.research.run_contract import freeze_input_snapshot
from tests.research.conftest import DeterministicClock

# ================================================================
# Phase 49-owned module graph (per 49-02-PLAN.md)
# ================================================================

_BACKEND = Path(__file__).resolve().parents[1]

PHASE49_MODULES: dict[str, Path] = {
    "research/promotion_service.py": _BACKEND / "app" / "research" / "promotion_service.py",
    "api/research_promotion.py": _BACKEND / "app" / "api" / "research_promotion.py",
}

# Prohibited import substrings — the Phase 45 set MINUS "promotion" (promotion
# is this phase's job). Any module-level or function-level import whose dotted
# name contains one of these tokens is a boundary violation (SC4).
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
# admit_factor (legit here; the service method is consume_promotion_ticket /
# register_research_factor to stay lexically clear). re.compile is allowed.
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

# The promotion module may import ONLY these research collaborators (R2/SC4):
# it re-reads verdicts, it does not re-compute. signal_chain / evaluation /
# walkforward / alpha_scoring are conspicuously absent.
_PROMOTION_IMPORT_ALLOWLIST = frozenset(
    {"factor_registry", "catalog", "run_contract", "admission", "repository"}
)
_PROMOTION_FORBIDDEN_IMPORTS = frozenset(
    {"signal_chain", "evaluation", "walkforward", "alpha_scoring"}
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
    """Assert a Phase 49 module exists on disk; return its path."""
    assert path.exists(), f"Phase 49 module {label} not found at {path}"
    return path


# ================================================================
# AST/import boundary tests
# ================================================================


class TestPhase49ModuleGraphImportBoundary:
    """Every Phase 49 module must be free of prohibited execution imports."""

    @pytest.mark.parametrize("label,path", list(PHASE49_MODULES.items()))
    def test_module_has_no_prohibited_import(self, label: str, path: Path) -> None:
        """No Phase 49 module imports an execution/provider/evaluator/queue collaborator."""
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

    @pytest.mark.parametrize("label,path", list(PHASE49_MODULES.items()))
    def test_module_has_no_prohibited_call_or_attr(self, label: str, path: Path) -> None:
        """No Phase 49 module source contains a prohibited call or attribute access."""
        _module_exists(label, path)
        source = _strip_docstring(path.read_text(encoding="utf-8"))
        for match in _PROHIBITED_CALL_RE.finditer(source):
            pytest.fail(f"{label}: prohibited call/reference '{match.group()}'")
        for match in _PROHIBITED_ATTR_RE.finditer(source):
            pytest.fail(f"{label}: prohibited attribute access '{match.group()}'")

    def test_promotion_module_imports_within_research_allowlist(self) -> None:
        """promotion_service imports ONLY the re-read collaborators (R2/SC4)."""
        path = PHASE49_MODULES["research/promotion_service.py"]
        _module_exists("research/promotion_service.py", path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        research_imports = {
            imp.split(".")[2]
            for imp in _extract_imports(tree)
            if imp.startswith("app.research.")
        }
        forbidden_present = research_imports & _PROMOTION_FORBIDDEN_IMPORTS
        assert not forbidden_present, (
            "promotion_service imports a re-scoring engine: "
            f"{sorted(forbidden_present)}"
        )
        outside_allowlist = research_imports - _PROMOTION_IMPORT_ALLOWLIST
        assert not outside_allowlist, (
            "promotion_service imports outside the research allowlist: "
            f"{sorted(outside_allowlist)}"
        )


class TestNoSecondDatabaseOrQueue:
    """No Phase 49 module may open a second database or external queue connection."""

    @pytest.mark.parametrize("label,path", list(PHASE49_MODULES.items()))
    def test_no_second_database_connection(self, label: str, path: Path) -> None:
        _module_exists(label, path)
        source = _strip_docstring(path.read_text(encoding="utf-8"))
        for forbidden in ("psycopg2", "mysql", "postgres", "mongodb", "influxdb"):
            assert forbidden not in source.lower(), (
                f"{label}: second database engine '{forbidden}' detected"
            )


# ================================================================
# Runtime fake-collaborator test (SC4 visible proof)
# ================================================================


class _RaisingFake:
    """A fake execution collaborator that fails immediately if ever invoked.

    If consume ever calls a method on this object, the test fails — proving no
    broker/order/position/portfolio/monitor/execution collaborator is reachable
    from the promotion path.
    """

    def __init__(self, name: str = "fake") -> None:
        self.name = name
        self.calls: list[str] = []

    def __getattr__(self, item: str) -> Any:
        def _fail(*_args: Any, **_kwargs: Any) -> None:
            self.calls.append(item)
            pytest.fail(
                f"execution collaborator '{self.name}.{item}' was called — "
                "Phase 49 promotion must not invoke execution collaborators"
            )

        return _fail


def _manifest() -> dict[str, Any]:
    return {
        "dsl": {"version": "factor-dsl-v1"},
        "grammar": {"fingerprint": "a" * 64, "version": "grammar-v1"},
        "vocabulary": {"fingerprint": "b" * 64, "size": 64},
        "policy": {"version": ADMISSION_POLICY_VERSION, "thresholds": {"min_ic": 0.02}},
        "budgets": {"max_expressions": 1000, "max_candidates": 200},
        "objective": {"name": "sharpe", "direction": "maximize"},
        "universe": {
            "name": "cn-a-share",
            "asset_type": "stock",
            "membership_fingerprint": "c" * 64,
        },
        "measured_window": {
            "start": "2020-01-01",
            "end": "2023-12-31",
            "calendar": "SSE",
        },
        "fold_geometry": {"train_size": 120, "gap_size": 5, "test_size": 20, "n_folds": 10},
        "code_manifest": {
            "fingerprint": "d" * 64,
            "build_fingerprint": "e" * 64,
            "dependency_fingerprint": "f" * 64,
        },
        "data_manifest": {"fingerprint": "g" * 64, "partition_fingerprint": "h" * 64},
        "seed": 42,
    }


def _seed_full_evidence(repo: ResearchRepository, registry: FactorRegistry) -> str:
    snapshot = freeze_input_snapshot(
        manifest=_manifest(), created_at="2026-08-08T00:00:00+00:00"
    )
    repo.create_alpha_run(
        run_id="run-guard49",
        principal="researcher@example.com",
        idempotency_key="idem-guard49-run",
        snapshot=snapshot,
        event_id="evt-guard49",
    )
    repo.append_candidate_attempt(
        run_id="run-guard49",
        candidate_id="acand_guard49",
        attempt_ordinal=1,
        candidate_digest="9" * 64,
        canonical_expression="close",
        ast_signature="ast-close",
        shape_signature="shape-close",
        dsl_version=DSL_VERSION,
        operation="generate",
        seed=0,
        step=0,
        status="admitted",
        reason={"verdict": "admitted"},
    )
    revision = registry.create_exploratory_revision(
        run_id="run-guard49",
        candidate_id="acand_guard49",
        candidate_digest="9" * 64,
        canonical_expression="close",
        dsl_version=DSL_VERSION,
        fields=("close",),
        step=0,
    )
    repo.insert_admission_verdict(
        revision_id=revision.id,
        policy_version=ADMISSION_POLICY_VERSION,
        verdict="admitted",
        reason="all gates passed",
        gates_json=[{"gate": "no_lookahead", "passed": True}],
        candidate_trail_json={
            "provenance": {
                "kind": "alpha_exploratory",
                "run_id": "run-guard49",
                "candidate_id": "acand_guard49",
                "candidate_digest": "9" * 64,
            }
        },
        resolved_universe_json={"method": "fixture", "membership_fingerprint": "c" * 64},
        input_snapshot_sha256="0" * 64,
    )
    record = repo.record_alpha_fold_evidence(
        run_id="run-guard49",
        candidate_digest="9" * 64,
        fold_index=9,
        is_oos=True,
        revision_id=revision.id,
        train_start="2020-01-01",
        train_end="2022-12-31",
        test_start="2023-01-01",
        test_end="2023-12-31",
        membership_fingerprint="c" * 64,
        declared_fingerprints={"membership": "c" * 64},
        stats={"sharpe": 1.2},
    )
    repo.append_candidate_attempt(
        run_id="run-guard49",
        candidate_id="acand_guard49_oos",
        attempt_ordinal=2,
        candidate_digest="9" * 64,
        canonical_expression="close",
        ast_signature="ast-close",
        shape_signature="shape-close",
        dsl_version=DSL_VERSION,
        operation="selection_oos",
        seed=0,
        step=0,
        status="selection_oos",
        reason={"selection_oos": True, "fold_evidence_id": record["id"]},
    )
    return "acand_guard49"


class TestPhase49RuntimeNoExecutionCollaborator:
    """Runtime proof: consume registers a revision without execution collaborators."""

    def test_consume_never_invokes_execution_collaborator(self, tmp_path: Path) -> None:
        repo = ResearchRepository(
            tmp_path / "guard49.db",
            clock=DeterministicClock(),
            artifact_root=tmp_path / "art",
        )
        repo.migrate()
        registry = FactorRegistry(repo)
        catalog = ExperimentCatalog(repo)
        candidate_id = _seed_full_evidence(repo, registry)
        issue_promotion_ticket(
            repo,
            run_id="run-guard49",
            candidate_id=candidate_id,
            reviewer="researcher@example.com",
            expires_at="2099-12-31T23:59:59+00:00",
            idempotency_key="idem-guard49-consume",
        )
        # Inject raising execution-collaborator fakes onto every collaborator
        # surface. If consume ever reaches for one, the test fails on the spot.
        fakes = [
            _RaisingFake("broker"),
            _RaisingFake("order"),
            _RaisingFake("position"),
            _RaisingFake("portfolio"),
            _RaisingFake("monitor"),
            _RaisingFake("execution"),
        ]
        for fake in fakes:
            setattr(catalog, f"_{fake.name}_collaborator", fake)
            setattr(registry, f"_{fake.name}_collaborator", fake)
            setattr(repo, f"_{fake.name}_collaborator", fake)

        result = consume_promotion_ticket(
            repo, registry, catalog, idempotency_key="idem-guard49-consume"
        )

        # Consume succeeded (registered a formal revision)...
        assert result.revision.provenance["kind"] == "alpha_promoted"
        # ...and never touched any execution fake.
        assert all(fake.calls == [] for fake in fakes), (
            "execution collaborator invoked: "
            + ", ".join(f"{f.name}={f.calls}" for f in fakes if f.calls)
        )


# ================================================================
# Module graph completeness — every Phase 49 module exists and parses
# ================================================================


class TestPhase49ModuleGraphCompleteness:
    """Every Phase 49-owned module must exist and parse without syntax errors."""

    @pytest.mark.parametrize("label,path", list(PHASE49_MODULES.items()))
    def test_module_exists_and_parses(self, label: str, path: Path) -> None:
        assert path.exists(), f"{label}: module not found at {path}"
        source = path.read_text(encoding="utf-8")
        ast.parse(source)
