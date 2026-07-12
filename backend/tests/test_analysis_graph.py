"""Wave 0 contracts for the bounded two-node analysis LangGraph."""
from __future__ import annotations

import pytest


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
        await graph.ainvoke({"frozen_evidence": {}}, {"configurable": {}})


async def test_analysis_graph_rejects_unvalidated_generated_body_before_it_can_be_reported(tmp_path):
    from app.analysis.graph import build_analysis_graph

    async def malformed_adapter(_messages):
        return '{"citations":["unknown"],"unexpected":true}'

    graph = build_analysis_graph(
        checkpoint_path=tmp_path / "analysis_checkpoints.db", generate_text=malformed_adapter
    )

    with pytest.raises(ValueError, match="generated analysis"):
        await graph.ainvoke(
            {"frozen_evidence": {"source_ids": ["known"]}},
            {"configurable": {"thread_id": "server-run-1"}},
        )
