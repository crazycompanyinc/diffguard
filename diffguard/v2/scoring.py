"""PR quality scoring."""

from __future__ import annotations

from diffguard.analyzer.diff_analyzer import parse_git_diff
from diffguard.v2.models import QualityScore, SemanticChange


class PRQualityScorer:
    """Scores completeness, tests, docs, and conventions on a 0..1 scale."""

    def score(self, diff_text: str, intent: str, changes: list[SemanticChange], findings: list[dict[str, object]]) -> QualityScore:
        files = parse_git_diff(diff_text)
        paths = [file.path for file in files]
        has_tests = any("test" in path.lower() or "spec" in path.lower() for path in paths)
        has_docs = any(path.lower().endswith((".md", ".rst")) or "docs/" in path.lower() for path in paths)
        semantic_risk = sum({"low": 0.05, "medium": 0.12, "high": 0.22}.get(change.severity, 0.1) for change in changes)
        finding_risk = sum({"low": 0.05, "medium": 0.12, "high": 0.22}.get(str(f.get("severity")), 0.1) for f in findings)
        sensitive = any(any(word in path.lower() for word in ("auth", "payment", "billing", "api", "db")) for path in paths)
        completeness = _clamp(0.9 - semantic_risk)
        test_coverage = 0.95 if has_tests else 0.35 if sensitive else 0.65
        documentation = 0.9 if has_docs else 0.75 if len(intent) > 40 else 0.5
        conventions = _clamp(0.95 - finding_risk)
        overall = _clamp((completeness * 0.3) + (test_coverage * 0.3) + (documentation * 0.15) + (conventions * 0.25))
        return QualityScore(round(overall, 3), round(completeness, 3), round(test_coverage, 3), round(documentation, 3), round(conventions, 3), {"changed_files": paths, "sensitive": sensitive, "has_tests": has_tests, "has_docs": has_docs})


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
