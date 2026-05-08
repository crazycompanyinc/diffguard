"""Dataclasses used across DiffGuard."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

Severity = Literal["low", "medium", "high"]
Verdict = Literal["approve", "concern", "block"]


@dataclass
class FileContext:
    path: str
    summary: str
    contracts: list[dict[str, Any]] = field(default_factory=list)
    patterns: list[dict[str, Any]] = field(default_factory=list)
    last_analyzed: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    id: int | None = None


@dataclass
class FileRelation:
    source_file: str
    target_file: str
    relation_type: str
    evidence: dict[str, Any] = field(default_factory=dict)
    id: int | None = None


@dataclass
class ImplicitContract:
    name: str
    description: str
    pattern_regex: str
    scope: str
    confidence: float
    evidence_count: int
    id: int | None = None


@dataclass
class ReviewArgument:
    type: str
    severity: Severity
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReviewResult:
    verdict: Verdict
    confidence: float
    arguments: list[ReviewArgument] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "confidence": round(max(0.0, min(1.0, self.confidence)), 3),
            "arguments": [
                {
                    "type": arg.type,
                    "severity": arg.severity,
                    "message": arg.message,
                    "evidence": arg.evidence,
                }
                for arg in self.arguments
            ],
            "suggestions": self.suggestions,
        }


@dataclass
class PRReview:
    pr_number: int
    repo: str
    arguments: list[dict[str, Any]]
    verdict: Verdict
    confidence: float
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    id: int | None = None
