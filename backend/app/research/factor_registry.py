"""Immutable factor-definition registry with deterministic similarity discovery."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
import uuid

from app.research.factor_dsl import FactorFeatures, ParsedFactor, parse_factor
from app.research.repository import ResearchRepository


@dataclass(frozen=True, slots=True)
class FactorRevision:
    id: str
    factor_id: str
    revision_number: int
    name: str
    description: str
    hypothesis: str
    canonical_expression: str
    dsl_version: str
    ast_signature: str
    shape_signature: str
    fields: tuple[str, ...]
    operators: tuple[str, ...]
    functions: tuple[str, ...]
    provenance: Mapping[str, Any]
    created_at: str

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "FactorRevision":
        return cls(
            id=str(record["id"]),
            factor_id=str(record["factor_id"]),
            revision_number=int(record["revision_number"]),
            name=str(record["name"]),
            description=str(record["description"]),
            hypothesis=str(record["hypothesis"]),
            canonical_expression=str(record["canonical_expression"]),
            dsl_version=str(record["dsl_version"]),
            ast_signature=str(record["ast_signature"]),
            shape_signature=str(record["shape_signature"]),
            fields=tuple(record["fields"]),
            operators=tuple(record["operators"]),
            functions=tuple(record["functions"]),
            provenance=dict(record["provenance"]),
            created_at=str(record["created_at"]),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "factor_id": self.factor_id,
            "revision_number": self.revision_number,
            "name": self.name,
            "description": self.description,
            "hypothesis": self.hypothesis,
            "canonical_expression": self.canonical_expression,
            "dsl_version": self.dsl_version,
            "ast_signature": self.ast_signature,
            "shape_signature": self.shape_signature,
            "fields": list(self.fields),
            "operators": list(self.operators),
            "functions": list(self.functions),
            "provenance": dict(self.provenance),
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class SimilarityCandidate:
    revision: FactorRevision
    score: float
    exact_structural_match: bool
    shape_match: float
    field_overlap: float
    operator_function_overlap: float
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "revision": self.revision.as_dict(),
            "score": self.score,
            "components": {
                "exact_structural_match": self.exact_structural_match,
                "shape_match": self.shape_match,
                "field_overlap": self.field_overlap,
                "operator_function_overlap": self.operator_function_overlap,
            },
            "reason": self.reason,
        }


def _required_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not (value := value.strip()):
        raise ValueError(f"{field} is required")
    return value


def _optional_text(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    return value.strip()


def _provenance(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("provenance must be a mapping")
    return dict(value)


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    union = left | right
    return 1.0 if not union else len(left & right) / len(union)


class FactorRegistry:
    """Validates first, then appends immutable factor revisions to SQLite."""

    def __init__(self, repository: ResearchRepository) -> None:
        self.repository = repository

    def create_factor(
        self,
        *,
        name: str,
        expression: str,
        description: str = "",
        hypothesis: str = "",
        provenance: Mapping[str, Any] | None = None,
    ) -> FactorRevision:
        parsed = parse_factor(expression)
        return self._create_from_parsed(
            name=_required_text(name, "name"),
            parsed=parsed,
            description=_optional_text(description, "description"),
            hypothesis=_optional_text(hypothesis, "hypothesis"),
            provenance=_provenance(provenance),
        )

    def _create_from_parsed(
        self,
        *,
        name: str,
        parsed: ParsedFactor,
        description: str,
        hypothesis: str,
        provenance: Mapping[str, Any],
    ) -> FactorRevision:
        record = self.repository.create_factor_with_revision(
            factor_id=uuid.uuid4().hex,
            revision_id=uuid.uuid4().hex,
            name=name,
            description=description,
            hypothesis=hypothesis,
            canonical_expression=parsed.canonical_expression,
            dsl_version=parsed.dsl_version,
            ast_signature=parsed.features.structural_signature,
            shape_signature=parsed.features.shape_signature,
            fields=parsed.features.fields,
            operators=parsed.features.operators,
            functions=parsed.features.functions,
            provenance=provenance,
        )
        return FactorRevision.from_record(record)

    def revise_factor(
        self,
        factor_id: str,
        *,
        expression: str,
        name: str | None = None,
        description: str | None = None,
        hypothesis: str | None = None,
        provenance: Mapping[str, Any] | None = None,
    ) -> FactorRevision:
        if not isinstance(factor_id, str) or not factor_id:
            raise ValueError("factor_id is required")
        # Parsing is intentionally complete before any database transaction begins.
        parsed = parse_factor(expression)
        prior = self.repository.get_current_revision(factor_id)
        if prior is None:
            raise ValueError("factor definition does not exist")
        record = self.repository.append_factor_revision(
            factor_id=factor_id,
            revision_id=uuid.uuid4().hex,
            name=_required_text(name if name is not None else str(prior["name"]), "name"),
            description=_optional_text(description if description is not None else str(prior["description"]), "description"),
            hypothesis=_optional_text(hypothesis if hypothesis is not None else str(prior["hypothesis"]), "hypothesis"),
            canonical_expression=parsed.canonical_expression,
            dsl_version=parsed.dsl_version,
            ast_signature=parsed.features.structural_signature,
            shape_signature=parsed.features.shape_signature,
            fields=parsed.features.fields,
            operators=parsed.features.operators,
            functions=parsed.features.functions,
            provenance=_provenance(provenance if provenance is not None else prior["provenance"]),
        )
        return FactorRevision.from_record(record)

    def save_factor(
        self,
        *,
        name: str,
        expression: str,
        factor_id: str | None = None,
        description: str | None = None,
        hypothesis: str | None = None,
        provenance: Mapping[str, Any] | None = None,
    ) -> FactorRevision:
        """Create a factor or append a revision; similarity never changes this path."""
        if factor_id is None:
            return self.create_factor(
                name=name,
                expression=expression,
                description="" if description is None else description,
                hypothesis="" if hypothesis is None else hypothesis,
                provenance=provenance,
            )
        return self.revise_factor(
            factor_id,
            expression=expression,
            name=name,
            description=description,
            hypothesis=hypothesis,
            provenance=provenance,
        )

    def get_revision(self, revision_id: str) -> FactorRevision | None:
        record = self.repository.get_revision(revision_id)
        return None if record is None else FactorRevision.from_record(record)

    def get_current(self, factor_id: str) -> FactorRevision | None:
        record = self.repository.get_current_revision(factor_id)
        return None if record is None else FactorRevision.from_record(record)

    def list_history(self, factor_id: str) -> list[FactorRevision]:
        return [FactorRevision.from_record(record) for record in self.repository.list_revisions(factor_id)]

    def list_current(self) -> list[FactorRevision]:
        return [FactorRevision.from_record(record) for record in self.repository.list_current_revisions()]

    def discover_similar(
        self,
        expression: str | ParsedFactor,
        *,
        limit: int = 20,
        exclude_revision_id: str | None = None,
    ) -> list[SimilarityCandidate]:
        parsed = parse_factor(expression) if isinstance(expression, str) else expression
        if limit < 1:
            raise ValueError("limit must be positive")
        candidates = [
            self._candidate(parsed.features, revision)
            for revision in self.list_current()
            if revision.id != exclude_revision_id
        ]
        candidates.sort(
            key=lambda candidate: (
                not candidate.exact_structural_match,
                -candidate.score,
                candidate.revision.canonical_expression,
                candidate.revision.id,
            )
        )
        return candidates[:limit]

    @staticmethod
    def _candidate(features: FactorFeatures, revision: FactorRevision) -> SimilarityCandidate:
        stored_fields = frozenset(revision.fields)
        stored_operators = frozenset(revision.operators) | frozenset(revision.functions)
        exact = features.structural_signature == revision.ast_signature
        shape_match = float(features.shape_signature == revision.shape_signature)
        field_overlap = _jaccard(features.fields, stored_fields)
        operation_overlap = _jaccard(features.operator_function_set, stored_operators)
        # Exact AST identity is always ordered ahead of weighted approximate matches.
        score = 1.0 if exact else 0.5 * shape_match + 0.3 * field_overlap + 0.2 * operation_overlap
        if exact:
            reason = "exact AST structural signature"
        else:
            reason = (
                f"shape match {shape_match:.2f}; governed-field overlap {field_overlap:.2f}; "
                f"operator/function overlap {operation_overlap:.2f}"
            )
        return SimilarityCandidate(
            revision=revision,
            score=score,
            exact_structural_match=exact,
            shape_match=shape_match,
            field_overlap=field_overlap,
            operator_function_overlap=operation_overlap,
            reason=reason,
        )
