"""Devil's advocate PR debate logic."""

from __future__ import annotations

import json
from typing import Iterable

from diffguard.analyzer.diff_analyzer import DiffAnalysis, SemanticDiffAnalyzer
from diffguard.core.db import DiffGuardDB
from diffguard.core.models import PRReview, ReviewArgument, ReviewResult
from diffguard.debater.arguments import from_issue, severity_weight


class PRDebater:
    """Turns semantic analysis into structured review arguments."""

    def __init__(self, db: DiffGuardDB | None = None, analyzer: SemanticDiffAnalyzer | None = None) -> None:
        self.db = db or DiffGuardDB()
        self.analyzer = analyzer or SemanticDiffAnalyzer(self.db)

    def review_diff(self, diff_text: str, intent: str, pr_number: int = 0, repo: str = "local") -> ReviewResult:
        analysis = self.analyzer.analyze(diff_text, intent)
        result = self._build_result(analysis)
        if pr_number:
            self.db.save_review(PRReview(pr_number, repo, result.to_dict()["arguments"], result.verdict, result.confidence))
        return result

    def debate(self, diff_text: str, intent: str, rounds: int = 3) -> list[dict[str, str]]:
        result = self.review_diff(diff_text, intent)
        transcript: list[dict[str, str]] = []
        top_args = result.arguments[: max(1, rounds)]
        for index, arg in enumerate(top_args, start=1):
            transcript.append({"speaker": "DiffGuard", "message": arg.message})
            transcript.append(
                {
                    "speaker": "Author",
                    "message": "The intent still looks reasonable if the evidence is addressed.",
                }
            )
            transcript.append(
                {
                    "speaker": "DiffGuard",
                    "message": self._rebuttal(arg, index),
                }
            )
        if not transcript:
            transcript.append({"speaker": "DiffGuard", "message": "I do not see a strong devil's advocate case in this diff."})
        return transcript

    def _build_result(self, analysis: DiffAnalysis) -> ReviewResult:
        arguments = [from_issue(issue.type, issue.severity, issue.message, issue.evidence) for issue in analysis.issues]
        arguments.extend(self._coverage_arguments(analysis))
        arguments = sorted(arguments, key=lambda arg: severity_weight(arg.severity), reverse=True)
        score = sum(severity_weight(arg.severity) for arg in arguments)
        if any(arg.severity == "high" for arg in arguments) or score >= 1.2:
            verdict = "block"
        elif arguments or analysis.intent_match.score < 0.35:
            verdict = "concern"
        else:
            verdict = "approve"
        confidence = min(0.95, 0.35 + score + (0.25 if analysis.intent_match.mismatches else 0.0))
        suggestions = self._suggestions(arguments, analysis)
        return ReviewResult(verdict=verdict, confidence=confidence, arguments=arguments, suggestions=suggestions)

    def _coverage_arguments(self, analysis: DiffAnalysis) -> list[ReviewArgument]:
        paths = [change.path for change in analysis.changed_files]
        has_tests = any("test" in path.lower() or "spec" in path.lower() for path in paths)
        sensitive = [path for path in paths if any(word in path.lower() for word in ("auth", "billing", "payment", "db", "api"))]
        if sensitive and not has_tests:
            return [
                ReviewArgument(
                    "test_coverage",
                    "medium",
                    f"This change touches sensitive area(s) {', '.join(sensitive[:4])} without test changes.",
                    {"changed_files": paths, "sensitive_files": sensitive},
                )
            ]
        return []

    def _suggestions(self, arguments: Iterable[ReviewArgument], analysis: DiffAnalysis) -> list[str]:
        suggestions: list[str] = []
        if any(arg.type == "intent_mismatch" for arg in arguments):
            suggestions.append("Rewrite the PR title/description to name the actual behavioral areas changed, or narrow the diff.")
        if any(arg.type in {"implicit_contract", "historical_pattern", "test_coverage"} for arg in arguments):
            suggestions.append("Add tests or code evidence showing the implicit contract still holds.")
        if analysis.side_effects:
            suggestions.append("Mention related files and downstream behavior in the PR description.")
        if not suggestions:
            suggestions.append("No blocking semantic concern found; keep the PR description aligned with the final diff.")
        return suggestions

    def _rebuttal(self, argument: ReviewArgument, index: int) -> str:
        evidence = json.dumps(argument.evidence, sort_keys=True)
        return f"Round {index}: the concern is evidence-backed ({evidence[:220]}). Address that evidence before treating this as safe."
