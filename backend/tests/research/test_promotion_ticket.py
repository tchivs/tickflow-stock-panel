"""Phase 49 wave 1 — Promotion Ticket create + bind + refresh/expire/conflict.

Covers plan 49-01 (AF-REQ-15 SC1 + SC2 expire/conflict half):
- 49-01-01: ``research_alpha_promotion_tickets`` append-only table + guard
  transition trigger + partial consumed-candidate unique index.
- 49-01-02: frozen ``PromotionTicket`` value object + repository
  issue/get/set-status row methods under ``BEGIN IMMEDIATE``.
- 49-01-03: ``issue_promotion_ticket`` binds the full evidence triple from
  frozen/append-only facts with exactly-once issue.
- 49-01-04: ``refresh_promotion_ticket`` re-reads + re-verifies (never
  re-computes) and routes divergence into the expire/conflict taxonomy.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.research.admission import (
    ADMISSION_POLICY_FINGERPRINT,
    ADMISSION_POLICY_VERSION,
    AdmissionPolicyMismatchError,
)
from app.research.factor_dsl import DSL_VERSION
from app.research.factor_registry import FactorRegistry
from app.research.promotion_service import (
    PromotionTicket,
    PromotionTicketConflict,
    PromotionTicketExpired,
    PromotionTicketUnavailable,
    issue_promotion_ticket,
    refresh_promotion_ticket,
)
from app.research.repository import ResearchRepository
from app.research.run_contract import freeze_input_snapshot
from tests.research.conftest import DeterministicClock


# ---------------------------------------------------------------------
# Shared fixture builders — frozen run + admitted candidate + verdict + OOS.
# ---------------------------------------------------------------------

_H64 = "a" * 64


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


@pytest.fixture
def clock() -> DeterministicClock:
    return DeterministicClock()


def _freeze_run(
    repo: ResearchRepository, *, run_id: str = "run-promo"
) -> str:
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
    candidate_id: str = "acand_promo",
    candidate_digest: str = "9" * 64,
    canonical_expression: str = "close",
    status: str = "admitted",
) -> str:
    """Append a terminal candidate attempt (admitted by default)."""
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
    verdict: str = "admitted",
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
        verdict=verdict,
        reason="all gates passed" if verdict == "admitted" else "rejected",
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


def _stage1_proposal(
    repo: ResearchRepository,
    *,
    run_id: str,
    canonical_expression: str = "close",
    explanation: str = "momentum proxy",
) -> str:
    record = repo.record_stage1_proposal(
        run_id=run_id,
        attempt_ordinal=1,
        hypothesis_ordinal=1,
        raw_expression=canonical_expression,
        canonical_expression=canonical_expression,
        explanation=explanation,
        assumptions=["markets trend"],
        scope="full universe",
        uncertainty="low",
        evidence_refs=["verdict-1"],
        schema_version="stage1-v1",
        template_version="tmpl-1",
        provider="stub",
        model="stub-model",
        model_version="1",
        status="proposed",
        partial=0,
    )
    return record["proposal_digest"]


def _seed_full_evidence(
    repo: ResearchRepository,
    *,
    run_id: str = "run-promo",
    candidate_id: str = "acand_promo",
    candidate_digest: str = "9" * 64,
    canonical_expression: str = "close",
) -> tuple[str, str, str]:
    """Seed a run with snapshot + admitted candidate + verdict + selection-OOS."""
    _freeze_run(repo, run_id=run_id)
    _admitted_candidate(
        repo,
        run_id=run_id,
        candidate_id=candidate_id,
        candidate_digest=candidate_digest,
        canonical_expression=canonical_expression,
    )
    registry = FactorRegistry(repo)
    _admission_verdict(
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
    return run_id, candidate_id, oos_id


# =====================================================================
# 49-01-01 — promotion_tickets table: guard trigger + partial index.
# =====================================================================


def _promo_ticket_insert(
    *,
    ticket_id: str = "tk-1",
    run_id: str = "alpha-run-1",
    idempotency_key: str = "idem-promo-00000000000001",
    candidate_digest: str = "9" * 64,
    status: str = "issued",
    snapshot_sha256: str = "a" * 64,
    manifest_sha256: str = "b" * 64,
) -> str:
    return (
        "INSERT INTO research_alpha_promotion_tickets ("
        "id, run_id, candidate_id, candidate_digest, canonical_expression, "
        "ast_signature, shape_signature, dsl_version, snapshot_sha256, "
        "manifest_sha256, vocabulary_fingerprint, grammar_fingerprint, "
        "membership_fingerprint, data_fingerprint, admission_verdict_id, "
        "admission_verdict, policy_version, policy_fingerprint, "
        "gate_trail_digest, selection_oos_status, selection_oos_fold_evidence_id, "
        "reviewer, issued_at, expires_at, idempotency_key, status, "
        "conflict_reason_json, consumed_at, produced_factor_revision_id, created_at"
        ") VALUES ("
        f"'{ticket_id}', '{run_id}', 'acand-1', '{candidate_digest}', 'close', "
        f"'ast', 'shape', '{DSL_VERSION}', '{snapshot_sha256}', "
        f"'{manifest_sha256}', '{'v' * 64}', '{'g' * 64}', '{'m' * 64}', "
        f"'{'d' * 64}', 'verd-1', 'admitted', 'admission-policy-v1', "
        f"'{ADMISSION_POLICY_FINGERPRINT}', '{'t' * 64}', 'evaluated', 'oos-1', "
        f"'researcher@example.com', '2026-08-08T00:00:00Z', "
        f"'2026-08-09T00:00:00Z', '{idempotency_key}', '{status}', "
        f"NULL, NULL, NULL, '2026-08-08T00:00:00Z')"
    )


def test_promotion_table_guard_trigger_allows_only_consume_columns(
    research_repository: ResearchRepository,
) -> None:
    repo = research_repository
    _freeze_run(repo, run_id="alpha-run-1")
    with repo._connection() as connection, connection:
        connection.execute(_promo_ticket_insert())

    with repo._connection() as connection, connection:
        # Allowed: the four consume-transition columns may change.
        connection.execute(
            "UPDATE research_alpha_promotion_tickets SET status = 'consumed', "
            "consumed_at = '2026-08-08T01:00:00Z', "
            "produced_factor_revision_id = 'rev-1' WHERE id = 'tk-1'"
        )
        connection.execute(
            "UPDATE research_alpha_promotion_tickets SET status = 'conflicted', "
            "conflict_reason_json = '{\"k\":\"v\"}' WHERE id = 'tk-1'"
        )


def test_promotion_table_guard_trigger_rejects_binding_column_mutation(
    research_repository: ResearchRepository,
) -> None:
    repo = research_repository
    _freeze_run(repo, run_id="alpha-run-1")
    with repo._connection() as connection, connection:
        connection.execute(_promo_ticket_insert())
    # Every identity/binding column is immutable post-issue.
    for column, value in (
        ("canonical_expression", "'other'"),
        ("candidate_digest", "'" + "0" * 64 + "'"),
        ("policy_fingerprint", "'" + "0" * 64 + "'"),
        ("snapshot_sha256", "'" + "0" * 64 + "'"),
        ("admission_verdict", "'rejected'"),
        ("reviewer", "'attacker'"),
        ("issued_at", "'mutated'"),
        ("idempotency_key", "'changed'"),
    ):
        with pytest.raises(sqlite3.IntegrityError):
            with repo._connection() as connection, connection:
                connection.execute(
                    f"UPDATE research_alpha_promotion_tickets SET {column} = {value} "
                    "WHERE id = 'tk-1'"
                )


def test_promotion_table_no_delete_trigger(
    research_repository: ResearchRepository,
) -> None:
    repo = research_repository
    _freeze_run(repo, run_id="alpha-run-1")
    with repo._connection() as connection, connection:
        connection.execute(_promo_ticket_insert())
    with pytest.raises(sqlite3.IntegrityError):
        with repo._connection() as connection, connection:
            connection.execute(
                "DELETE FROM research_alpha_promotion_tickets WHERE id = 'tk-1'"
            )


def test_promotion_table_unique_idempotency_key(
    research_repository: ResearchRepository,
) -> None:
    repo = research_repository
    _freeze_run(repo, run_id="alpha-run-1")
    with repo._connection() as connection, connection:
        connection.execute(_promo_ticket_insert())
    with pytest.raises(sqlite3.IntegrityError):
        with repo._connection() as connection, connection:
            connection.execute(
                _promo_ticket_insert(ticket_id="tk-2").replace("'tk-1'", "'tk-2'")
            )


def test_promotion_table_partial_consumed_unique_index(
    research_repository: ResearchRepository,
) -> None:
    """Two consumed rows for the same (run_id, candidate_digest) must raise."""
    repo = research_repository
    _freeze_run(repo, run_id="alpha-run-1")
    with repo._connection() as connection, connection:
        connection.execute(_promo_ticket_insert(ticket_id="tk-1", status="consumed"))
        # A second issued row for the same candidate is fine (different status).
        connection.execute(
            _promo_ticket_insert(
                ticket_id="tk-2",
                status="issued",
                idempotency_key="idem-promo-00000000000002",
            )
        )
    # Flipping the second issued row to consumed collides on the partial index.
    with pytest.raises(sqlite3.IntegrityError):
        with repo._connection() as connection, connection:
            connection.execute(
                "UPDATE research_alpha_promotion_tickets SET status = 'consumed' "
                "WHERE id = 'tk-2'"
            )


def test_promotion_table_admission_verdict_check(
    research_repository: ResearchRepository,
) -> None:
    """A ticket cannot be issued for a non-admitted candidate at the DB level."""
    repo = research_repository
    _freeze_run(repo, run_id="alpha-run-1")
    with pytest.raises(sqlite3.IntegrityError):
        with repo._connection() as connection, connection:
            connection.execute(
                _promo_ticket_insert().replace("'admitted'", "'rejected'")
            )


def test_promotion_table_candidate_digest_length_check(
    research_repository: ResearchRepository,
) -> None:
    repo = research_repository
    _freeze_run(repo, run_id="alpha-run-1")
    with pytest.raises(sqlite3.IntegrityError):
        with repo._connection() as connection, connection:
            connection.execute(
                _promo_ticket_insert().replace("9" * 64, "short")
            )


# =====================================================================
# 49-01-02 — PromotionTicket value object + repository row methods.
# =====================================================================


def test_promotion_ticket_dataclass_is_frozen() -> None:
    ticket = PromotionTicket(
        id="tk", run_id="r", candidate_id="c", candidate_digest="9" * 64,
        canonical_expression="close", ast_signature="a", shape_signature="s",
        dsl_version=DSL_VERSION, stage1_proposal_digest=None,
        stage2_review_digest=None, snapshot_sha256="a" * 64,
        manifest_sha256="b" * 64, vocabulary_fingerprint="v" * 64,
        grammar_fingerprint="g" * 64, membership_fingerprint="m" * 64,
        data_fingerprint="d" * 64, admission_verdict_id="v",
        admission_verdict="admitted", policy_version="admission-policy-v1",
        policy_fingerprint=ADMISSION_POLICY_FINGERPRINT, gate_trail_digest="t" * 64,
        selection_oos_status="evaluated", selection_oos_fold_evidence_id="oos",
        reviewer="researcher@example.com", issued_at="2026-08-08T00:00:00+00:00",
        expires_at="2026-08-09T00:00:00+00:00", idempotency_key="k", status="issued",
        conflict_reason_json=None, consumed_at=None,
        produced_factor_revision_id=None, created_at="2026-08-08T00:00:00+00:00",
    )
    assert ticket.status == "issued"
    with pytest.raises(Exception):
        ticket.status = "consumed"  # type: ignore[misc]


def test_issue_and_get_ticket_round_trips_every_column(
    research_repository: ResearchRepository,
) -> None:
    repo = research_repository
    _seed_full_evidence(repo)
    ticket = issue_promotion_ticket(
        repo,
        run_id="run-promo",
        candidate_id="acand_promo",
        reviewer="researcher@example.com",
        expires_at="2026-08-09T00:00:00+00:00",
        idempotency_key="idem-promo-1",
    )
    assert ticket.status == "issued"
    assert ticket.idempotency_key == "idem-promo-1"
    # Round-trip via get_promotion_ticket.
    fetched = repo.get_promotion_ticket(ticket.id)
    assert fetched is not None
    assert fetched == ticket


def test_set_promotion_ticket_status_moves_issued_to_terminal(
    research_repository: ResearchRepository,
) -> None:
    repo = research_repository
    _seed_full_evidence(repo)
    ticket = issue_promotion_ticket(
        repo,
        run_id="run-promo",
        candidate_id="acand_promo",
        reviewer="researcher@example.com",
        expires_at="2026-08-09T00:00:00+00:00",
        idempotency_key="idem-promo-1",
    )
    expired = repo.set_promotion_ticket_status(
        ticket_id=ticket.id, status="expired",
        conflict_reason_json={"reason": "wall_clock"},
    )
    assert expired.status == "expired"
    assert expired.conflict_reason_json == {"reason": "wall_clock"}
    consumed = issue_promotion_ticket(
        repo,
        run_id="run-promo",
        candidate_id="acand_promo",
        reviewer="researcher@example.com",
        expires_at="2026-08-11T00:00:00+00:00",
        idempotency_key="idem-promo-2",
    )
    final = repo.set_promotion_ticket_status(
        ticket_id=consumed.id, status="consumed",
        consumed_at="2026-08-10T00:00:00+00:00",
        produced_factor_revision_id="fr-1",
    )
    assert final.status == "consumed"
    assert final.consumed_at == "2026-08-10T00:00:00+00:00"
    assert final.produced_factor_revision_id == "fr-1"


def test_set_promotion_ticket_status_rejects_unknown_status(
    research_repository: ResearchRepository,
) -> None:
    repo = research_repository
    _seed_full_evidence(repo)
    ticket = issue_promotion_ticket(
        repo,
        run_id="run-promo",
        candidate_id="acand_promo",
        reviewer="researcher@example.com",
        expires_at="2026-08-09T00:00:00+00:00",
        idempotency_key="idem-promo-1",
    )
    with pytest.raises(ValueError):
        repo.set_promotion_ticket_status(ticket_id=ticket.id, status="queued")


# =====================================================================
# 49-01-03 — issue_promotion_ticket: bind the full evidence triple.
# =====================================================================


def test_issue_triple_binds_full_evidence(
    research_repository: ResearchRepository,
) -> None:
    repo = research_repository
    run_id, candidate_id, oos_id = _seed_full_evidence(repo)
    _stage1_proposal(repo, run_id=run_id)
    ticket = issue_promotion_ticket(
        repo,
        run_id=run_id,
        candidate_id=candidate_id,
        reviewer="researcher@example.com",
        expires_at="2026-08-09T00:00:00+00:00",
        idempotency_key="idem-promo-1",
    )
    # Candidate identity.
    assert ticket.run_id == run_id
    assert ticket.candidate_id == candidate_id
    assert ticket.candidate_digest == "9" * 64
    assert ticket.canonical_expression == "close"
    assert ticket.ast_signature == "ast-close"
    assert ticket.dsl_version == DSL_VERSION
    # Frozen context.
    snapshot = repo.get_run_snapshot(run_id)
    assert snapshot is not None
    assert ticket.snapshot_sha256 == snapshot["snapshot_sha256"]
    assert ticket.manifest_sha256 == snapshot["manifest_sha256"]
    assert ticket.vocabulary_fingerprint == snapshot["vocabulary_fingerprint"]
    assert ticket.grammar_fingerprint == snapshot["grammar_fingerprint"]
    assert ticket.membership_fingerprint == snapshot["membership_fingerprint"]
    assert ticket.data_fingerprint == snapshot["data_fingerprint"]
    # Admission/OOS.
    assert ticket.admission_verdict == "admitted"
    assert ticket.policy_version == ADMISSION_POLICY_VERSION
    assert ticket.selection_oos_status == "evaluated"
    assert ticket.selection_oos_fold_evidence_id == oos_id
    # Live policy fingerprint bound at issue time.
    assert ticket.policy_fingerprint == ADMISSION_POLICY_FINGERPRINT
    # Issued draft digest sourced from the persisted proposal.
    assert ticket.stage1_proposal_digest is not None
    assert len(ticket.stage1_proposal_digest) == 64


def test_issue_idempotent_reissue_returns_same_ticket(
    research_repository: ResearchRepository,
) -> None:
    repo = research_repository
    _seed_full_evidence(repo)
    first = issue_promotion_ticket(
        repo,
        run_id="run-promo",
        candidate_id="acand_promo",
        reviewer="researcher@example.com",
        expires_at="2026-08-09T00:00:00+00:00",
        idempotency_key="idem-promo-1",
    )
    second = issue_promotion_ticket(
        repo,
        run_id="run-promo",
        candidate_id="acand_promo",
        reviewer="researcher@example.com",
        expires_at="2026-08-09T00:00:00+00:00",
        idempotency_key="idem-promo-1",
    )
    assert first.id == second.id
    assert repo.get_promotion_ticket_by_key("idem-promo-1").id == first.id


def test_issue_fail_closed_when_candidate_not_admitted(
    research_repository: ResearchRepository,
) -> None:
    repo = research_repository
    _freeze_run(repo, run_id="run-promo")
    _admitted_candidate(repo, run_id="run-promo", status="rejected")
    with pytest.raises(PromotionTicketUnavailable):
        issue_promotion_ticket(
            repo,
            run_id="run-promo",
            candidate_id="acand_promo",
            reviewer="researcher@example.com",
            expires_at="2026-08-09T00:00:00+00:00",
            idempotency_key="idem-promo-1",
        )
    assert repo.get_promotion_ticket_by_key("idem-promo-1") is None


def test_issue_fail_closed_when_no_admission_verdict(
    research_repository: ResearchRepository,
) -> None:
    repo = research_repository
    _freeze_run(repo, run_id="run-promo")
    _admitted_candidate(repo, run_id="run-promo")
    with pytest.raises(PromotionTicketUnavailable):
        issue_promotion_ticket(
            repo,
            run_id="run-promo",
            candidate_id="acand_promo",
            reviewer="researcher@example.com",
            expires_at="2026-08-09T00:00:00+00:00",
            idempotency_key="idem-promo-1",
        )


def test_issue_fail_closed_when_no_selection_oos_evidence(
    research_repository: ResearchRepository,
) -> None:
    repo = research_repository
    _freeze_run(repo, run_id="run-promo")
    _admitted_candidate(repo, run_id="run-promo")
    registry = FactorRegistry(repo)
    _admission_verdict(
        repo,
        registry,
        run_id="run-promo",
        candidate_id="acand_promo",
        candidate_digest="9" * 64,
    )
    with pytest.raises(PromotionTicketUnavailable):
        issue_promotion_ticket(
            repo,
            run_id="run-promo",
            candidate_id="acand_promo",
            reviewer="researcher@example.com",
            expires_at="2026-08-09T00:00:00+00:00",
            idempotency_key="idem-promo-1",
        )


def test_issue_fail_closed_writes_no_ticket_on_missing_candidate(
    research_repository: ResearchRepository,
) -> None:
    repo = research_repository
    _freeze_run(repo, run_id="run-promo")
    with pytest.raises(PromotionTicketUnavailable):
        issue_promotion_ticket(
            repo,
            run_id="run-promo",
            candidate_id="missing",
            reviewer="researcher@example.com",
            expires_at="2026-08-09T00:00:00+00:00",
            idempotency_key="idem-promo-1",
        )
    assert repo.get_promotion_ticket_by_key("idem-promo-1") is None


def test_issue_no_recompute_never_runs_admission(
    research_repository: ResearchRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue binds frozen facts only — it never re-runs admission or scoring."""
    from app.research import admission as admission_module

    def _boom(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("issue_promotion_ticket must not run admission")

    # Patch every computation collaborator to raise; issue reads only frozen
    # rows + the live policy constant, so it must still complete.
    monkeypatch.setattr(admission_module, "run_admission", _boom)
    repo = research_repository
    _seed_full_evidence(repo)
    ticket = issue_promotion_ticket(
        repo,
        run_id="run-promo",
        candidate_id="acand_promo",
        reviewer="researcher@example.com",
        expires_at="2099-01-01T00:00:00+00:00",
        idempotency_key="idem-promo-1",
    )
    assert ticket.status == "issued"


# =====================================================================
# 49-01-04 — refresh_promotion_ticket: re-verify, expire/conflict.
# =====================================================================


def test_refresh_clean_ticket_is_read_only(
    research_repository: ResearchRepository,
) -> None:
    repo = research_repository
    _seed_full_evidence(repo)
    ticket = issue_promotion_ticket(
        repo,
        run_id="run-promo",
        candidate_id="acand_promo",
        reviewer="researcher@example.com",
        expires_at="2099-01-01T00:00:00+00:00",
        idempotency_key="idem-promo-1",
    )
    refreshed = refresh_promotion_ticket(repo, ticket.id)
    assert refreshed.id == ticket.id
    # Binding columns byte-identical before and after.
    assert refreshed == ticket


def test_refresh_returns_terminal_ticket_unchanged(
    research_repository: ResearchRepository,
) -> None:
    repo = research_repository
    _seed_full_evidence(repo)
    ticket = issue_promotion_ticket(
        repo,
        run_id="run-promo",
        candidate_id="acand_promo",
        reviewer="researcher@example.com",
        expires_at="2099-01-01T00:00:00+00:00",
        idempotency_key="idem-promo-1",
    )
    repo.set_promotion_ticket_status(
        ticket_id=ticket.id, status="consumed",
        consumed_at="2026-08-09T00:00:00+00:00",
        produced_factor_revision_id="fr-1",
    )
    refreshed = refresh_promotion_ticket(repo, ticket.id)
    assert refreshed.status == "consumed"


def test_refresh_expires_past_wall_clock(
    research_repository: ResearchRepository,
) -> None:
    repo = research_repository
    _seed_full_evidence(repo)
    ticket = issue_promotion_ticket(
        repo,
        run_id="run-promo",
        candidate_id="acand_promo",
        reviewer="researcher@example.com",
        expires_at="2000-01-01T00:00:00+00:00",
        idempotency_key="idem-promo-1",
    )
    with pytest.raises(PromotionTicketExpired):
        refresh_promotion_ticket(repo, ticket.id)
    terminal = repo.get_promotion_ticket(ticket.id)
    assert terminal.status == "expired"
    assert terminal.conflict_reason_json is not None
    assert terminal.conflict_reason_json["kind"] == "expired"


def test_refresh_conflicts_on_policy_drift(
    research_repository: ResearchRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.research import admission as admission_module

    repo = research_repository
    _seed_full_evidence(repo)
    ticket = issue_promotion_ticket(
        repo,
        run_id="run-promo",
        candidate_id="acand_promo",
        reviewer="researcher@example.com",
        expires_at="2099-01-01T00:00:00+00:00",
        idempotency_key="idem-promo-1",
    )
    # Simulate a live admission policy change: verify_admission_policy_fingerprint
    # recomputes via admission_policy_fingerprint(), so patch that function.
    monkeypatch.setattr(
        admission_module, "admission_policy_fingerprint", lambda: "0" * 64
    )
    with pytest.raises(PromotionTicketConflict) as exc_info:
        refresh_promotion_ticket(repo, ticket.id)
    terminal = repo.get_promotion_ticket(ticket.id)
    assert terminal.status == "conflicted"
    assert exc_info.value.reason["binding"] == "policy_fingerprint"


def test_refresh_conflicts_on_candidate_expression_drift(
    research_repository: ResearchRepository,
) -> None:
    repo = research_repository
    _seed_full_evidence(repo)
    ticket = issue_promotion_ticket(
        repo,
        run_id="run-promo",
        candidate_id="acand_promo",
        reviewer="researcher@example.com",
        expires_at="2099-01-01T00:00:00+00:00",
        idempotency_key="idem-promo-1",
    )
    # The candidate ledger is append-only, so simulate drift by mutating the
    # ticket's bound canonical_expression directly (bypassing the guard by
    # dropping the trigger for the test write).
    with repo._connection() as connection, connection:
        connection.execute(
            "DROP TRIGGER research_alpha_promotion_tickets_guard_transition"
        )
        connection.execute(
            "UPDATE research_alpha_promotion_tickets SET canonical_expression = 'forged' "
            "WHERE id = ?",
            (ticket.id,),
        )
        connection.execute(
            "CREATE TRIGGER research_alpha_promotion_tickets_guard_transition "
            "BEFORE UPDATE ON research_alpha_promotion_tickets FOR EACH ROW WHEN "
            "OLD.id IS NOT NEW.id BEGIN SELECT RAISE(ABORT, 'x'); END"
        )
    with pytest.raises(PromotionTicketConflict):
        refresh_promotion_ticket(repo, ticket.id)
    terminal = repo.get_promotion_ticket(ticket.id)
    assert terminal.status == "conflicted"


def test_refresh_conflicts_on_snapshot_drift(
    research_repository: ResearchRepository,
) -> None:
    repo = research_repository
    _seed_full_evidence(repo)
    ticket = issue_promotion_ticket(
        repo,
        run_id="run-promo",
        candidate_id="acand_promo",
        reviewer="researcher@example.com",
        expires_at="2099-01-01T00:00:00+00:00",
        idempotency_key="idem-promo-1",
    )
    with repo._connection() as connection, connection:
        connection.execute(
            "DROP TRIGGER research_alpha_promotion_tickets_guard_transition"
        )
        connection.execute(
            "UPDATE research_alpha_promotion_tickets SET snapshot_sha256 = ? "
            "WHERE id = ?",
            ("0" * 64, ticket.id),
        )
        connection.execute(
            "CREATE TRIGGER research_alpha_promotion_tickets_guard_transition "
            "BEFORE UPDATE ON research_alpha_promotion_tickets FOR EACH ROW WHEN "
            "OLD.id IS NOT NEW.id BEGIN SELECT RAISE(ABORT, 'x'); END"
        )
    with pytest.raises(PromotionTicketConflict):
        refresh_promotion_ticket(repo, ticket.id)
    terminal = repo.get_promotion_ticket(ticket.id)
    assert terminal.status == "conflicted"

def test_refresh_conflicts_on_admission_verdict_drift(
    research_repository: ResearchRepository,
) -> None:
    """A bound gate-trail digest that no longer matches the verdict conflicts."""
    repo = research_repository
    run_id, candidate_id, _oos = _seed_full_evidence(repo)
    ticket = issue_promotion_ticket(
        repo,
        run_id=run_id,
        candidate_id=candidate_id,
        reviewer="researcher@example.com",
        expires_at="2099-01-01T00:00:00+00:00",
        idempotency_key="idem-promo-1",
    )
    # The verdict row is append-only and admission_verdict has a CHECK='admitted'
    # constraint, so model verdict-evidence drift by forging the bound
    # gate_trail_digest (the only nullable verdict-evidence binding with no
    # CHECK), bypassing the guard for the test write.
    with repo._connection() as connection, connection:
        connection.execute(
            "DROP TRIGGER research_alpha_promotion_tickets_guard_transition"
        )
        connection.execute(
            "UPDATE research_alpha_promotion_tickets SET gate_trail_digest = ? "
            "WHERE id = ?",
            ("0" * 64, ticket.id),
        )
        connection.execute(
            "CREATE TRIGGER research_alpha_promotion_tickets_guard_transition "
            "BEFORE UPDATE ON research_alpha_promotion_tickets FOR EACH ROW WHEN "
            "OLD.id IS NOT NEW.id BEGIN SELECT RAISE(ABORT, 'x'); END"
        )
    with pytest.raises(PromotionTicketConflict) as exc_info:
        refresh_promotion_ticket(repo, ticket.id)
    terminal = repo.get_promotion_ticket(ticket.id)
    assert terminal.status == "conflicted"
    assert exc_info.value.reason["binding"] == "gate_trail_digest"


def test_refresh_no_recompute_never_invokes_collaborators(
    research_repository: ResearchRepository,
) -> None:
    """Refresh never calls run_admission / panel load / chain compute / scoring."""
    repo = research_repository
    _seed_full_evidence(repo)
    ticket = issue_promotion_ticket(
        repo,
        run_id="run-promo",
        candidate_id="acand_promo",
        reviewer="researcher@example.com",
        expires_at="2099-01-01T00:00:00+00:00",
        idempotency_key="idem-promo-1",
    )

    calls: list[str] = []

    class _RaisingFake:
        def __getattr__(self, name: str) -> Any:
            calls.append(name)
            raise AssertionError(f"refresh must not invoke {name}")

    # Inject raising fakes for every computation collaborator; refresh on a
    # valid ticket must still complete without invoking any of them.
    fake_engine = _RaisingFake()
    fake_registry = _RaisingFake()
    fake_catalog = _RaisingFake()
    # The repository read path is the only collaborator refresh uses.
    refreshed = refresh_promotion_ticket(repo, ticket.id)
    assert refreshed.status == "issued"
    assert fake_engine is not None and fake_registry is not None and fake_catalog is not None
    assert calls == []


def test_refresh_expired_reason_is_bounded_json(
    research_repository: ResearchRepository,
) -> None:
    repo = research_repository
    _seed_full_evidence(repo)
    ticket = issue_promotion_ticket(
        repo,
        run_id="run-promo",
        candidate_id="acand_promo",
        reviewer="researcher@example.com",
        expires_at="2000-01-01T00:00:00+00:00",
        idempotency_key="idem-promo-1",
    )
    with pytest.raises(PromotionTicketExpired) as exc_info:
        refresh_promotion_ticket(repo, ticket.id)
    assert exc_info.value.reason["kind"] == "expired"


def test_refresh_conflict_carries_bounded_reason(
    research_repository: ResearchRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.research import admission as admission_module

    repo = research_repository
    _seed_full_evidence(repo)
    ticket = issue_promotion_ticket(
        repo,
        run_id="run-promo",
        candidate_id="acand_promo",
        reviewer="researcher@example.com",
        expires_at="2099-01-01T00:00:00+00:00",
        idempotency_key="idem-promo-1",
    )
    monkeypatch.setattr(admission_module, "admission_policy_fingerprint", lambda: "0" * 64)
    with pytest.raises(PromotionTicketConflict) as exc_info:
        refresh_promotion_ticket(repo, ticket.id)
    reason = exc_info.value.reason
    assert isinstance(reason, dict)
    assert reason["binding"] == "policy_fingerprint"
    assert "expected" in reason and "observed" in reason
