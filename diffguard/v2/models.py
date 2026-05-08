"""Typed models for DiffGuard v2 analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Risk = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class CodeSymbol:
    name: str
    kind: str
    signature: str
    return_type: str | None = None
    visibility: str | None = None
    decorators: tuple[str, ...] = ()
    line: int = 0


@dataclass(frozen=True)
class LanguageProfile:
    language: str
    path: str
    symbols: tuple[CodeSymbol, ...] = ()
    imports: tuple[str, ...] = ()
    contracts: tuple[dict[str, Any], ...] = ()
    concerns: tuple[str, ...] = ()


@dataclass(frozen=True)
class SemanticChange:
    type: str
    path: str
    severity: Risk
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeNode:
    id: str
    kind: str
    label: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeEdge:
    source: str
    target: str
    relation: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeGraph:
    nodes: dict[str, KnowledgeNode] = field(default_factory=dict)
    edges: list[KnowledgeEdge] = field(default_factory=list)

    def add_node(self, node: KnowledgeNode) -> None:
        self.nodes[node.id] = node

    def add_edge(self, edge: KnowledgeEdge) -> None:
        if edge.source != edge.target:
            self.edges.append(edge)

    def neighbors(self, node_id: str) -> list[KnowledgeEdge]:
        return [edge for edge in self.edges if edge.source == node_id or edge.target == node_id]


@dataclass(frozen=True)
class QualityScore:
    overall: float
    completeness: float
    test_coverage: float
    documentation: float
    conventions: float
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewerRecommendation:
    reviewer: str
    reason: str
    confidence: float


@dataclass(frozen=True)
class AutoFix:
    title: str
    path: str
    snippet: str
    rationale: str


@dataclass(frozen=True)
class ConversationTurn:
    speaker: str
    message: str


@dataclass
class V2ReviewResult:
    base_review: dict[str, Any]
    semantic_changes: list[SemanticChange]
    graph_impacts: list[dict[str, Any]]
    historical_matches: list[dict[str, Any]]
    cross_pr_impacts: list[dict[str, Any]]
    agent_findings: list[dict[str, Any]]
    auto_fixes: list[AutoFix]
    reviewer_recommendations: list[ReviewerRecommendation]
    quality_score: QualityScore
    conversation: list[ConversationTurn]
    security_findings: list[dict[str, Any]]
    performance_findings: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_review": self.base_review,
            "semantic_changes": [change.__dict__ for change in self.semantic_changes],
            "graph_impacts": self.graph_impacts,
            "historical_matches": self.historical_matches,
            "cross_pr_impacts": self.cross_pr_impacts,
            "agent_findings": self.agent_findings,
            "auto_fixes": [fix.__dict__ for fix in self.auto_fixes],
            "reviewer_recommendations": [reviewer.__dict__ for reviewer in self.reviewer_recommendations],
            "quality_score": self.quality_score.__dict__,
            "conversation": [turn.__dict__ for turn in self.conversation],
            "security_findings": self.security_findings,
            "performance_findings": self.performance_findings,
        }
