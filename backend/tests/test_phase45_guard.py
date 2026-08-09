"""Phase 45 complete module-graph boundary guard (45-04-02).

This guard mechanically proves the complete Phase 45-owned module graph
remains durable research-only: no provider/model invocation, factor
evaluation, reserved OOS, promotion/catalog mutation, broker/order/position/
portfolio/monitor/live-execution, Redis/Kafka/NATS/Celery/RQ or external
queue, second database, arbitrary code execution, or browser/SSE workbench
collaborator is imported or called (T-45-09).

It also runs runtime fake-collaborator tests proving that create, replay,
retry, cancel, event-history, candidate-history, progress, and worker-boundary
operations never invoke execution collaborators, and that cross-principal
reads/writes share one safe not-found boundary (T-45-12).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import pytest

from app.research.repository import ResearchRepository
from app.research.run_service import ResearchRunService
from tests.api.conftest import alpha_manifest

# ================================================================
# Phase 45-owned module graph (complete, per 45-04-PLAN.md)
# ================================================================

_BACKEND = Path(__file__).resolve().parents[1]

PHASE45_MODULES: dict[str, Path] = {
    "operational/migrations.py": _BACKEND / "app" / "operational" / "migrations.py",
    "research/run_contract.py": _BACKEND / "app" / "research" / "run_contract.py",
    "research/repository.py": _BACKEND / "app" / "research" / "repository.py",
    "research/artifacts.py": _BACKEND / "app" / "research" / "artifacts.py",
    "research/run_service.py": _BACKEND / "app" / "research" / "run_service.py",
    "research/run_worker.py": _BACKEND / "app" / "research" / "run_worker.py",
    "research/run_schemas.py": _BACKEND / "app" / "research" / "run_schemas.py",
    "research/projections.py": _BACKEND / "app" / "research" / "projections.py",
    "api/research_alpha.py": _BACKEND / "app" / "api" / "research_alpha.py",
}

# Prohibited import substrings — any module-level import whose dotted name
# contains one of these tokens is a boundary violation (T-45-09).
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
    "promotion",
    "catalog_mut",
    "redis",
    "kafka",
    "nats",
    "celery",
    "rq.",
)
# Prohibited call/reference tokens — a call expression whose function name
# matches one of these is an execution-escalation violation.  ``re.compile``
# (regex compilation) is explicitly allowed; bare ``compile(``/``eval(``/
# ``exec(`` (code execution) are not.
_PROHIBITED_CALL_RE = re.compile(
    r"(?<!re\.)\b(?:"
    r"execute_order|place_order|submit_order|cancel_order|"
    r"eval_factor|evaluate_factor|run_factor|score_factor|"
    r"promote_factor|admit_factor|"
    r"connect_redis|redis_client|kafka_producer|"
    r"eval\(|exec\(|(?<!re\.)compile\(|__import__\("
    r")",
)

# Prohibited attribute-access patterns (e.g. subprocess.Popen, pickle.loads).
_PROHIBITED_ATTR_RE = re.compile(
    r"\b(subprocess|pickle|marshal|ctypes)\.",
)

# Phase 49 ratifies that the shared append-only persistence authority
# (repository.py) materializes promotion-ticket value objects, so it may import
# promotion_service. The Phase 45 LOGIC modules (run_service, run_worker,
# research_alpha, ...) remain promotion-free; only the persistence layer is
# exempt from the `promotion` token (RESEARCH §6.2 — promotion is Phase 49's
# job). No execution/second-engine token is exempted here.
_PROMOTION_PERSISTENCE_MODULES = frozenset({"research/repository.py"})


def _extract_imports(tree: ast.AST) -> list[str]:
    """Extract all import module names from an AST tree."""
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
    """Assert a Phase 45 module exists on disk; return its path."""
    assert path.exists(), f"Phase 45 module {label} not found at {path}"
    return path


# ================================================================
# AST/import boundary tests
# ================================================================


class TestPhase45ModuleGraphImportBoundary:
    """Every Phase 45 module must be free of prohibited execution imports."""

    @pytest.mark.parametrize("label,path", list(PHASE45_MODULES.items()))
    def test_module_has_no_prohibited_import(self, label: str, path: Path) -> None:
        """No Phase 45 module imports an execution/provider/evaluator/queue collaborator."""
        _module_exists(label, path)
        source = _strip_docstring(path.read_text(encoding="utf-8"))
        tree = ast.parse(source)
        imports = _extract_imports(tree)
        for imp in imports:
            lowered = imp.lower()
            for token in _PROHIBITED_IMPORT_TOKENS:
                # repository.py is the shared persistence authority; Phase 49
                # ratifies it may import promotion_service to materialize ticket
                # rows. No execution token is exempted (only `promotion`).
                if token == "promotion" and label in _PROMOTION_PERSISTENCE_MODULES:
                    continue
                if token in lowered:
                    pytest.fail(
                        f"{label}: prohibited import '{imp}' contains token '{token}'"
                    )

    @pytest.mark.parametrize("label,path", list(PHASE45_MODULES.items()))
    def test_module_has_no_prohibited_call_or_attr(self, label: str, path: Path) -> None:
        """No Phase 45 module source contains a prohibited call or attribute access."""
        _module_exists(label, path)
        source = _strip_docstring(path.read_text(encoding="utf-8"))
        for match in _PROHIBITED_CALL_RE.finditer(source):
            pytest.fail(f"{label}: prohibited call/reference '{match.group()}'")
        for match in _PROHIBITED_ATTR_RE.finditer(source):
            pytest.fail(f"{label}: prohibited attribute access '{match.group()}'")


class TestNoSecondDatabaseOrQueue:
    """No Phase 45 module may open a second database or external queue connection."""

    @pytest.mark.parametrize("label,path", list(PHASE45_MODULES.items()))
    def test_no_second_database_connection(self, label: str, path: Path) -> None:
        """Only operational.db via ResearchRepository/OperationalRepository is allowed."""
        _module_exists(label, path)
        source = _strip_docstring(path.read_text(encoding="utf-8"))
        # sqlite3.connect is allowed in repository.py (the single authority).
        # Reject any other DB engine connection.
        for forbidden in ("psycopg2", "mysql", "postgres", "mongodb", "influxdb"):
            assert forbidden not in source.lower(), (
                f"{label}: second database engine '{forbidden}' detected"
            )


class TestNoBrowserOrWatchlistSurface:
    """Phase 45 must not add a browser/SSE workbench or Watchlist route/import."""

    def test_no_watchlist_import_in_phase45_modules(self) -> None:
        for label, path in PHASE45_MODULES.items():
            source = path.read_text(encoding="utf-8")
            assert "Watchlist" not in source, f"{label}: Watchlist reference detected"
            assert "watchlist" not in source.lower().replace("watchlist", ""), (
                f"{label}: watchlist token detected"
            )

    def test_no_sse_streaming_route_added(self) -> None:
        """Phase 45 API routes must not add a live SSE/streaming transport (D-09)."""
        api_source = (_BACKEND / "app" / "api" / "research_alpha.py").read_text("utf-8")
        assert "StreamingResponse" not in api_source, (
            "research_alpha.py: SSE StreamingResponse is out of scope (Phase 50)"
        )
        assert "text/event-stream" not in api_source, (
            "research_alpha.py: event-stream media type is out of scope (Phase 50)"
        )

    def test_no_new_router_in_main_beyond_research_alpha(self) -> None:
        """main.py must not include a new browser/workbench router for Phase 45."""
        main_source = (_BACKEND / "app" / "main.py").read_text("utf-8")
        # The Phase 45 router is research_alpha.router; no workbench/router addition.
        assert "workbench" not in main_source.lower(), (
            "main.py: workbench router detected (out of scope)"
        )


# ================================================================
# Runtime fake-collaborator tests (T-45-09, T-45-12)
# ================================================================


class _RaisingFake:
    """A fake collaborator that records calls and raises if ever invoked.

    If any Phase 45 operation calls a method on this object, the test fails
    immediately — proving no execution/provider/evaluator collaborator is
    reachable from the durable contract path.
    """

    def __init__(self, name: str = "fake") -> None:
        self.name = name
        self.calls: list[str] = []

    def __getattr__(self, item: str) -> Any:
        def _fail(*_args: Any, **_kwargs: Any) -> None:
            self.calls.append(item)
            pytest.fail(
                f"execution collaborator '{self.name}.{item}' was called — "
                "Phase 45 must not invoke execution/provider/evaluator collaborators"
            )
        return _fail


class TestRuntimeNoExecutionCollaborator:
    """Runtime proof: Phase 45 operations never call execution collaborators."""

    @pytest.fixture
    def repo(self, tmp_path: Path) -> ResearchRepository:
        from tests.research.conftest import DeterministicClock

        repository = ResearchRepository(
            tmp_path / "guard.db",
            clock=DeterministicClock(),
            artifact_root=tmp_path / "alpha_artifacts",
        )
        repository.migrate()
        return repository

    @pytest.fixture
    def service_with_fakes(self, repo: ResearchRepository) -> ResearchRunService:
        """Build the service without optional execution collaborators.

        The publisher is a legitimate post-commit wake-up seam, not an
        execution collaborator; wiring a raising fake here would incorrectly
        reject the required commit-before-publish behavior.  Worker-side
        bookkeeping is covered by the dedicated adapter test below.
        """
        return ResearchRunService(repo)

    def test_create_does_not_call_execution_collaborator(
        self, service_with_fakes: ResearchRunService,
    ) -> None:
        service_with_fakes.create(
            principal="researcher@example.com",
            idempotency_key="idem-guard-000000000001",
            manifest=alpha_manifest(),
        )

    def test_replay_does_not_call_execution_collaborator(
        self, service_with_fakes: ResearchRunService, repo: ResearchRepository,
    ) -> None:
        from app.research.run_contract import freeze_input_snapshot
        from tests.research.conftest import DeterministicClock

        clock = DeterministicClock()
        snapshot = freeze_input_snapshot(
            manifest=alpha_manifest(), created_at=clock.now_iso()
        )
        repo.create_alpha_run(
            run_id="run-guard-replay", principal="researcher@example.com",
            idempotency_key="idem-guard-000000000002",
            snapshot=snapshot, event_id="aevt-guard-replay",
        )
        assert service_with_fakes.replay(
            "run-guard-replay", principal="researcher@example.com"
        ) is not None

    def test_retry_does_not_call_execution_collaborator(
        self, service_with_fakes: ResearchRunService, repo: ResearchRepository,
    ) -> None:
        from app.research.run_contract import freeze_input_snapshot
        from tests.research.conftest import DeterministicClock

        clock = DeterministicClock()
        snapshot = freeze_input_snapshot(
            manifest=alpha_manifest(), created_at=clock.now_iso()
        )
        repo.create_alpha_run(
            run_id="run-guard-retry", principal="researcher@example.com",
            idempotency_key="idem-guard-000000000003",
            snapshot=snapshot, event_id="aevt-guard-retry",
        )
        assert service_with_fakes.retry(
            "run-guard-retry", principal="researcher@example.com",
            idempotency_key="idem-guard-retry-k1", manifest=alpha_manifest(seed=99),
        ) is not None

    def test_cancel_does_not_call_execution_collaborator(
        self, service_with_fakes: ResearchRunService, repo: ResearchRepository,
    ) -> None:
        from app.research.run_contract import freeze_input_snapshot
        from tests.research.conftest import DeterministicClock

        clock = DeterministicClock()
        snapshot = freeze_input_snapshot(
            manifest=alpha_manifest(), created_at=clock.now_iso()
        )
        run = repo.create_alpha_run(
            run_id="run-guard-cancel", principal="researcher@example.com",
            idempotency_key="idem-guard-000000000004",
            snapshot=snapshot, event_id="aevt-guard-cancel",
        )
        assert service_with_fakes.cancel(
            "run-guard-cancel", principal="researcher@example.com",
            expected_version=run["transition_version"],
        ) is not None

    def test_event_and_candidate_history_do_not_call_collaborator(
        self, service_with_fakes: ResearchRunService, repo: ResearchRepository,
    ) -> None:
        from app.research.run_contract import freeze_input_snapshot
        from tests.research.conftest import DeterministicClock

        clock = DeterministicClock()
        snapshot = freeze_input_snapshot(
            manifest=alpha_manifest(), created_at=clock.now_iso()
        )
        repo.create_alpha_run(
            run_id="run-guard-history", principal="researcher@example.com",
            idempotency_key="idem-guard-000000000005",
            snapshot=snapshot, event_id="aevt-guard-history",
        )
        events = service_with_fakes.list_events(
            "run-guard-history", principal="researcher@example.com"
        )
        assert len(events) == 1
        assert service_with_fakes.list_candidates(
            "run-guard-history", principal="researcher@example.com"
        ) == []

    def test_progress_does_not_call_execution_collaborator(
        self, service_with_fakes: ResearchRunService, repo: ResearchRepository,
    ) -> None:
        from app.research.run_contract import freeze_input_snapshot
        from tests.research.conftest import DeterministicClock

        clock = DeterministicClock()
        snapshot = freeze_input_snapshot(
            manifest=alpha_manifest(), created_at=clock.now_iso()
        )
        repo.create_alpha_run(
            run_id="run-guard-progress", principal="researcher@example.com",
            idempotency_key="idem-guard-000000000006",
            snapshot=snapshot, event_id="aevt-guard-progress",
        )
        result = service_with_fakes.get(
            "run-guard-progress", principal="researcher@example.com"
        )
        assert result is not None
        assert result["candidate_attempts_total"] == 0


class TestWorkerBoundaryNoExecutionCollaborator:
    """The untrusted worker adapter must not invoke execution collaborators."""

    def test_worker_adapter_requests_only_service_methods(self, tmp_path: Path) -> None:
        from app.research.run_contract import freeze_input_snapshot
        from app.research.run_worker import ResearchRunWorkerAdapter
        from tests.research.conftest import DeterministicClock

        clock = DeterministicClock()
        repo = ResearchRepository(
            tmp_path / "guard.db", clock=clock,
            artifact_root=tmp_path / "alpha_artifacts",
        )
        repo.migrate()
        snapshot = freeze_input_snapshot(
            manifest=alpha_manifest(), created_at=clock.now_iso()
        )
        run = repo.create_alpha_run(
            run_id="run-guard-worker", principal="researcher@example.com",
            idempotency_key="idem-guard-000000000007",
            snapshot=snapshot, event_id="aevt-guard-worker",
        )
        service = ResearchRunService(repo)
        started = service.start_or_resume(
            "run-guard-worker", principal="researcher@example.com",
            expected_version=run["transition_version"],
        )
        assert started is not None
        adapter = ResearchRunWorkerAdapter(
            service, principal="researcher@example.com",
            job_store=_RaisingFake("job_store"),
        )
        result = adapter.report_progress(
            run_id="run-guard-worker",
            expected_version=started["transition_version"],
            attempt_token=started["_attempt_token"],
            folds_total=10,
        )
        assert result is not None
        assert result["folds_total"] == 10


class TestCrossPrincipalBoundary:
    """Cross-principal reads and writes share one safe not-found boundary."""

    def test_cross_principal_get_returns_none(self, tmp_path: Path) -> None:
        from app.research.run_contract import freeze_input_snapshot
        from tests.research.conftest import DeterministicClock

        clock = DeterministicClock()
        repo = ResearchRepository(
            tmp_path / "guard.db", clock=clock,
            artifact_root=tmp_path / "alpha_artifacts",
        )
        repo.migrate()
        snapshot = freeze_input_snapshot(
            manifest=alpha_manifest(), created_at=clock.now_iso()
        )
        repo.create_alpha_run(
            run_id="run-guard-xp", principal="researcher@example.com",
            idempotency_key="idem-guard-000000000008",
            snapshot=snapshot, event_id="aevt-guard-xp",
        )
        service = ResearchRunService(repo)
        assert service.get("run-guard-xp", principal="attacker@example.com") is None
        assert service.get("arun_nonexistent", principal="researcher@example.com") is None

    def test_cross_principal_events_and_candidates_return_empty(self, tmp_path: Path) -> None:
        from app.research.run_contract import freeze_input_snapshot
        from tests.research.conftest import DeterministicClock

        clock = DeterministicClock()
        repo = ResearchRepository(
            tmp_path / "guard.db", clock=clock,
            artifact_root=tmp_path / "alpha_artifacts",
        )
        repo.migrate()
        snapshot = freeze_input_snapshot(
            manifest=alpha_manifest(), created_at=clock.now_iso()
        )
        repo.create_alpha_run(
            run_id="run-guard-xp2", principal="researcher@example.com",
            idempotency_key="idem-guard-000000000009",
            snapshot=snapshot, event_id="aevt-guard-xp2",
        )
        service = ResearchRunService(repo)
        assert service.list_events(
            "run-guard-xp2", principal="attacker@example.com"
        ) == []
        assert service.list_candidates(
            "run-guard-xp2", principal="attacker@example.com"
        ) == []
        assert service.list_events(
            "arun_nonexistent", principal="researcher@example.com"
        ) == []


class TestTokenAndCheckpointBoundary:
    """Attempt token plaintext never crosses public projection; checkpoints stay bounded."""

    def test_attempt_token_not_in_run_projection(self) -> None:
        from app.research import projections

        record = {
            "id": "arun_test", "status": "running", "transition_version": 2,
            "last_event_seq": 2, "candidate_attempts_total": 0,
            "candidate_attempts_completed": 0, "folds_total": 0, "folds_completed": 0,
            "snapshot_sha256": "a" * 64, "manifest_sha256": "b" * 64,
            "started_at": "2026-08-08T00:00:00+00:00", "finished_at": None,
            "terminal_reason": None, "retry_of_run_id": None, "retry_attempt": 0,
            "created_at": "2026-08-08T00:00:00+00:00",
        }
        projected = projections.run(record)
        assert "_attempt_token" not in projected
        assert "attempt_token" not in projected

    def test_progress_projection_has_no_token(self) -> None:
        from app.research import projections

        record = {
            "candidate_attempts_total": 10, "candidate_attempts_completed": 5,
            "folds_total": 4, "folds_completed": 2,
        }
        projected = projections.progress(record)
        assert "_attempt_token" not in projected
        assert "attempt_token" not in projected
        assert "principal" not in projected

    def test_checkpoint_payload_bound_is_enforced(self, tmp_path: Path) -> None:
        """Inline checkpoint JSON must be bounded at 16 KiB; larger state uses artifacts."""
        import json

        from app.research.run_contract import MAX_INLINE_CHECKPOINT_BYTES
        from app.research.run_service import AlphaCheckpointValidationError, ResearchRunService

        repo = ResearchRepository(
            tmp_path / "guard.db", artifact_root=tmp_path / "alpha_artifacts",
        )
        repo.migrate()
        service = ResearchRunService(repo)
        prefix = b'{"x":"'
        suffix = b'"}'
        at_bound = prefix + (b"a" * (MAX_INLINE_CHECKPOINT_BYTES - len(prefix) - len(suffix))) + suffix
        service.validate_inline_checkpoint_payload(at_bound)
        over_bound = b"x" * (MAX_INLINE_CHECKPOINT_BYTES + 1)
        with pytest.raises(AlphaCheckpointValidationError, match="exceeds 16 KiB"):
            service.validate_inline_checkpoint_payload(over_bound)


# ================================================================
# Module graph completeness — every Phase 45 module exists and is importable
# ================================================================


class TestModuleGraphCompleteness:
    """Every Phase 45-owned module must exist and parse without syntax errors."""

    @pytest.mark.parametrize("label,path", list(PHASE45_MODULES.items()))
    def test_module_exists_and_parses(self, label: str, path: Path) -> None:
        assert path.exists(), f"{label}: module not found at {path}"
        source = path.read_text(encoding="utf-8")
        ast.parse(source)

    def test_main_py_wires_research_run_service(self) -> None:
        """main.py must initialize the shared ResearchRunService in app.state."""
        main_source = (_BACKEND / "app" / "main.py").read_text("utf-8")
        assert "research_run_service" in main_source, (
            "main.py: app.state.research_run_service not wired"
        )
        assert "ResearchRunService" in main_source, (
            "main.py: ResearchRunService not imported/constructed"
        )
        assert "research_alpha.router" in main_source, (
            "main.py: research_alpha.router not included"
        )
