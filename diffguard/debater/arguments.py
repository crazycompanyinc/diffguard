"""Argument formatting helpers."""

from __future__ import annotations

from diffguard.core.models import ReviewArgument


def from_issue(issue_type: str, severity: str, message: str, evidence: dict[str, object]) -> ReviewArgument:
    normalized = severity if severity in {"low", "medium", "high"} else "medium"
    return ReviewArgument(type=issue_type, severity=normalized, message=message, evidence=evidence)  # type: ignore[arg-type]


def severity_weight(severity: str) -> float:
    return {"low": 0.2, "medium": 0.45, "high": 0.75}.get(severity, 0.35)
