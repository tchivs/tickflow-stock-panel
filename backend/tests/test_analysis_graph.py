"""Wave 0 contracts for the bounded two-node analysis LangGraph."""
from __future__ import annotations

from datetime import date, datetime

import pytest


def _snapshot():
    from app.analysis.evidence import EvidencePreparationService

    return EvidencePreparationService().freeze(
        subject_key="600519.SH",
        records=[
            {
                "source_id": "known",
                "origin": "exchange-filing",
                "independence_group": "exchange",
                "value": 100.0,
                "unit": "CNY_million",
                "period": "2025-Q4",
                "definition": "revenue",
                "retrieved_at": datetime(2026, 7, 12),
                "as_of": date(2026, 7, 11),
            }
        ],
    )


async def test_analysis_graph_has_only_the_named_fixed_two_node_topology(tmp_path):
    from app.analysis.graph import build_analysis_graph

    graph = build_analysis_graph(checkpoint_path=tmp_path / "analysis_checkpoints.db")
    topology = graph.get_graph()
    node_names = set(topology.nodes)
    edges = {(edge.source, edge.target) for edge in topology.edges}

    assert {"validate_frozen_input", "generate_validated_body"} <= node_names
    assert edges == {
        ("__start__", "validate_frozen_input"),
        ("validate_frozen_input", "generate_validated_body"),
        ("generate_validated_body", "__end__"),
    }
    assert not any("tool" in node.lower() or "agent" in node.lower() for node in node_names)


async def test_analysis_graph_requires_a_server_generated_thread_id(tmp_path):
    from app.analysis.graph import build_analysis_graph

    graph = build_analysis_graph(checkpoint_path=tmp_path / "analysis_checkpoints.db")

    with pytest.raises(ValueError, match="thread_id"):
        await graph.ainvoke({"frozen_evidence": _snapshot()}, {"configurable": {}})


async def test_analysis_graph_rejects_unvalidated_generated_body_before_it_can_be_reported(tmp_path):
    from app.analysis.graph import build_analysis_graph

    async def malformed_adapter(_messages, **_kwargs):
        return '{"citations":["unknown"],"unexpected":true}'

    graph = build_analysis_graph(
        checkpoint_path=tmp_path / "analysis_checkpoints.db", generate_text=malformed_adapter
    )

    with pytest.raises(ValueError, match="generated analysis"):
        await graph.ainvoke(
            {"frozen_evidence": _snapshot()},
            {"configurable": {"thread_id": "server-run-1"}},
        )


async def test_analysis_adapter_uses_fixed_server_messages_and_validates_json():
    from app.analysis.model_adapter import ConfiguredAnalysisAdapter

    observed = []

    async def offline_transport(messages, **kwargs):
        observed.append((messages, kwargs))
        return (
            '{"perspectives":[{"name":"fundamental","stance":"supports","score":70,'
            '"rationale":"governed evidence","evidence_ids":["known"]},'
            '{"name":"risk","stance":"neutral","score":50,"rationale":"watch",'
            '"evidence_ids":["known"]}],"valuation":{"applicable":false,'
            '"method":"not_applicable","conclusion":"insufficient"},"ic_memo":'
            '{"recommendation":"research_only_watch","thesis":"wait","risks":["risk"],'
            '"invalidation_conditions":["conflict"],"evidence_ids":["known"]}}'
        )

    body = await ConfiguredAnalysisAdapter(
        provider="offline", model="offline-contract", generate_text=offline_transport
    ).ainvoke(_snapshot())

    assert body.ic_memo.recommendation == "research_only_watch"
    assert observed[0][1] == {"temperature": 0, "max_tokens": 2000, "timeout": 30.0}
    assert observed[0][0][0]["role"] == "system"
    assert "tools" in observed[0][0][0]["content"].lower()
