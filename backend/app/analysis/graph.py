"""The fixed two-node, tool-free LangGraph analysis workflow."""
from __future__ import annotations

from pathlib import Path
from typing import Any, NotRequired, TypedDict

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from app.analysis.model_adapter import ConfiguredAnalysisAdapter, GenerateText
from app.analysis.schemas import FrozenEvidenceSnapshot, GeneratedAnalysis


class AnalysisGraphState(TypedDict):
    """Only frozen evidence enters the graph; only a validated body leaves it."""

    frozen_evidence: FrozenEvidenceSnapshot | dict[str, object]
    generated_body: NotRequired[GeneratedAnalysis]


class PersistentAnalysisGraph:
    """Graph facade that opens the approved SQLite saver for each async invocation."""

    def __init__(self, *, builder: StateGraph, checkpoint_path: Path) -> None:
        self._builder = builder
        self._checkpoint_path = checkpoint_path
        # Topology inspection is deliberately saver-free; execution always uses SQLite.
        self._topology_graph = builder.compile()

    def get_graph(self):
        return self._topology_graph.get_graph()

    async def ainvoke(self, state: AnalysisGraphState, config: dict[str, Any] | None = None):
        thread_id = (config or {}).get("configurable", {}).get("thread_id")
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise ValueError("analysis graph requires a server-generated thread_id")
        self._checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(str(self._checkpoint_path)) as saver:
            await saver.setup()
            graph = self._builder.compile(checkpointer=saver)
            return await graph.ainvoke(state, config)


def build_analysis_graph(
    *,
    checkpoint_path: Path,
    adapter: ConfiguredAnalysisAdapter | None = None,
    generate_text: GenerateText | None = None,
):
    """Compile the one approved DAG; no conditional, tool, or loop edges exist."""
    if adapter is not None and generate_text is not None:
        raise ValueError("analysis graph accepts an adapter or generate_text, not both")
    model_adapter = adapter or ConfiguredAnalysisAdapter(generate_text=generate_text)

    async def validate_frozen_input(state: AnalysisGraphState) -> dict[str, FrozenEvidenceSnapshot]:
        snapshot = FrozenEvidenceSnapshot.model_validate(state["frozen_evidence"])
        if snapshot.context_status != "ready":
            raise ValueError("analysis generation requires ready frozen evidence")
        return {"frozen_evidence": snapshot}

    async def generate_validated_body(state: AnalysisGraphState) -> dict[str, GeneratedAnalysis]:
        snapshot = FrozenEvidenceSnapshot.model_validate(state["frozen_evidence"])
        return {"generated_body": await model_adapter.ainvoke(snapshot)}

    builder = StateGraph(AnalysisGraphState)
    builder.add_node("validate_frozen_input", validate_frozen_input)
    builder.add_node("generate_validated_body", generate_validated_body)
    builder.add_edge(START, "validate_frozen_input")
    builder.add_edge("validate_frozen_input", "generate_validated_body")
    builder.add_edge("generate_validated_body", END)
    return PersistentAnalysisGraph(builder=builder, checkpoint_path=Path(checkpoint_path))
