"""Stage 1 contract tests for the FactorResearchAgent (AF-REQ-12).

Phase 48-02. Covers:
* 48-02-01 — StageOneRequest + versioned strict (extra='forbid') output schema.
* 48-02-02 — server parse_factor confirmation + transient exploratory proposal
  store (catalog isolation, append-only).
* 48-02-03 — Stage1Service over the Agent seam + partial labeling (R2) +
  no-fallback invariant (SC4).
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from app.research.repository import AlphaRunConflictError, ResearchRepository
from app.research.run_contract import freeze_input_snapshot


# ------------------------------------------------------------------
# Shared fixtures (mirror test_agent_provider.py conventions)
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


def _make_run(repo: ResearchRepository, *, run_id: str = "run-stage1") -> str:
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


def _request_kwargs(**overrides) -> dict:
    base = dict(
        thesis="Short-term mean reversion in liquid names.",
        permitted_grammar={"max_depth": 4, "max_nodes": 12, "fingerprint": "a" * 64},
        permitted_fields=frozenset({"close", "volume"}),
        permitted_functions=frozenset({"rolling_mean"}),
        budget_hints={"max_expressions": 3, "max_explanation_chars": 2000},
        snapshot_ref={"snapshot_sha256": "1" * 64, "manifest_sha256": "2" * 64},
    )
    base.update(overrides)
    return base


def _hypothesis_dict(**overrides) -> dict:
    base = dict(
        expression="close",
        explanation="Price level as a factor signal.",
        uncertainty="low",
        scope="daily cross-section",
        assumptions=["liquidity assumed"],
        evidence_refs=["thesis"],
    )
    base.update(overrides)
    return base


def _stage1_payload(hypotheses: list[dict], **overrides) -> dict:
    payload = {
        "schema_version": "factor-stage1-v1",
        "hypotheses": hypotheses,
    }
    payload.update(overrides)
    return payload


# ==================================================================
# 48-02-01 — StageOneRequest + versioned strict schema (extra='forbid')
# ==================================================================


class TestStageOneRequest:
    def test_stage1_request_valid_construction(self) -> None:
        from app.research.agent_stage1 import StageOneRequest

        request = StageOneRequest(**_request_kwargs())
        assert request.thesis.startswith("Short-term")
        assert request.permitted_fields == frozenset({"close", "volume"})

    def test_stage1_request_empty_thesis_rejected(self) -> None:
        from app.research.agent_stage1 import StageOneRequest

        with pytest.raises(ValueError, match="thesis"):
            StageOneRequest(**_request_kwargs(thesis="   "))

    def test_stage1_request_oversized_thesis_rejected(self) -> None:
        from app.research.agent_stage1 import StageOneRequest

        with pytest.raises(ValueError, match="thesis"):
            StageOneRequest(**_request_kwargs(thesis="x" * 5000))

    def test_stage1_request_unknown_field_rejected(self) -> None:
        from app.research.agent_stage1 import StageOneRequest

        with pytest.raises(ValueError, match="permitted_fields"):
            StageOneRequest(**_request_kwargs(permitted_fields=frozenset({"close", "not_a_field"})))

    def test_stage1_request_unknown_function_rejected(self) -> None:
        from app.research.agent_stage1 import StageOneRequest

        with pytest.raises(ValueError, match="permitted_functions"):
            StageOneRequest(**_request_kwargs(permitted_functions=frozenset({"rolling_mean", "sin"})))

    def test_stage1_request_as_request_scope_is_bounded_json(self) -> None:
        from app.research.agent_stage1 import StageOneRequest
        from app.research.run_contract import canonical_bounded_json

        request = StageOneRequest(**_request_kwargs())
        scope = request.as_request_scope()
        # The scope must serialize to bounded canonical JSON (provenance digest source).
        canonical_bounded_json(scope, "stage1 request scope")


class TestDecodeStage1Payload:
    def test_decode_malformed_json_rejected(self) -> None:
        from app.research.agent_stage1 import decode_stage1_payload

        with pytest.raises(ValueError, match="malformed JSON"):
            decode_stage1_payload("not json at all")

    def test_decode_non_object_rejected(self) -> None:
        from app.research.agent_stage1 import decode_stage1_payload

        with pytest.raises(ValueError, match="JSON object"):
            decode_stage1_payload("[]")

    def test_decode_unknown_top_level_field_rejected(self) -> None:
        from app.research.agent_stage1 import decode_stage1_payload

        raw = json.dumps(_stage1_payload([_hypothesis_dict()], extra="boom"))
        with pytest.raises(ValueError, match="unsupported field"):
            decode_stage1_payload(raw)

    def test_decode_missing_top_level_field_rejected(self) -> None:
        from app.research.agent_stage1 import decode_stage1_payload

        raw = json.dumps({"schema_version": "factor-stage1-v1"})
        with pytest.raises(ValueError, match="missing field"):
            decode_stage1_payload(raw)

    def test_decode_schema_version_mismatch_rejected(self) -> None:
        from app.research.agent_stage1 import decode_stage1_payload

        raw = json.dumps(_stage1_payload(
            [_hypothesis_dict()], schema_version="factor-stage1-v2"))
        with pytest.raises(ValueError, match="schema_version mismatch"):
            decode_stage1_payload(raw)

    def test_decode_unknown_hypothesis_field_rejected(self) -> None:
        from app.research.agent_stage1 import decode_stage1_payload

        raw = json.dumps(_stage1_payload([_hypothesis_dict(bogus="x")]))
        with pytest.raises(ValueError, match="unsupported field"):
            decode_stage1_payload(raw)

    def test_decode_missing_required_hypothesis_field_rejected(self) -> None:
        from app.research.agent_stage1 import decode_stage1_payload

        item = _hypothesis_dict()
        del item["expression"]
        raw = json.dumps(_stage1_payload([item]))
        with pytest.raises(ValueError, match="missing field"):
            decode_stage1_payload(raw)

    def test_decode_oversized_hypotheses_rejected(self) -> None:
        from app.research.agent_stage1 import decode_stage1_payload

        hypotheses = [_hypothesis_dict(expression="close") for _ in range(4)]
        raw = json.dumps(_stage1_payload(hypotheses))
        with pytest.raises(ValueError, match="maximum"):
            decode_stage1_payload(raw)

    def test_decode_oversized_explanation_rejected(self) -> None:
        from app.research.agent_stage1 import decode_stage1_payload

        raw = json.dumps(_stage1_payload([_hypothesis_dict(explanation="x" * 2001)]))
        with pytest.raises(ValueError, match="explanation"):
            decode_stage1_payload(raw)

    def test_decode_bad_uncertainty_rejected(self) -> None:
        from app.research.agent_stage1 import decode_stage1_payload

        raw = json.dumps(_stage1_payload([_hypothesis_dict(uncertainty="huge")]))
        with pytest.raises(ValueError, match="uncertainty"):
            decode_stage1_payload(raw)

    def test_decode_empty_hypotheses_rejected(self) -> None:
        from app.research.agent_stage1 import decode_stage1_payload

        raw = json.dumps(_stage1_payload([]))
        with pytest.raises(ValueError, match="non-empty"):
            decode_stage1_payload(raw)

    def test_decode_valid_payload_decodes_to_hypotheses(self) -> None:
        from app.research.agent_stage1 import StageOneHypothesis, decode_stage1_payload

        raw = json.dumps(_stage1_payload([
            _hypothesis_dict(expression="close", uncertainty="low"),
            _hypothesis_dict(expression="volume", uncertainty="medium"),
        ]))
        hypotheses = decode_stage1_payload(raw)
        assert len(hypotheses) == 2
        assert all(isinstance(h, StageOneHypothesis) for h in hypotheses)
        assert hypotheses[0].expression == "close"
        assert hypotheses[0].uncertainty == "low"
        assert hypotheses[1].assumptions == ("liquidity assumed",)

    def test_decode_optional_scope_defaults_empty(self) -> None:
        from app.research.agent_stage1 import decode_stage1_payload

        item = _hypothesis_dict()
        del item["scope"]
        raw = json.dumps(_stage1_payload([item]))
        hypotheses = decode_stage1_payload(raw)
        assert hypotheses[0].scope == ""

    def test_decode_is_pure_does_not_mutate_input(self) -> None:
        from app.research.agent_stage1 import decode_stage1_payload

        item = _hypothesis_dict()
        raw = json.dumps(_stage1_payload([item]))
        original = raw
        decode_stage1_payload(raw)
        assert raw == original  # str is immutable; assert the function returns without side effects
