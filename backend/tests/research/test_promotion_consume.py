"""Phase 49 wave 2 — atomic consume → immutable FactorRevision + catalog handoff.

Covers plan 49-02 (AF-REQ-15 SC2 concurrent half + SC3):
- 49-02-01: ``consume_promotion_ticket`` — the §3.1 8-step transaction under
  ``BEGIN IMMEDIATE``, idempotent reconnect, partial-unique at-most-one across
  same- and distinct-ticket concurrency.
- 49-02-02: the formal ``alpha_promoted`` ``FactorRevision`` via a NEW factor_id
  (revision_number=1) with preserved candidate lineage + the promotion
  ``ExperimentSnapshot`` (``summary_kind='promoted-factor'``), and prior runs
  unchanged (INSERTs only).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.research.admission import ADMISSION_POLICY_VERSION
from app.research.catalog import ExperimentCatalog
from app.research.factor_dsl import DSL_VERSION
from app.research.factor_registry import FactorRegistry
from app.research.promotion_service import (
    ALPHA_PROMOTED_KIND,
    PromotionTicketConflict,
    PromotionTicketConsumed,
    PromotionTicketExpired,
    PromotionTicketUnavailable,
    consume_promotion_ticket,
    issue_promotion_ticket,
    register_research_factor,
)
from app.research.repository import ResearchRepository
from app.research.run_contract import freeze_input_snapshot
from tests.research.conftest import DeterministicClock

_FAR_FUTURE = "2099-12-31T23:59:59+00:00"


# ---------------------------------------------------------------------
# Shared fixtures — clock-aware repo + registry + catalog.
# ---------------------------------------------------------------------


@pytest.fixture
def clock() -> DeterministicClock:
    return DeterministicClock()


@pytest.fixture
def repo(tmp_path: Path, clock: DeterministicClock) -> ResearchRepository:
    repository = ResearchRepository(
        tmp_path / "op.db", clock=clock, artifact_root=tmp_path / "art"
    )
    repository.migrate()
    return repository


@pytest.fixture
def registry(repo: ResearchRepository) -> FactorRegistry:
    return FactorRegistry(repo)


@pytest.fixture
def catalog(repo: ResearchRepository) -> ExperimentCatalog:
    return ExperimentCatalog(repo)


# ---------------------------------------------------------------------
# Frozen-evidence seed builders (mirrors test_promotion_ticket.py).
# ---------------------------------------------------------------------


def _admission_manifest() -> dict[str, Any]:
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
        "fold_geometry": {
            "train_size": 120,
            "gap_size": 5,
            "test_size": 20,
            "n_folds": 10,
        },
        "code_manifest": {
            "fingerprint": "d" * 64,
            "build_fingerprint": "e" * 64,
            "dependency_fingerprint": "f" * 64,
        },
        "data_manifest": {
            "fingerprint": "g" * 64,
            "partition_fingerprint": "h" * 64,
        },
        "seed": 42,
    }


def _freeze_run(repo: ResearchRepository, *, run_id: str = "run-consume") -> str:
    snapshot = freeze_input_snapshot(
        manifest=_admission_manifest(), created_at="2026-08-08T00:00:00+00:00"
    )
    repo.create_alpha_run(
        run_id=run_id,
        principal="researcher@example.com",
        idempotency_key=f"idem-{run_id}",
        snapshot=snapshot,
        event_id=f"evt-{run_id}",
    )
    return run_id


def _admitted_candidate(
    repo: ResearchRepository,
    *,
    run_id: str,
    candidate_id: str = "acand_consume",
    candidate_digest: str = "9" * 64,
    canonical_expression: str = "close",
    status: str = "admitted",
) -> str:
    repo.append_candidate_attempt(
        run_id=run_id,
        candidate_id=candidate_id,
        attempt_ordinal=1,
        candidate_digest=candidate_digest,
        canonical_expression=canonical_expression,
        ast_signature="ast-" + canonical_expression,
        shape_signature="shape-" + canonical_expression,
        dsl_version=DSL_VERSION,
        operation="generate",
        seed=0,
        step=0,
        status=status,
        reason={"verdict": status},
    )
    return candidate_id


def _admission_verdict(
    repo: ResearchRepository,
    registry: FactorRegistry,
    *,
    run_id: str,
    candidate_id: str,
    candidate_digest: str,
    canonical_expression: str = "close",
    gate_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    revision = registry.create_exploratory_revision(
        run_id=run_id,
        candidate_id=candidate_id,
        candidate_digest=candidate_digest,
        canonical_expression=canonical_expression,
        dsl_version=DSL_VERSION,
        fields=("close",),
        step=0,
    )
    gates = gate_results if gate_results is not None else [
        {"gate": "no_lookahead", "passed": True},
        {"gate": "coverage", "passed": True},
    ]
    return repo.insert_admission_verdict(
        revision_id=revision.id,
        policy_version=ADMISSION_POLICY_VERSION,
        verdict="admitted",
        reason="all gates passed",
        gates_json=gates,
        candidate_trail_json={
            "provenance": {
                "kind": "alpha_exploratory",
                "run_id": run_id,
                "candidate_id": candidate_id,
                "candidate_digest": candidate_digest,
            },
        },
        resolved_universe_json={"method": "fixture", "membership_fingerprint": "c" * 64},
        input_snapshot_sha256="0" * 64,
    )


def _selection_oos_evidence(
    repo: ResearchRepository,
    registry: FactorRegistry,
    *,
    run_id: str,
    candidate_id: str,
    candidate_digest: str,
    canonical_expression: str = "close",
) -> str:
    revision = registry.find_exploratory_revision(run_id, candidate_digest)
    assert revision is not None
    record = repo.record_alpha_fold_evidence(
        run_id=run_id,
        candidate_digest=candidate_digest,
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
        run_id=run_id,
        candidate_id=candidate_id + "_oos",
        attempt_ordinal=2,
        candidate_digest=candidate_digest,
        canonical_expression=canonical_expression,
        ast_signature="ast-" + canonical_expression,
        shape_signature="shape-" + canonical_expression,
        dsl_version=DSL_VERSION,
        operation="selection_oos",
        seed=0,
        step=0,
        status="selection_oos",
        reason={"selection_oos": True, "fold_evidence_id": record["id"]},
    )
    return record["id"]


def _seed_full_evidence(
    repo: ResearchRepository,
    registry: FactorRegistry,
    *,
    run_id: str = "run-consume",
    candidate_id: str = "acand_consume",
    candidate_digest: str = "9" * 64,
    canonical_expression: str = "close",
) -> tuple[str, str, str]:
    """Seed snapshot + admitted candidate + verdict + selection-OOS + exploratory revision."""
    _freeze_run(repo, run_id=run_id)
    _admitted_candidate(
        repo,
        run_id=run_id,
        candidate_id=candidate_id,
        candidate_digest=candidate_digest,
        canonical_expression=canonical_expression,
    )
    verdict = _admission_verdict(
        repo,
        registry,
        run_id=run_id,
        candidate_id=candidate_id,
        candidate_digest=candidate_digest,
        canonical_expression=canonical_expression,
    )
    oos_id = _selection_oos_evidence(
        repo,
        registry,
        run_id=run_id,
        candidate_id=candidate_id,
        candidate_digest=candidate_digest,
        canonical_expression=canonical_expression,
    )
    return verdict["id"], candidate_id, oos_id


def _issue(
    repo: ResearchRepository,
    *,
    run_id: str,
    candidate_id: str,
    key: str,
    expires_at: str = _FAR_FUTURE,
    reviewer: str = "researcher@example.com",
):
    return issue_promotion_ticket(
        repo,
        run_id=run_id,
        candidate_id=candidate_id,
        reviewer=reviewer,
        expires_at=expires_at,
        idempotency_key=key,
    )


def _count(repo: ResearchRepository, table: str, where: str = "") -> int:
    with repo._connection() as connection:
        return int(
            connection.execute(f"SELECT COUNT(*) FROM {table} {where}").fetchone()[0]
        )


def _formal_revisions(repo: ResearchRepository) -> list[dict[str, Any]]:
    with repo._connection() as connection:
        rows = connection.execute(
            """SELECT revisions.* FROM research_factor_revisions AS revisions
               WHERE json_extract(revisions.provenance_json, '$.kind') = 'alpha_promoted'"""
        ).fetchall()
    return [dict(row) for row in rows]


# =====================================================================
# 49-02-01 — consume_promotion_ticket: atomic consume + idempotency +
#            at-most-one across same- and distinct-ticket concurrency.
# =====================================================================


def test_consume_produces_one_formal_revision_and_flips_consumed(
    repo: ResearchRepository, registry: FactorRegistry, catalog: ExperimentCatalog
) -> None:
    verdict_id, candidate_id, _oos = _seed_full_evidence(repo, registry)
    ticket = _issue(repo, run_id="run-consume", candidate_id=candidate_id, key="idem-1")

    result = consume_promotion_ticket(
        repo, registry, catalog, idempotency_key="idem-1"
    )

    assert isinstance(result, PromotionTicketConsumed)
    assert result.revision.provenance.get("kind") == ALPHA_PROMOTED_KIND
    consumed = repo.get_promotion_ticket(ticket.id)
    assert consumed.status == "consumed"
    assert consumed.produced_factor_revision_id == result.revision.id
    assert consumed.consumed_at is not None
    # Exactly one formal revision was minted.
    assert len(_formal_revisions(repo)) == 1


def test_register_research_factor_is_consume_alias(
    repo: ResearchRepository, registry: FactorRegistry, catalog: ExperimentCatalog
) -> None:
    assert register_research_factor is consume_promotion_ticket
    _seed_full_evidence(repo, registry)
    _issue(repo, run_id="run-consume", candidate_id="acand_consume", key="idem-alias")
    result = register_research_factor(
        repo, registry, catalog, idempotency_key="idem-alias"
    )
    assert result.revision.provenance.get("kind") == ALPHA_PROMOTED_KIND


def test_consume_idempotent_reconnect_returns_same_revision_no_second_mint(
    repo: ResearchRepository, registry: FactorRegistry, catalog: ExperimentCatalog
) -> None:
    _seed_full_evidence(repo, registry)
    _issue(repo, run_id="run-consume", candidate_id="acand_consume", key="idem-recon")

    mint_calls = {"n": 0}

    def _counting_mint(r, reg, c, *, ticket):  # type: ignore[no-untyped-def]
        mint_calls["n"] += 1
        from app.research.promotion_service import _mint_promoted_factor

        return _mint_promoted_factor(r, reg, c, ticket=ticket)

    first = consume_promotion_ticket(
        repo, registry, catalog, idempotency_key="idem-recon", _mint=_counting_mint
    )
    # Sequential repeat: service-level reconnect short-circuits before _mint.
    second = consume_promotion_ticket(
        repo, registry, catalog, idempotency_key="idem-recon", _mint=_counting_mint
    )

    assert second.revision.id == first.revision.id
    assert mint_calls["n"] == 1
    assert len(_formal_revisions(repo)) == 1


def test_consume_already_conflicted_ticket_raises_conflict_and_produces_no_revision(
    repo: ResearchRepository, registry: FactorRegistry, catalog: ExperimentCatalog
) -> None:
    _seed_full_evidence(repo, registry)
    ticket = _issue(
        repo, run_id="run-consume", candidate_id="acand_consume", key="idem-conf"
    )
    repo.set_promotion_ticket_status(
        ticket_id=ticket.id, status="conflicted", conflict_reason_json={"kind": "conflict"}
    )

    with pytest.raises(PromotionTicketConflict):
        consume_promotion_ticket(repo, registry, catalog, idempotency_key="idem-conf")

    assert _formal_revisions(repo) == []


def test_consume_atomic_reconnect_under_lock_returns_existing_revision(
    repo: ResearchRepository, registry: FactorRegistry, catalog: ExperimentCatalog
) -> None:
    """The atomic handoff reconnects when the SAME ticket is already consumed."""
    _seed_full_evidence(repo, registry)
    ticket = _issue(
        repo, run_id="run-consume", candidate_id="acand_consume", key="idem-atomic"
    )
    # First consume commits.
    first = consume_promotion_ticket(
        repo, registry, catalog, idempotency_key="idem-atomic"
    )
    # Re-invoke the atomic handoff directly: it must reconnect, not re-mint.
    result = repo.consume_promotion_ticket_atomic(
        ticket_id=ticket.id,
        factor_id="deadbeef",
        revision_id="deadbeef",
        experiment_id="deadbeef",
        name="must-not-mint",
        provenance={"kind": ALPHA_PROMOTED_KIND},
        resolved_config={},
        input_manifest={},
        metrics={"summary_kind": "promoted-factor"},
        canonical_expression="close",
        dsl_version=DSL_VERSION,
        ast_signature="ast-close",
        shape_signature="shape-close",
        fields=("close",),
        operators=(),
        functions=(),
    )
    assert result["outcome"] == "consumed_reconnect"
    assert result["revision_id"] == first.revision.id
    # No second formal revision was minted.
    assert len(_formal_revisions(repo)) == 1


def test_consume_expired_ticket_raises_and_produces_no_revision(
    repo: ResearchRepository, registry: FactorRegistry, catalog: ExperimentCatalog, clock: DeterministicClock
) -> None:
    _seed_full_evidence(repo, registry)
    ticket = _issue(
        repo,
        run_id="run-consume",
        candidate_id="acand_consume",
        key="idem-expired",
        expires_at=clock.now_iso(),
    )
    clock.advance()  # now > expires_at

    with pytest.raises(PromotionTicketExpired) as exc_info:
        consume_promotion_ticket(repo, registry, catalog, idempotency_key="idem-expired")

    assert exc_info.value.reason["binding"] == "expires_at"
    terminal = repo.get_promotion_ticket(ticket.id)
    assert terminal.status == "expired"
    assert _formal_revisions(repo) == []




def test_consume_missing_ticket_raises_unavailable(
    repo: ResearchRepository, registry: FactorRegistry, catalog: ExperimentCatalog
) -> None:
    with pytest.raises(PromotionTicketUnavailable):
        consume_promotion_ticket(
            repo, registry, catalog, idempotency_key="does-not-exist"
        )


def test_consume_two_distinct_tickets_same_candidate_only_one_survives(
    repo: ResearchRepository, registry: FactorRegistry, catalog: ExperimentCatalog
) -> None:
    """At-most-one revision: the partial unique index gates the second consume.

    Two distinct tickets bind the same candidate. The first consume wins
    (consumed + one revision); the second's atomic UPDATE trips the partial
    consumed-candidate unique index, rolls back its uncommitted revision +
    snapshot, and the ticket goes to conflicted. Net: exactly one revision.
    """
    _seed_full_evidence(repo, registry)
    winner = _issue(
        repo, run_id="run-consume", candidate_id="acand_consume", key="idem-win"
    )
    loser = _issue(
        repo, run_id="run-consume", candidate_id="acand_consume", key="idem-lose"
    )

    first = consume_promotion_ticket(
        repo, registry, catalog, idempotency_key="idem-win"
    )
    with pytest.raises(PromotionTicketConflict):
        consume_promotion_ticket(repo, registry, catalog, idempotency_key="idem-lose")

    assert len(_formal_revisions(repo)) == 1
    winner_row = repo.get_promotion_ticket(winner.id)
    loser_row = repo.get_promotion_ticket(loser.id)
    assert winner_row.status == "consumed"
    assert winner_row.produced_factor_revision_id == first.revision.id
    assert loser_row.status == "conflicted"
    assert loser_row.conflict_reason_json["binding"] == "consumed_candidate_unique"
    # The promotion snapshot count matches the single surviving revision.
    assert _count(repo, "research_experiments", "WHERE originating_run_id LIKE 'promotion:%'") == 1


def test_consume_same_ticket_concurrent_threads_serialize_to_one_revision(
    repo: ResearchRepository, registry: FactorRegistry, catalog: ExperimentCatalog
) -> None:
    """Two concurrent consumes of the SAME ticket serialize under BEGIN IMMEDIATE.

    The winner mints + flips consumed; the loser reconnects under the lock and
    returns the same revision. Both succeed; exactly one revision is minted.
    """
    import concurrent.futures as futures
    import threading

    _seed_full_evidence(repo, registry)
    _issue(
        repo, run_id="run-consume", candidate_id="acand_consume", key="idem-concurrent"
    )
    barrier = threading.Barrier(2)

    def _consume():
        barrier.wait()
        return consume_promotion_ticket(
            repo, registry, catalog, idempotency_key="idem-concurrent"
        )

    with futures.ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(_consume), pool.submit(_consume)]
        results = [f.result(timeout=30) for f in futs]

    assert results[0].revision.id == results[1].revision.id
    assert len(_formal_revisions(repo)) == 1


def test_consume_two_distinct_tickets_concurrent_threads_one_wins(
    repo: ResearchRepository, registry: FactorRegistry, catalog: ExperimentCatalog
) -> None:
    """Two concurrent consumes of DISTINCT tickets for one candidate: one wins."""
    import concurrent.futures as futures
    import threading

    _seed_full_evidence(repo, registry)
    _issue(repo, run_id="run-consume", candidate_id="acand_consume", key="idem-c1")
    _issue(repo, run_id="run-consume", candidate_id="acand_consume", key="idem-c2")
    keys = ["idem-c1", "idem-c2"]
    barrier = threading.Barrier(2)
    outcomes: dict[str, Any] = {}

    def _consume(key: str):
        barrier.wait()
        try:
            result = consume_promotion_ticket(
                repo, registry, catalog, idempotency_key=key
            )
            outcomes[key] = ("consumed", result.revision.id)
        except PromotionTicketConflict:
            outcomes[key] = ("conflicted", None)

    with futures.ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(_consume, k) for k in keys]
        for f in futs:
            f.result(timeout=30)

    statuses = [outcomes[k][0] for k in keys]
    assert sorted(statuses) == ["conflicted", "consumed"]
    assert len(_formal_revisions(repo)) == 1


# =====================================================================
# 49-02-02 — formal FactorRevision + lineage + catalog + prior-runs-unchanged.
# =====================================================================


def test_formal_revision_new_factor_id_revision_one_alpha_promoted_lineage(
    repo: ResearchRepository, registry: FactorRegistry, catalog: ExperimentCatalog
) -> None:
    verdict_id, candidate_id, oos_id = _seed_full_evidence(repo, registry)
    exploratory = registry.find_exploratory_revision("run-consume", "9" * 64)
    assert exploratory is not None
    ticket = _issue(repo, run_id="run-consume", candidate_id=candidate_id, key="idem-lin")

    result = consume_promotion_ticket(repo, registry, catalog, idempotency_key="idem-lin")
    revision = result.revision

    assert revision.factor_id != exploratory.factor_id  # NEW factor_id (OQ-1)
    assert revision.revision_number == 1
    assert revision.provenance["kind"] == ALPHA_PROMOTED_KIND
    assert revision.provenance["source_run_id"] == "run-consume"
    assert revision.provenance["candidate_id"] == candidate_id
    assert revision.provenance["candidate_digest"] == "9" * 64
    assert revision.provenance["source_exploratory_revision_id"] == exploratory.id
    assert revision.provenance["admission_verdict_id"] == verdict_id
    assert revision.provenance["selection_oos_fold_evidence_id"] == oos_id
    assert revision.provenance["promotion_ticket_id"] == ticket.id
    assert revision.provenance["reviewer"] == "researcher@example.com"


def test_formal_revision_in_list_current_exploratory_excluded(
    repo: ResearchRepository, registry: FactorRegistry, catalog: ExperimentCatalog
) -> None:
    """SC3 structural proof: only alpha_promoted revisions appear in the catalog."""
    _seed_full_evidence(repo, registry)
    _issue(repo, run_id="run-consume", candidate_id="acand_consume", key="idem-cat")

    before = registry.list_current()
    assert before == []  # the exploratory revision is excluded

    consume_promotion_ticket(repo, registry, catalog, idempotency_key="idem-cat")

    after = registry.list_current()
    assert len(after) == 1
    assert after[0].provenance["kind"] == ALPHA_PROMOTED_KIND


def test_promotion_snapshot_namespace_metrics_and_evidence_refs(
    repo: ResearchRepository, registry: FactorRegistry, catalog: ExperimentCatalog
) -> None:
    verdict_id, candidate_id, oos_id = _seed_full_evidence(repo, registry)
    ticket = _issue(repo, run_id="run-consume", candidate_id=candidate_id, key="idem-snap")

    result = consume_promotion_ticket(repo, registry, catalog, idempotency_key="idem-snap")

    snapshot = catalog.get(result.experiment_id)
    assert snapshot is not None
    # Promotion-scoped originating_run_id (R6) — no collision with the eval run.
    assert snapshot.originating_run_id == f"promotion:{ticket.id}"
    assert snapshot.factor_revision_id == result.revision.id
    assert snapshot.metrics["summary_kind"] == "promoted-factor"
    assert snapshot.metrics["admission_verdict"]["verdict_id"] == verdict_id
    assert snapshot.metrics["admission_verdict"]["input_snapshot_sha256"] == ticket.snapshot_sha256
    assert snapshot.metrics["selection_oos"]["fold_evidence_id"] == oos_id
    assert snapshot.metrics["factor_lineage"]["factor_id"] == result.revision.factor_id
    assert snapshot.metrics["factor_lineage"]["revision_id"] == result.revision.id
    assert snapshot.metrics["factor_lineage"]["revision_number"] == 1
    assert snapshot.diagnostics["summary_kind"] == "promoted-factor"
    # The snapshot cites the verdict + OOS by id; it does NOT re-bind the verdict
    # to the formal revision (R5) — the verdict row's revision is unchanged.
    verdicts = repo.list_admission_verdicts_for_run("run-consume")
    assert verdicts[0]["revision_id"] != result.revision.id


def test_prior_runs_unchanged_only_new_rows_after_consume(
    repo: ResearchRepository, registry: FactorRegistry, catalog: ExperimentCatalog
) -> None:
    verdict_id, candidate_id, oos_id = _seed_full_evidence(repo, registry)
    _issue(repo, run_id="run-consume", candidate_id=candidate_id, key="idem-pristine")

    def _ledger_digest() -> str:
        with repo._connection() as connection:
            rows = connection.execute(
                "SELECT id, candidate_digest, canonical_expression, status "
                "FROM research_alpha_candidate_attempts WHERE run_id=? ORDER BY id",
                ("run-consume",),
            ).fetchall()
        return json.dumps([dict(r) for r in rows], sort_keys=True)

    revisions_before = _count(repo, "research_factor_revisions")
    experiments_before = _count(repo, "research_experiments")
    fold_evidence_before = _count(repo, "research_alpha_fold_evidence")
    snapshot_before = repo.get_run_snapshot("run-consume")
    ledger_before = _ledger_digest()
    verdict_before = repo.list_admission_verdicts_for_run("run-consume")

    consume_promotion_ticket(repo, registry, catalog, idempotency_key="idem-pristine")

    # Prior-run frozen facts are byte-identical.
    assert repo.get_run_snapshot("run-consume")["snapshot_sha256"] == snapshot_before["snapshot_sha256"]
    assert _ledger_digest() == ledger_before
    assert repo.list_admission_verdicts_for_run("run-consume") == verdict_before
    assert _count(repo, "research_alpha_fold_evidence") == fold_evidence_before
    # Only NEW rows were added: one formal revision + one promotion snapshot.
    assert _count(repo, "research_factor_revisions") == revisions_before + 1
    assert _count(repo, "research_experiments") == experiments_before + 1


def test_consume_never_recomputes_no_admission_or_scoring(
    repo: ResearchRepository, registry: FactorRegistry, catalog: ExperimentCatalog, monkeypatch
) -> None:
    """Consume re-reads verdicts; it never re-runs admission or scoring (R2)."""
    _seed_full_evidence(repo, registry)
    _issue(repo, run_id="run-consume", candidate_id="acand_consume", key="idem-norecompute")

    from app.research import admission as admission_module

    monkeypatch.setattr(admission_module, "run_admission", lambda *a, **k: (_ for _ in ()).throw(AssertionError("recompute")))
    # consume must not call run_admission; if it did, the AssertionError fires.
    result = consume_promotion_ticket(
        repo, registry, catalog, idempotency_key="idem-norecompute"
    )
    assert result.revision.provenance["kind"] == ALPHA_PROMOTED_KIND
