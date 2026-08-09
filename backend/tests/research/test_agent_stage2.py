"""Stage 2 contract tests for the FactorResearchAgent (AF-REQ-13, AF-REQ-21).

Phase 48-03. Covers:
* 48-03-01 -- StageTwoRequest (frozen snapshot + server evidence) + versioned
  strict (extra='forbid') output schema with NO mutable field (caveats + bounded
  advisory recommendation). disposition is the only action and it is advisory.
* 48-03-02 -- verify_evidence_refs referential-integrity check over evidence_refs
  (candidate/evaluation/gate=verdict-row/artifact); same-run resolves, cross-run
  and fabricated ids are permanent failures (OQ-2).
* 48-03-03 -- Stage2Service (read-only over server evidence) + stage-boundary
  checkpoint (terminal event + checkpoint in one transaction) + advisory-only
  recommendation (no autonomous run).
"""
from __future__ import annotations

import json

import pytest

from app.research.repository import ResearchRepository
from app.research.run_contract import freeze_input_snapshot


# ------------------------------------------------------------------
# Shared fixtures (mirror test_agent_stage1.py conventions)
# ------------------------------------------------------------------


def _manifest(*, seed: int = 42) -> dict:
    return {
        "dsl": {"version": "factor-dsl-v1"},
        "grammar": {"fingerprint": "a" * 64, "version": "grammar-v1"},
        "vocabulary": {"fingerprint": "b" * 64, "size": 64},
        "policy": {"version": "admission-v1", "thresholds": {"min_ic": 0.02}},
        "budgets": {"max_expressions": 1000, "max_candidates": 200},
        "objective": {"name": "sharpe", "direction": "maximize"},
        "universe": {
            "name": "cn-a-share",
            "asset_type": "stock",
            "membership_fingerprint": "c" * 64,
        },
        "measured_window": {"start": "2020-01-01", "end": "2023-12-31", "calendar": "SSE"},
        "fold_geometry": {"train_size": 120, "gap_size": 5, "test_size": 20, "n_folds": 10},
        "code_manifest": {
            "fingerprint": "d" * 64,
            "build_fingerprint": "e" * 64,
            "dependency_fingerprint": "f" * 64,
        },
        "data_manifest": {"fingerprint": "g" * 64, "partition_fingerprint": "h" * 64},
        "seed": seed,
    }


def _make_run(repo: ResearchRepository, *, run_id: str = "run-stage2") -> str:
    snapshot = freeze_input_snapshot(
        manifest=_manifest(), created_at="2026-08-09T00:00:00+00:00"
    )
    repo.create_alpha_run(
        run_id=run_id,
        principal="researcher@example.com",
        idempotency_key=f"idem-{run_id}",
        snapshot=snapshot,
        event_id=f"evt-{run_id}",
    )
    return run_id


def _caveat_dict(**overrides) -> dict:
    base = dict(
        kind="gate_failure",
        claim="Admission IC gate failed on fold 3 with a negative spread.",
        evidence_refs=[{"kind": "candidate", "id": "acand_one"}],
    )
    base.update(overrides)
    return base


def _recommendation_dict(**overrides) -> dict:
    base = dict(
        disposition="inspect",
        rationale="Re-examine the gate trail before promoting.",
        follow_up_run_dims=None,
    )
    base.update(overrides)
    return base


def _stage2_payload(caveats=None, recommendation=None, **overrides) -> dict:
    payload = {
        "schema_version": "factor-stage2-v1",
        "caveats": caveats if caveats is not None else [_caveat_dict()],
        "recommendation": recommendation if recommendation is not None else _recommendation_dict(),
    }
    payload.update(overrides)
    return payload


def _evidence_ref(kind: str, id_: str, **extras) -> dict:
    ref = {"kind": kind, "id": id_}
    ref.update(extras)
    return ref


# ==================================================================
# 48-03-01 -- StageTwoRequest + versioned strict schema (no mutable field)
# ==================================================================


class TestStageTwoRequest:
    def test_stage2_request_valid_construction(self) -> None:
        from app.research.agent_stage2 import ServerEvidence, StageTwoRequest

        evidence = ServerEvidence(
            candidates=(), fold_evidence=(), admission_verdicts=(), selection_summary=None
        )
        request = StageTwoRequest(
            snapshot_ref={"snapshot_sha256": "1" * 64, "manifest_sha256": "2" * 64},
            evidence=evidence,
            budget_hints={"max_caveats": 12},
        )
        assert request.evidence is evidence
        assert request.budget_hints["max_caveats"] == 12

    def test_stage2_request_rejects_non_mapping_snapshot_ref(self) -> None:
        from app.research.agent_stage2 import ServerEvidence, StageTwoRequest

        evidence = ServerEvidence(
            candidates=(), fold_evidence=(), admission_verdicts=(), selection_summary=None
        )
        with pytest.raises(ValueError, match="snapshot_ref"):
            StageTwoRequest(
                snapshot_ref="not-a-mapping",  # type: ignore[arg-type]
                evidence=evidence,
                budget_hints={},
            )

    def test_stage2_request_as_request_scope_is_bounded_json(self) -> None:
        from app.research.agent_stage2 import ServerEvidence, StageTwoRequest
        from app.research.run_contract import canonical_bounded_json

        evidence = ServerEvidence(
            candidates=(
                {"id": "acand_one", "status": "admitted", "canonical_expression": "close"},
            ),
            fold_evidence=(),
            admission_verdicts=(),
            selection_summary={"winner_candidate_id": "acand_one"},
        )
        request = StageTwoRequest(
            snapshot_ref={"snapshot_sha256": "1" * 64, "manifest_sha256": "2" * 64},
            evidence=evidence,
            budget_hints={"max_caveats": 12},
        )
        scope = request.as_request_scope()
        canonical_bounded_json(scope, "stage2 request scope")


class TestDecodeStage2PayloadSchema:
    def test_decode_malformed_json_rejected(self) -> None:
        from app.research.agent_stage2 import decode_stage2_payload

        with pytest.raises(ValueError, match="malformed JSON"):
            decode_stage2_payload("not json at all")

    def test_decode_non_object_rejected(self) -> None:
        from app.research.agent_stage2 import decode_stage2_payload

        with pytest.raises(ValueError, match="JSON object"):
            decode_stage2_payload("[]")

    def test_decode_unknown_top_level_field_rejected(self) -> None:
        from app.research.agent_stage2 import decode_stage2_payload

        raw = json.dumps(_stage2_payload(extra="boom"))
        with pytest.raises(ValueError, match="unsupported field"):
            decode_stage2_payload(raw)

    def test_decode_missing_top_level_field_rejected(self) -> None:
        from app.research.agent_stage2 import decode_stage2_payload

        raw = json.dumps({"schema_version": "factor-stage2-v1"})
        with pytest.raises(ValueError, match="missing field"):
            decode_stage2_payload(raw)

    def test_decode_schema_version_mismatch_rejected(self) -> None:
        from app.research.agent_stage2 import decode_stage2_payload

        raw = json.dumps(
            _stage2_payload(schema_version="factor-stage2-v2")
        )
        with pytest.raises(ValueError, match="schema_version mismatch"):
            decode_stage2_payload(raw)

    def test_decode_unknown_caveat_field_rejected(self) -> None:
        from app.research.agent_stage2 import decode_stage2_payload

        raw = json.dumps(_stage2_payload([_caveat_dict(bogus="x")]))
        with pytest.raises(ValueError, match="unsupported field"):
            decode_stage2_payload(raw)

    def test_decode_missing_required_caveat_field_rejected(self) -> None:
        from app.research.agent_stage2 import decode_stage2_payload

        item = _caveat_dict()
        del item["claim"]
        raw = json.dumps(_stage2_payload([item]))
        with pytest.raises(ValueError, match="missing field"):
            decode_stage2_payload(raw)

    def test_decode_bad_caveat_kind_rejected(self) -> None:
        from app.research.agent_stage2 import decode_stage2_payload

        raw = json.dumps(_stage2_payload([_caveat_dict(kind="not_a_kind")]))
        with pytest.raises(ValueError, match="kind"):
            decode_stage2_payload(raw)

    def test_decode_caveat_evidence_ref_not_object_rejected(self) -> None:
        from app.research.agent_stage2 import decode_stage2_payload

        raw = json.dumps(
            _stage2_payload([_caveat_dict(evidence_refs=["bare-id"])])
        )
        with pytest.raises(ValueError, match="evidence_ref"):
            decode_stage2_payload(raw)

    def test_decode_evidence_ref_unknown_field_rejected(self) -> None:
        from app.research.agent_stage2 import decode_stage2_payload

        raw = json.dumps(
            _stage2_payload(
                [_caveat_dict(evidence_refs=[_evidence_ref("candidate", "acand_one", extra="x")])]  # type: ignore[arg-type]
            )
        )
        with pytest.raises(ValueError, match="unsupported field"):
            decode_stage2_payload(raw)

    def test_decode_evidence_ref_bad_kind_rejected(self) -> None:
        from app.research.agent_stage2 import decode_stage2_payload

        raw = json.dumps(
            _stage2_payload([_caveat_dict(evidence_refs=[_evidence_ref("not_a_kind", "x")])])
        )
        with pytest.raises(ValueError, match="kind"):
            decode_stage2_payload(raw)

    def test_decode_caveat_requires_at_least_one_evidence_ref(self) -> None:
        from app.research.agent_stage2 import decode_stage2_payload

        raw = json.dumps(_stage2_payload([_caveat_dict(evidence_refs=[])]))
        with pytest.raises(ValueError, match="evidence_refs"):
            decode_stage2_payload(raw)

    def test_decode_unknown_recommendation_field_rejected(self) -> None:
        from app.research.agent_stage2 import decode_stage2_payload

        raw = json.dumps(
            _stage2_payload(recommendation=_recommendation_dict(bogus="x"))
        )
        with pytest.raises(ValueError, match="unsupported field"):
            decode_stage2_payload(raw)

    def test_decode_oversized_caveats_rejected(self) -> None:
        from app.research.agent_stage2 import MAX_STAGE2_CAVEATS, decode_stage2_payload

        caveats = [_caveat_dict() for _ in range(MAX_STAGE2_CAVEATS + 1)]
        raw = json.dumps(_stage2_payload(caveats))
        with pytest.raises(ValueError, match="maximum"):
            decode_stage2_payload(raw)

    def test_decode_valid_payload_decodes_to_caveats_and_recommendation(self) -> None:
        from app.research.agent_stage2 import (
            Caveat,
            EvidenceRef,
            Recommendation,
            decode_stage2_payload,
        )

        raw = json.dumps(
            _stage2_payload(
                caveats=[
                    _caveat_dict(
                        kind="narrow_coverage",
                        evidence_refs=[
                            _evidence_ref("candidate", "acand_one"),
                            _evidence_ref("evaluation", "afe_fold1"),
                            _evidence_ref("gate", "verdict_row_1"),
                            _evidence_ref("artifact", "aart_one"),
                        ],
                    ),
                ],
                recommendation=_recommendation_dict(
                    disposition="propose_new_run",
                    follow_up_run_dims=["universe", "window"],
                ),
            )
        )
        caveats, recommendation = decode_stage2_payload(raw)
        assert len(caveats) == 1
        assert isinstance(caveats[0], Caveat)
        assert caveats[0].kind == "narrow_coverage"
        assert all(isinstance(ref, EvidenceRef) for ref in caveats[0].evidence_refs)
        assert [ref.kind for ref in caveats[0].evidence_refs] == [
            "candidate", "evaluation", "gate", "artifact",
        ]
        assert isinstance(recommendation, Recommendation)
        assert recommendation.disposition == "propose_new_run"
        assert recommendation.follow_up_run_dims == ("universe", "window")

    def test_decode_empty_caveats_with_no_action_allowed(self) -> None:
        from app.research.agent_stage2 import decode_stage2_payload

        raw = json.dumps(
            _stage2_payload(caveats=[], recommendation=_recommendation_dict(disposition="no_action"))
        )
        caveats, recommendation = decode_stage2_payload(raw)
        assert caveats == ()
        assert recommendation.disposition == "no_action"
        assert recommendation.follow_up_run_dims is None

    def test_decode_propose_new_run_with_null_follow_up_dims_allowed(self) -> None:
        from app.research.agent_stage2 import decode_stage2_payload

        raw = json.dumps(
            _stage2_payload(
                recommendation=_recommendation_dict(
                    disposition="propose_new_run", follow_up_run_dims=None,
                )
            )
        )
        _, recommendation = decode_stage2_payload(raw)
        assert recommendation.disposition == "propose_new_run"
        assert recommendation.follow_up_run_dims is None

    def test_decode_is_pure_does_not_mutate_input(self) -> None:
        from app.research.agent_stage2 import decode_stage2_payload

        raw = json.dumps(_stage2_payload())
        original = raw
        decode_stage2_payload(raw)
        assert raw == original


class TestNoMutableFieldEnforcement:
    """T-48-03a: a mutable field (expression/metric/threshold/oos/admission/
    score/override, incl. aliases) is rejected at any nesting level."""

    @pytest.mark.parametrize(
        "mutable_field",
        [
            "expression",
            "metric",
            "threshold",
            "oos",
            "admission",
            "score",
            "override",
            # Aliased forms (substring matches) must also be rejected.
            "expression_override",
            "oos_flag",
            "threshold_value",
            "admission_override",
        ],
    )
    def test_mutable_field_at_top_level_rejected(self, mutable_field: str) -> None:
        from app.research.agent_stage2 import decode_stage2_payload

        raw = json.dumps(_stage2_payload(**{mutable_field: "smuggled"}))
        with pytest.raises(ValueError, match="forbidden mutable field"):
            decode_stage2_payload(raw)

    @pytest.mark.parametrize(
        "mutable_field",
        ["expression", "metric", "threshold", "oos", "admission", "score", "override"],
    )
    def test_mutable_field_inside_caveat_rejected(self, mutable_field: str) -> None:
        from app.research.agent_stage2 import decode_stage2_payload

        caveat = _caveat_dict()
        caveat[mutable_field] = "smuggled"
        raw = json.dumps(_stage2_payload([caveat]))
        with pytest.raises(ValueError, match="forbidden mutable field"):
            decode_stage2_payload(raw)

    @pytest.mark.parametrize(
        "mutable_field",
        ["expression", "metric", "threshold", "oos", "admission", "score", "override"],
    )
    def test_mutable_field_inside_recommendation_rejected(self, mutable_field: str) -> None:
        from app.research.agent_stage2 import decode_stage2_payload

        recommendation = _recommendation_dict()
        recommendation[mutable_field] = "smuggled"
        raw = json.dumps(_stage2_payload(recommendation=recommendation))
        with pytest.raises(ValueError, match="forbidden mutable field"):
            decode_stage2_payload(raw)

    def test_mutable_field_inside_evidence_ref_rejected(self) -> None:
        from app.research.agent_stage2 import decode_stage2_payload

        ref = _evidence_ref("candidate", "acand_one")
        ref["threshold"] = 0.05
        raw = json.dumps(_stage2_payload([_caveat_dict(evidence_refs=[ref])]))
        with pytest.raises(ValueError, match="forbidden mutable field"):
            decode_stage2_payload(raw)



# ==================================================================
# 48-03-02 -- verify_evidence_refs referential-integrity check (OQ-2)
# ==================================================================


_DIGEST_A = "a" * 64
_DIGEST_B = "b" * 64
_MEMBERSHIP = "c" * 64


def _seed_candidate(repo: ResearchRepository, *, run_id: str, candidate_id: str) -> str:
    repo.append_candidate_attempt(
        run_id=run_id,
        candidate_id=candidate_id,
        attempt_ordinal=1,
        candidate_digest=_DIGEST_A,
        canonical_expression="close",
        ast_signature="ast",
        shape_signature="shape",
        dsl_version="factor-dsl-v1",
        operation="seed",
        seed=1,
        step=0,
        status="rejected",
        reason={"verdict": "rejected", "failing_gate": "min_ic", "gate_trail": []},
    )
    return candidate_id


def _seed_fold_evidence(repo: ResearchRepository, *, run_id: str, revision_id: str) -> str:
    row = repo.record_alpha_fold_evidence(
        run_id=run_id,
        candidate_digest=_DIGEST_A,
        fold_index=0,
        is_oos=False,
        revision_id=revision_id,
        train_start="2020-01-01",
        train_end="2020-06-01",
        test_start="2020-06-02",
        test_end="2020-06-30",
        membership_fingerprint=_MEMBERSHIP,
        declared_fingerprints={"grammar": "a" * 64},
        stats={"ic": 0.01},
    )
    return str(row["id"])


def _seed_admission_verdict(
    repo: ResearchRepository, *, run_id: str, candidate_id: str, revision_id: str
) -> str:
    repo.create_factor_with_revision(
        factor_id="fac_" + revision_id,
        revision_id=revision_id,
        name="seed",
        description="seed revision",
        hypothesis="seed",
        canonical_expression="close",
        dsl_version="factor-dsl-v1",
        ast_signature="ast",
        shape_signature="shape",
        fields=frozenset({"close"}),
        operators=frozenset({}),
        functions=frozenset({}),
        provenance={"run_id": run_id, "candidate_id": candidate_id, "candidate_digest": _DIGEST_A},
    )
    row = repo.insert_admission_verdict(
        revision_id=revision_id,
        policy_version="admission-v1",
        verdict="rejected",
        reason="min_ic gate failed",
        gates_json=[{"name": "min_ic", "observed": 0.0, "threshold": 0.02, "passed": False}],
        candidate_trail_json={
            "provenance": {
                "run_id": run_id,
                "candidate_id": candidate_id,
                "candidate_digest": _DIGEST_A,
            },
            "evaluation_run_ids": [],
            "experiment_snapshot_ids": [],
            "gate_results": [],
        },
        resolved_universe_json={"membership_fingerprint": _MEMBERSHIP},
        input_snapshot_sha256=_DIGEST_B,
    )
    return str(row["id"])


def _seed_artifact(repo: ResearchRepository, *, run_id: str, artifact_id: str) -> str:
    import sqlite3

    with repo._connection() as connection, connection:
        connection.execute(
            """INSERT INTO research_alpha_artifacts
               (id, run_id, logical_kind, relative_path, content_type,
                byte_size, checksum_sha256, schema_version, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                artifact_id, run_id, "evidence",
                f"research_artifacts/alpha_runs/{run_id}/{_DIGEST_A}.json",
                "application/json", 16, _DIGEST_A,
                "alpha-artifact-v1", "2026-08-09T00:00:00+00:00",
            ),
        )
    return artifact_id


class TestReferentialIntegrity:
    """T-48-03b / OQ-2: every cited evidence id resolves within the same run."""

    def test_valid_same_run_citations_across_all_four_kinds_resolve(self, tmp_path) -> None:
        from app.research.agent_stage2 import EvidenceRef, verify_evidence_refs

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        run_id = _make_run(repo)
        candidate_id = _seed_candidate(repo, run_id=run_id, candidate_id="acand_one")
        fold_id = _seed_fold_evidence(repo, run_id=run_id, revision_id="rev_one")
        verdict_id = _seed_admission_verdict(
            repo, run_id=run_id, candidate_id=candidate_id, revision_id="rev_one"
        )
        artifact_id = _seed_artifact(repo, run_id=run_id, artifact_id="aart_one")

        refs = (
            EvidenceRef(kind="candidate", id=candidate_id),
            EvidenceRef(kind="evaluation", id=fold_id),
            EvidenceRef(kind="gate", id=verdict_id),
            EvidenceRef(kind="artifact", id=artifact_id),
        )
        # Resolves -- no exception.
        verify_evidence_refs(refs, repo=repo, run_id=run_id)

    def test_fabricated_candidate_id_rejected(self, tmp_path) -> None:
        from app.research.agent_stage2 import (
            EvidenceRef,
            ReferentialIntegrityError,
            verify_evidence_refs,
        )

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        run_id = _make_run(repo)
        with pytest.raises(ReferentialIntegrityError) as exc_info:
            verify_evidence_refs(
                (EvidenceRef(kind="candidate", id="acand_missing"),),
                repo=repo,
                run_id=run_id,
            )
        # The bounded detail names the offending {kind, id}.
        assert "candidate" in str(exc_info.value)
        assert "acand_missing" in str(exc_info.value)

    def test_cross_run_candidate_id_rejected(self, tmp_path) -> None:
        from app.research.agent_stage2 import (
            EvidenceRef,
            ReferentialIntegrityError,
            verify_evidence_refs,
        )

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        _make_run(repo, run_id="run-a")
        _make_run(repo, run_id="run-b")
        _seed_candidate(repo, run_id="run-a", candidate_id="acand_a")
        with pytest.raises(ReferentialIntegrityError):
            verify_evidence_refs(
                (EvidenceRef(kind="candidate", id="acand_a"),),
                repo=repo,
                run_id="run-b",
            )

    def test_fabricated_evaluation_id_rejected(self, tmp_path) -> None:
        from app.research.agent_stage2 import (
            EvidenceRef,
            ReferentialIntegrityError,
            verify_evidence_refs,
        )

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        run_id = _make_run(repo)
        with pytest.raises(ReferentialIntegrityError):
            verify_evidence_refs(
                (EvidenceRef(kind="evaluation", id="afe_missing"),),
                repo=repo,
                run_id=run_id,
            )

    def test_fabricated_artifact_id_rejected(self, tmp_path) -> None:
        from app.research.agent_stage2 import (
            EvidenceRef,
            ReferentialIntegrityError,
            verify_evidence_refs,
        )

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        run_id = _make_run(repo)
        with pytest.raises(ReferentialIntegrityError):
            verify_evidence_refs(
                (EvidenceRef(kind="artifact", id="aart_missing"),),
                repo=repo,
                run_id=run_id,
            )

    def test_gate_verdict_row_from_another_run_rejected(self, tmp_path) -> None:
        from app.research.agent_stage2 import (
            EvidenceRef,
            ReferentialIntegrityError,
            verify_evidence_refs,
        )

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        _make_run(repo, run_id="run-a")
        _make_run(repo, run_id="run-b")
        _seed_candidate(repo, run_id="run-a", candidate_id="acand_a")
        verdict_id = _seed_admission_verdict(
            repo, run_id="run-a", candidate_id="acand_a", revision_id="rev_a"
        )
        # The verdict is bound to run-a; citing it from run-b is a cross-run ref.
        with pytest.raises(ReferentialIntegrityError):
            verify_evidence_refs(
                (EvidenceRef(kind="gate", id=verdict_id),),
                repo=repo,
                run_id="run-b",
            )

    def test_gate_non_verdict_id_resolves_to_nothing(self, tmp_path) -> None:
        from app.research.agent_stage2 import (
            EvidenceRef,
            ReferentialIntegrityError,
            verify_evidence_refs,
        )

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        run_id = _make_run(repo)
        # A candidate id is NOT a verdict row -- a gate ref to it must not resolve.
        candidate_id = _seed_candidate(repo, run_id=run_id, candidate_id="acand_one")
        with pytest.raises(ReferentialIntegrityError):
            verify_evidence_refs(
                (EvidenceRef(kind="gate", id=candidate_id),),
                repo=repo,
                run_id=run_id,
            )

    def test_verify_evidence_refs_read_only_no_mutation(self, tmp_path) -> None:
        from app.research.agent_stage2 import EvidenceRef, verify_evidence_refs

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        run_id = _make_run(repo)
        candidate_id = _seed_candidate(repo, run_id=run_id, candidate_id="acand_one")
        before = repo.list_candidates(run_id)
        verify_evidence_refs(
            (EvidenceRef(kind="candidate", id=candidate_id),),
            repo=repo,
            run_id=run_id,
        )
        after = repo.list_candidates(run_id)
        assert before == after  # the check performs only bounded SELECT reads

    def test_verify_evidence_refs_empty_iterable_passes(self, tmp_path) -> None:
        from app.research.agent_stage2 import verify_evidence_refs

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        run_id = _make_run(repo)
        verify_evidence_refs((), repo=repo, run_id=run_id)

    def test_referential_integrity_error_is_value_error(self) -> None:
        from app.research.agent_stage2 import ReferentialIntegrityError

        assert issubclass(ReferentialIntegrityError, ValueError)


# ==================================================================
# 48-03-03 -- Stage2Service (read-only) + stage-boundary checkpoint
# ==================================================================


def _make_started_run(repo: ResearchRepository, *, run_id: str = "run-stage2") -> dict:
    from app.research.run_service import ResearchRunService

    _make_run(repo, run_id=run_id)
    run = repo.get_alpha_run(run_id, principal="researcher@example.com")
    assert run is not None
    started = ResearchRunService(repo).start_or_resume(
        run_id, principal="researcher@example.com",
        expected_version=run["transition_version"],
    )
    assert started is not None
    return started


def _seed_full_evidence(repo: ResearchRepository, *, run_id: str) -> dict:
    candidate_id = _seed_candidate(repo, run_id=run_id, candidate_id="acand_one")
    fold_id = _seed_fold_evidence(repo, run_id=run_id, revision_id="rev_one")
    verdict_id = _seed_admission_verdict(
        repo, run_id=run_id, candidate_id=candidate_id, revision_id="rev_one"
    )
    artifact_id = _seed_artifact(repo, run_id=run_id, artifact_id="aart_one")
    return {
        "candidate_id": candidate_id,
        "fold_id": fold_id,
        "verdict_id": verdict_id,
        "artifact_id": artifact_id,
    }


def _stage2_service():
    from app.research.agent_stage2 import Stage2Service

    return Stage2Service(
        provider="offline_fake", model="offline-fixture", model_version="offline-v1"
    )


def _generate_returning(raw: str):
    async def _generate(*_args, **_kwargs) -> str:
        return raw

    return _generate


def _generate_raising(error: BaseException):
    async def _generate(*_args, **_kwargs) -> str:
        raise error

    return _generate


class _FakeRecorder:
    def __init__(self, repo: ResearchRepository) -> None:
        self._repo = repo

    def __call__(self, **kwargs):
        return self._repo.record_analysis_attempt(**kwargs)


def _seam(repo: ResearchRepository, generate_text):
    from app.research.agent_provider import AgentProviderSeam

    return AgentProviderSeam(
        generate_text=generate_text, record_analysis_attempt=_FakeRecorder(repo)
    )


def _evidence_citing_payload(ids: dict, *, disposition: str = "inspect") -> str:
    caveats = [
        _caveat_dict(
            kind="gate_failure",
            evidence_refs=[
                _evidence_ref("candidate", ids["candidate_id"]),
                _evidence_ref("evaluation", ids["fold_id"]),
                _evidence_ref("gate", ids["verdict_id"]),
                _evidence_ref("artifact", ids["artifact_id"]),
            ],
        )
    ]
    recommendation = _recommendation_dict(disposition=disposition)
    if disposition == "propose_new_run":
        recommendation["follow_up_run_dims"] = ["universe", "window"]
    return json.dumps(_stage2_payload(caveats=caveats, recommendation=recommendation))


class TestStage2Service:
    async def test_stage2_service_clean_run_records_validated_and_checkpoint(
        self, tmp_path
    ) -> None:
        from app.research.agent_stage2 import Stage2Result
        from app.research.run_service import ResearchRunService

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        started = _make_started_run(repo)
        run_id = started["id"]
        ids = _seed_full_evidence(repo, run_id=run_id)
        raw = _evidence_citing_payload(ids)
        result = await _stage2_service().run(
            snapshot_ref={
                "snapshot_sha256": started["snapshot_sha256"],
                "manifest_sha256": started["manifest_sha256"],
            },
            seam=_seam(repo, _generate_returning(raw)),
            repo=repo, run_id=run_id, run_service=ResearchRunService(repo),
            principal="researcher@example.com",
            expected_version=started["transition_version"],
            attempt_token=started["_attempt_token"],
        )
        assert isinstance(result, Stage2Result)
        assert result.attempt_ordinal == 1
        # A validated attempt row exists for stage2.
        attempts = repo.list_analysis_attempts(run_id, stage="stage2")
        assert any(r["outcome"] == "validated" for r in attempts)
        # The stage2_completed event was appended.
        events = repo.list_run_events(run_id)
        assert any(e["event_type"] == "stage2_completed" for e in events)
        # A contiguous stage-boundary checkpoint was written.
        boundary_event = next(e for e in events if e["event_type"] == "stage2_completed")
        assert boundary_event["seq"] == started["last_event_seq"] + 1

    async def test_stage2_service_checkpoint_is_contiguous_and_recoverable(
        self, tmp_path
    ) -> None:
        from app.research.run_service import ResearchRunService

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        started = _make_started_run(repo)
        run_id = started["id"]
        ids = _seed_full_evidence(repo, run_id=run_id)
        raw = _evidence_citing_payload(ids)
        await _stage2_service().run(
            snapshot_ref={
                "snapshot_sha256": started["snapshot_sha256"],
                "manifest_sha256": started["manifest_sha256"],
            },
            seam=_seam(repo, _generate_returning(raw)),
            repo=repo, run_id=run_id, run_service=ResearchRunService(repo),
            principal="researcher@example.com",
            expected_version=started["transition_version"],
            attempt_token=started["_attempt_token"],
        )
        service = ResearchRunService(repo)
        checkpoint = service.get_latest_valid_checkpoint(
            run_id, principal="researcher@example.com"
        )
        assert checkpoint is not None
        assert checkpoint["stage"] == "stage2"
        assert checkpoint["committed_event_seq"] == started["last_event_seq"] + 1
        # The advisory recommendation is stored as bounded inline summary data.
        assert checkpoint["inline_summary"]["stage"] == "stage2"
        assert checkpoint["inline_summary"]["disposition"] == "inspect"

    async def test_stage2_service_provider_exception_zero_validated_no_checkpoint(
        self, tmp_path
    ) -> None:
        from app.research.agent_provider import ProviderCallError
        from app.research.run_service import ResearchRunService

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        started = _make_started_run(repo)
        run_id = started["id"]
        _seed_full_evidence(repo, run_id=run_id)
        with pytest.raises(ProviderCallError):
            await _stage2_service().run(
                snapshot_ref={
                    "snapshot_sha256": started["snapshot_sha256"],
                    "manifest_sha256": started["manifest_sha256"],
                },
                seam=_seam(repo, _generate_raising(TimeoutError("upstream blip"))),
                repo=repo, run_id=run_id, run_service=ResearchRunService(repo),
                principal="researcher@example.com",
                expected_version=started["transition_version"],
                attempt_token=started["_attempt_token"],
            )
        attempts = repo.list_analysis_attempts(run_id, stage="stage2")
        # ZERO validated rows; the transport failure is a failed/cancelled row.
        assert not any(r["outcome"] == "validated" for r in attempts)
        assert any(r["outcome"] in ("failed", "cancelled") for r in attempts)
        # No stage2_completed event and no checkpoint were written.
        events = repo.list_run_events(run_id)
        assert not any(e["event_type"] == "stage2_completed" for e in events)
        assert (
            ResearchRunService(repo).get_latest_valid_checkpoint(
                run_id, principal="researcher@example.com"
            )
            is None
            or ResearchRunService(repo)
            .get_latest_valid_checkpoint(run_id, principal="researcher@example.com")[
                "stage"
            ]
            != "stage2"
        )

    async def test_stage2_service_decode_failure_zero_validated(self, tmp_path) -> None:
        from app.research.agent_provider import ProviderCallError
        from app.research.run_service import ResearchRunService

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        started = _make_started_run(repo)
        run_id = started["id"]
        _seed_full_evidence(repo, run_id=run_id)
        with pytest.raises(ProviderCallError):
            await _stage2_service().run(
                snapshot_ref={
                    "snapshot_sha256": started["snapshot_sha256"],
                    "manifest_sha256": started["manifest_sha256"],
                },
                seam=_seam(repo, _generate_returning("not json at all")),
                repo=repo, run_id=run_id, run_service=ResearchRunService(repo),
                principal="researcher@example.com",
                expected_version=started["transition_version"],
                attempt_token=started["_attempt_token"],
            )
        attempts = repo.list_analysis_attempts(run_id, stage="stage2")
        assert not any(r["outcome"] == "validated" for r in attempts)
        assert any(
            r["outcome"] == "failed" and r["failure_class"] == "malformed_json"
            for r in attempts
        )

    async def test_stage2_service_referential_failure_zero_validated(
        self, tmp_path
    ) -> None:
        from app.research.agent_provider import ProviderCallError
        from app.research.run_service import ResearchRunService

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        started = _make_started_run(repo)
        run_id = started["id"]
        # Seed evidence, but the model cites a fabricated candidate id.
        _seed_full_evidence(repo, run_id=run_id)
        payload = json.dumps(
            _stage2_payload(
                caveats=[
                    _caveat_dict(
                        evidence_refs=[_evidence_ref("candidate", "acand_missing")]
                    )
                ]
            )
        )
        with pytest.raises(ProviderCallError):
            await _stage2_service().run(
                snapshot_ref={
                    "snapshot_sha256": started["snapshot_sha256"],
                    "manifest_sha256": started["manifest_sha256"],
                },
                seam=_seam(repo, _generate_returning(payload)),
                repo=repo, run_id=run_id, run_service=ResearchRunService(repo),
                principal="researcher@example.com",
                expected_version=started["transition_version"],
                attempt_token=started["_attempt_token"],
            )
        attempts = repo.list_analysis_attempts(run_id, stage="stage2")
        assert not any(r["outcome"] == "validated" for r in attempts)
        assert any(
            r["outcome"] == "failed" and r["failure_class"] == "schema_violation"
            for r in attempts
        )

    async def test_stage2_service_propose_new_run_does_not_spawn_run(
        self, tmp_path
    ) -> None:
        from app.research.run_service import ResearchRunService

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        started = _make_started_run(repo)
        run_id = started["id"]
        ids = _seed_full_evidence(repo, run_id=run_id)
        raw = _evidence_citing_payload(ids, disposition="propose_new_run")
        with repo._connection() as connection:
            before = connection.execute(
                "SELECT COUNT(*) FROM research_alpha_runs"
            ).fetchone()[0]
        result = await _stage2_service().run(
            snapshot_ref={
                "snapshot_sha256": started["snapshot_sha256"],
                "manifest_sha256": started["manifest_sha256"],
            },
            seam=_seam(repo, _generate_returning(raw)),
            repo=repo, run_id=run_id, run_service=ResearchRunService(repo),
            principal="researcher@example.com",
            expected_version=started["transition_version"],
            attempt_token=started["_attempt_token"],
        )
        assert result.recommendation.disposition == "propose_new_run"
        with repo._connection() as connection:
            after = connection.execute(
                "SELECT COUNT(*) FROM research_alpha_runs"
            ).fetchone()[0]
        # disposition='propose_new_run' is advisory -- no autonomous run spawned.
        assert before == after

    async def test_stage2_service_read_only_no_candidate_write(self, tmp_path) -> None:
        from app.research.run_service import ResearchRunService

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        started = _make_started_run(repo)
        run_id = started["id"]
        ids = _seed_full_evidence(repo, run_id=run_id)
        before_candidates = repo.list_candidates(run_id)
        before_folds = repo.list_alpha_fold_evidence(run_id=run_id)
        raw = _evidence_citing_payload(ids)
        await _stage2_service().run(
            snapshot_ref={
                "snapshot_sha256": started["snapshot_sha256"],
                "manifest_sha256": started["manifest_sha256"],
            },
            seam=_seam(repo, _generate_returning(raw)),
            repo=repo, run_id=run_id, run_service=ResearchRunService(repo),
            principal="researcher@example.com",
            expected_version=started["transition_version"],
            attempt_token=started["_attempt_token"],
        )
        # Stage 2 is read-only over Phase 47 evidence: no new candidate/OOS rows.
        assert repo.list_candidates(run_id) == before_candidates
        assert repo.list_alpha_fold_evidence(run_id=run_id) == before_folds


class TestStageBoundaryCheckpoint:
    async def test_boundary_event_and_checkpoint_written_atomically(self, tmp_path) -> None:
        from app.research.run_contract import attempt_token_digest, checkpoint_state_checksum
        from app.research.run_service import ResearchRunService

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        started = _make_started_run(repo)
        run_id = started["id"]
        service = ResearchRunService(repo)
        committed_event_seq = started["last_event_seq"] + 1
        checkpoint_version = repo.next_checkpoint_version(run_id)
        state_checksum = checkpoint_state_checksum(
            run_id=run_id, checkpoint_version=checkpoint_version,
            committed_event_seq=committed_event_seq, stage="stage2",
            snapshot_sha256=started["snapshot_sha256"],
            manifest_sha256=started["manifest_sha256"],
            referenced_candidate_ids=(), inline_summary=None, frontier_artifact_id=None,
        )
        checkpoint = service.append_stage_boundary(
            repo, run_id=run_id, after_stage="stage2",
            event_id="aevt_b1", event_type="stage2_completed",
            idempotency_key="stage2-boundary-1", actor="service", source="test",
            payload={"stage": "stage2"},
            committed_event_seq=committed_event_seq, checkpoint_stage="stage2",
            snapshot_sha256=started["snapshot_sha256"],
            manifest_sha256=started["manifest_sha256"],
            state_checksum=state_checksum, principal="researcher@example.com",
            expected_version=started["transition_version"],
            expected_attempt_token_digest=attempt_token_digest(started["_attempt_token"]),
        )
        assert checkpoint["stage"] == "stage2"
        assert checkpoint["committed_event_seq"] == committed_event_seq
        events = repo.list_run_events(run_id)
        assert any(e["event_type"] == "stage2_completed" for e in events)
        assert next(e for e in events if e["event_type"] == "stage2_completed")["seq"] == committed_event_seq

    def test_boundary_non_contiguous_committed_event_seq_rejected(self, tmp_path) -> None:
        from app.research.run_contract import attempt_token_digest, checkpoint_state_checksum
        from app.research.run_service import ResearchRunService

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        started = _make_started_run(repo)
        run_id = started["id"]
        service = ResearchRunService(repo)
        # Predict the WRONG seq (off by one) -- the contiguity fence rejects it.
        wrong_seq = started["last_event_seq"] + 2
        checkpoint_version = repo.next_checkpoint_version(run_id)
        state_checksum = checkpoint_state_checksum(
            run_id=run_id, checkpoint_version=checkpoint_version,
            committed_event_seq=wrong_seq, stage="stage2",
            snapshot_sha256=started["snapshot_sha256"],
            manifest_sha256=started["manifest_sha256"],
            referenced_candidate_ids=(), inline_summary=None, frontier_artifact_id=None,
        )
        with pytest.raises(ValueError, match="contiguous"):
            service.append_stage_boundary(
                repo, run_id=run_id, after_stage="stage2",
                event_id="aevt_bad", event_type="stage2_completed",
                idempotency_key="stage2-boundary-bad", actor="service", source="test",
                payload={"stage": "stage2"},
                committed_event_seq=wrong_seq, checkpoint_stage="stage2",
                snapshot_sha256=started["snapshot_sha256"],
                manifest_sha256=started["manifest_sha256"],
                state_checksum=state_checksum, principal="researcher@example.com",
                expected_version=started["transition_version"],
                expected_attempt_token_digest=attempt_token_digest(started["_attempt_token"]),
            )
        # Nothing partial committed: no stage2_completed event, no checkpoint.
        events = repo.list_run_events(run_id)
        assert not any(e["event_type"] == "stage2_completed" for e in events)

    def test_boundary_stale_attempt_token_rejected(self, tmp_path) -> None:
        from app.research.run_contract import checkpoint_state_checksum
        from app.research.run_service import ResearchRunService

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        started = _make_started_run(repo)
        run_id = started["id"]
        service = ResearchRunService(repo)
        committed_event_seq = started["last_event_seq"] + 1
        checkpoint_version = repo.next_checkpoint_version(run_id)
        state_checksum = checkpoint_state_checksum(
            run_id=run_id, checkpoint_version=checkpoint_version,
            committed_event_seq=committed_event_seq, stage="stage2",
            snapshot_sha256=started["snapshot_sha256"],
            manifest_sha256=started["manifest_sha256"],
            referenced_candidate_ids=(), inline_summary=None, frontier_artifact_id=None,
        )
        with pytest.raises(ValueError, match="token"):
            service.append_stage_boundary(
                repo, run_id=run_id, after_stage="stage2",
                event_id="aevt_stale", event_type="stage2_completed",
                idempotency_key="stage2-boundary-stale", actor="service", source="test",
                payload={"stage": "stage2"},
                committed_event_seq=committed_event_seq, checkpoint_stage="stage2",
                snapshot_sha256=started["snapshot_sha256"],
                manifest_sha256=started["manifest_sha256"],
                state_checksum=state_checksum, principal="researcher@example.com",
                expected_version=started["transition_version"],
                expected_attempt_token_digest="0" * 64,
            )

    def test_boundary_stage1_maps_to_stage2_pending_checkpoint(self, tmp_path) -> None:
        from app.research.run_contract import attempt_token_digest, checkpoint_state_checksum
        from app.research.run_service import ResearchRunService

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        started = _make_started_run(repo)
        run_id = started["id"]
        service = ResearchRunService(repo)
        committed_event_seq = started["last_event_seq"] + 1
        checkpoint_version = repo.next_checkpoint_version(run_id)
        state_checksum = checkpoint_state_checksum(
            run_id=run_id, checkpoint_version=checkpoint_version,
            committed_event_seq=committed_event_seq, stage="stage2_pending",
            snapshot_sha256=started["snapshot_sha256"],
            manifest_sha256=started["manifest_sha256"],
            referenced_candidate_ids=(), inline_summary=None, frontier_artifact_id=None,
        )
        checkpoint = service.append_stage_boundary(
            repo, run_id=run_id, after_stage="stage1",
            event_id="aevt_s1", event_type="stage1_completed",
            idempotency_key="stage1-boundary-1", actor="service", source="test",
            payload={"stage": "stage1"},
            committed_event_seq=committed_event_seq, checkpoint_stage="stage2_pending",
            snapshot_sha256=started["snapshot_sha256"],
            manifest_sha256=started["manifest_sha256"],
            state_checksum=state_checksum, principal="researcher@example.com",
            expected_version=started["transition_version"],
            expected_attempt_token_digest=attempt_token_digest(started["_attempt_token"]),
        )
        assert checkpoint["stage"] == "stage2_pending"
        events = repo.list_run_events(run_id)
        assert any(e["event_type"] == "stage1_completed" for e in events)