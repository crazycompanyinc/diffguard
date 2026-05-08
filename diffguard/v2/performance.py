"""Performance impact analysis."""

from __future__ import annotations

import re

from diffguard.analyzer.diff_analyzer import parse_git_diff


class PerformanceAnalyzer:
    """Flags likely complexity and resource regressions."""

    def analyze(self, diff_text: str) -> list[dict[str, object]]:
        findings: list[dict[str, object]] = []
        for change in parse_git_diff(diff_text):
            added = "\n".join(change.added)
            if self._nested_loop(added):
                findings.append({"type": "nested_loop", "severity": "medium", "path": change.path, "message": "Added nested iteration may become O(n^2) with larger inputs.", "evidence": self._snippet(added, r"\b(for|while|forEach|map)\b")})
            if re.search(r"\bSELECT\b|\bfindAll\b|\ball\(\)", added, re.I) and self._loop_context(added):
                findings.append({"type": "query_in_loop", "severity": "high", "path": change.path, "message": "Database or collection-wide query appears inside iterative code.", "evidence": self._snippet(added, r"SELECT|findAll|all\(\)")})
            if re.search(r"\b(readFileSync|sleep\(|time\.Sleep|Thread\.sleep|await\s+.*forEach)\b", added):
                findings.append({"type": "blocking_work", "severity": "medium", "path": change.path, "message": "Added blocking or serial work on a likely request path.", "evidence": self._snippet(added, r"readFileSync|sleep|Sleep|forEach")})
        return findings

    def _nested_loop(self, text: str) -> bool:
        compact = re.sub(r"\s+", " ", text)
        return bool(re.search(r"\b(for|while|forEach|map)\b.{0,220}\b(for|while|forEach|map)\b", compact))

    def _loop_context(self, text: str) -> bool:
        return bool(re.search(r"\b(for|while|forEach|map)\b", text))

    def _snippet(self, text: str, pattern: str) -> str:
        match = re.search(pattern, text, re.I)
        if not match:
            return text[:220]
        start = max(0, match.start() - 80)
        return text[start : start + 220].strip()
