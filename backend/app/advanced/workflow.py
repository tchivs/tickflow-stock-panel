"""Fixed, replay-safe LangGraph orchestration for advanced research jobs.

The graph is a recovery cursor only.  Authorization, frozen inputs, gates, and
authoritative outcome writes remain in injected application services.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NotRequired, Protocol, TypedDict

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class AdvancedWorkflowState(TypedDict):
    """Compact server-derived state persisted by the checkpoint cursor."""

    job_id: str
    authorization_id: str
    subject_ref: str
    frozen_evidence_refs: NotRequired[list[str]]
    draft: NotRequired[dict[str, object]]
    gate_status: NotRequired[Literal["passed", "rejected"]]
    human_decision: NotRequired[Literal["approved", "rejected"]]


class AuthorizationAdapter(Protocol):
    def authorize_and_freeze(self, **kwargs: object) -> Awaitable[dict[str, object]]: ...


class DraftProvider(Protocol):
    def generate_draft(self, **kwargs: object) -> Awaitable[dict[str, object]]: ...


class GateAdapter(Protocol):
    def evaluate(self, **kwargs: object) -> Awaitable[dict[str, bool]]: ...


class OutcomeAdapter(Protocol):
    def record_once(self, **kwargs: object) -> Awaitable[dict[str, object]]: ...


@dataclass(frozen=True)
class AdvancedWorkflowServices:
    """Narrow adapters; none can grant graph-level authority."""

    authorization: AuthorizationAdapter
    draft_provider: DraftProvider | None
    gates: GateAdapter
    outcomes: OutcomeAdapter
    thread_owner: Callable[[str], str]


class PersistentAdvancedGraph:
    """Open a SQLite saver for each invocation and enforce server thread binding."""

    def __init__(self, *, builder: StateGraph, checkpoint_path: Path, services: AdvancedWorkflowServices) -> None:
        self._builder = builder
        self._checkpoint_path = checkpoint_path
        self._services = services
        self._topology_graph = builder.compile()
        self._thread_jobs: dict[str, str] = {}

    def get_graph(self):
        return self._topology_graph.get_graph()

    async def ainvoke(
        self,
        state: AdvancedWorkflowState | Command,
        config: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        thread_id = (config or {}).get("configurable", {}).get("thread_id")
        if not isinstance(thread_id, str) or not thread_id:
            raise ValueError("advanced graph requires a server-generated thread_id")

        if isinstance(state, Command):
            if thread_id not in self._thread_jobs:
                raise ValueError("advanced graph requires a server-owned thread binding")
        else:
            job_id = state.get("job_id")
            if not isinstance(job_id, str) or not job_id:
                raise ValueError("advanced graph requires a server-owned job ID")
            if thread_id != self._services.thread_owner(job_id):
                raise ValueError("advanced graph server thread ownership does not match job")
            self._thread_jobs[thread_id] = job_id

        self._checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(str(self._checkpoint_path)) as saver:
            await saver.setup()
            graph = self._builder.compile(checkpointer=saver)
            return await graph.ainvoke(state, config)


def _safe_draft(raw_draft: dict[str, object], frozen_refs: set[str]) -> dict[str, object]:
    """Project untrusted provider output to bounded data before deterministic gates."""
    evidence_refs = raw_draft.get("evidence_refs")
    if not isinstance(evidence_refs, list) or not all(isinstance(ref, str) for ref in evidence_refs):
        raise ValueError("draft evidence references are invalid")
    if not set(evidence_refs).issubset(frozen_refs):
        raise ValueError("draft references are not frozen server evidence")
    rationale = raw_draft.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 2_000:
        raise ValueError("draft rationale is invalid")
    confidence = raw_draft.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
        raise ValueError("draft confidence is invalid")
    assumptions = raw_draft.get("assumptions", [])
    if not isinstance(assumptions, list) or len(assumptions) > 10 or not all(isinstance(item, str) for item in assumptions):
        raise ValueError("draft assumptions are invalid")
    kind = raw_draft.get("kind")
    if kind not in {"viewpoint_draft", "experiment_draft", "strategy_mutation_draft"}:
        raise ValueError("draft kind is invalid")
    return {
        "kind": kind,
        "rationale": rationale.strip(),
        "evidence_refs": evidence_refs,
        "assumptions": assumptions,
        "confidence": float(confidence),
    }


def build_advanced_graph(*, checkpoint_path: Path, services: AdvancedWorkflowServices) -> PersistentAdvancedGraph:
    """Build the sole approved advanced workflow topology."""

    async def authorize_and_freeze(state: AdvancedWorkflowState) -> dict[str, object]:
        prepared = await services.authorization.authorize_and_freeze(
            job_id=state["job_id"],
            authorization_id=state["authorization_id"],
            subject_ref=state["subject_ref"],
        )
        frozen_refs = prepared.get("frozen_evidence_refs")
        subject_ref = prepared.get("subject_ref")
        authorization_id = prepared.get("authorization_id")
        if not isinstance(frozen_refs, list) or not frozen_refs or not all(isinstance(ref, str) for ref in frozen_refs):
            raise ValueError("authorization did not provide frozen evidence")
        if not isinstance(subject_ref, str) or not isinstance(authorization_id, str):
            raise ValueError("authorization did not provide a valid frozen binding")
        return {
            "authorization_id": authorization_id,
            "subject_ref": subject_ref,
            "frozen_evidence_refs": frozen_refs,
        }

    async def optional_draft(state: AdvancedWorkflowState) -> dict[str, object]:
        if services.draft_provider is None:
            return {"draft": {"kind": "strategy_mutation_draft", "rationale": "no provider configured", "evidence_refs": state["frozen_evidence_refs"], "assumptions": [], "confidence": 0.0}}
        draft = await services.draft_provider.generate_draft(
            job_id=state["job_id"], subject_ref=state["subject_ref"], evidence_refs=state["frozen_evidence_refs"]
        )
        return {"draft": _safe_draft(draft, set(state["frozen_evidence_refs"]))}

    async def deterministic_gates(state: AdvancedWorkflowState) -> dict[str, Literal["passed", "rejected"]]:
        result = await services.gates.evaluate(job_id=state["job_id"], draft=state["draft"])
        return {"gate_status": "passed" if result.get("passed") is True else "rejected"}

    def route_after_gates(state: AdvancedWorkflowState) -> Literal["human_interrupt", "record_rejection"]:
        return "human_interrupt" if state["gate_status"] == "passed" else "record_rejection"

    def human_interrupt(_state: AdvancedWorkflowState) -> dict[str, Literal["approved", "rejected"]]:
        decision = interrupt({"kind": "advanced_review"})
        return {"human_decision": "approved" if decision == "approve" else "rejected"}

    async def record_rejection(state: AdvancedWorkflowState) -> dict[str, object]:
        await services.outcomes.record_once(job_id=state["job_id"], outcome_type="rejected")
        return {}

    async def record_outcome(state: AdvancedWorkflowState) -> dict[str, object]:
        await services.outcomes.record_once(job_id=state["job_id"], outcome_type=state["human_decision"])
        return {}

    builder = StateGraph(AdvancedWorkflowState)
    builder.add_node("authorize_and_freeze", authorize_and_freeze)
    builder.add_node("optional_draft", optional_draft)
    builder.add_node("deterministic_gates", deterministic_gates)
    builder.add_node("human_interrupt", human_interrupt)
    builder.add_node("record_rejection", record_rejection)
    builder.add_node("record_outcome", record_outcome)
    builder.add_edge(START, "authorize_and_freeze")
    builder.add_edge("authorize_and_freeze", "optional_draft")
    builder.add_edge("optional_draft", "deterministic_gates")
    builder.add_conditional_edges("deterministic_gates", route_after_gates)
    builder.add_edge("human_interrupt", "record_outcome")
    builder.add_edge("record_rejection", END)
    builder.add_edge("record_outcome", END)
    return PersistentAdvancedGraph(builder=builder, checkpoint_path=Path(checkpoint_path), services=services)
