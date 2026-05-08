"""Reviewer assignment recommendations."""

from __future__ import annotations

from collections import Counter

from diffguard.v2.models import ReviewerRecommendation, SemanticChange


DEFAULT_REVIEWERS = {
    "auth": "security-reviewer",
    "security": "security-reviewer",
    "payment": "payments-reviewer",
    "billing": "payments-reviewer",
    "db": "data-reviewer",
    "migration": "data-reviewer",
    "api": "backend-reviewer",
    "frontend": "frontend-reviewer",
    "perf": "performance-reviewer",
    "performance": "performance-reviewer",
    "test": "qa-reviewer",
}


class ReviewerAssigner:
    """Chooses reviewers from paths, semantic changes, and findings."""

    def __init__(self, reviewer_map: dict[str, str] | None = None) -> None:
        self.reviewer_map = reviewer_map or DEFAULT_REVIEWERS

    def recommend(self, paths: list[str], changes: list[SemanticChange], findings: list[dict[str, object]]) -> list[ReviewerRecommendation]:
        text = " ".join(paths + [change.summary for change in changes] + [str(finding) for finding in findings]).lower()
        counts: Counter[str] = Counter()
        reasons: dict[str, str] = {}
        for keyword, reviewer in self.reviewer_map.items():
            if keyword in text:
                counts[reviewer] += 1
                reasons.setdefault(reviewer, f"Matched {keyword}-related changes.")
        if not counts:
            return [ReviewerRecommendation("generalist-reviewer", "No specialized area dominated the diff.", 0.55)]
        return [ReviewerRecommendation(reviewer, reasons[reviewer], round(min(0.95, 0.55 + count * 0.15), 3)) for reviewer, count in counts.most_common(3)]
