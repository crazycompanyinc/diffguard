"""Historical PR learning and cross-PR impact analysis."""

from __future__ import annotations

import re
from collections import Counter

from diffguard.core.db import DiffGuardDB
from diffguard.v2.models import SemanticChange


class HistoricalLearner:
    """Finds similar prior reviews using stored PR review arguments."""

    def __init__(self, db: DiffGuardDB) -> None:
        self.db = db

    def similar_reviews(self, changes: list[SemanticChange], limit: int = 5) -> list[dict[str, object]]:
        rows = self.db.conn.execute("SELECT pr_number, repo, arguments_json, verdict, confidence, created_at FROM pr_reviews ORDER BY id DESC").fetchall()
        query_terms = _terms(" ".join(change.summary + " " + change.path + " " + change.type for change in changes))
        matches: list[dict[str, object]] = []
        for row in rows:
            haystack = f"{row['arguments_json']} {row['verdict']}"
            overlap = query_terms & _terms(haystack)
            if overlap:
                matches.append({"pr_number": row["pr_number"], "repo": row["repo"], "verdict": row["verdict"], "confidence": row["confidence"], "because": sorted(overlap)[:8], "created_at": row["created_at"], "similarity": round(len(overlap) / max(1, len(query_terms)), 3)})
        return sorted(matches, key=lambda item: item["similarity"], reverse=True)[:limit]


class CrossPRImpactAnalyzer:
    """Flags interactions between the current PR and recent reviewed PRs."""

    def __init__(self, db: DiffGuardDB) -> None:
        self.db = db

    def analyze(self, current_pr: int, repo: str, changes: list[SemanticChange], limit: int = 20) -> list[dict[str, object]]:
        rows = self.db.conn.execute(
            "SELECT pr_number, repo, arguments_json, verdict FROM pr_reviews WHERE repo = ? AND pr_number != ? ORDER BY id DESC LIMIT ?",
            (repo, current_pr, limit),
        ).fetchall()
        current_paths = {change.path for change in changes}
        current_areas = Counter(_area(path) for path in current_paths)
        impacts: list[dict[str, object]] = []
        for row in rows:
            text = row["arguments_json"]
            path_hits = {path for path in current_paths if path in text}
            area_hits = {area for area in current_areas if area and re.search(rf"\b{re.escape(area)}\b", text, re.I)}
            if path_hits or area_hits:
                impacts.append({"pr_number": row["pr_number"], "repo": row["repo"], "risk": "related_recent_pr", "shared_paths": sorted(path_hits), "shared_areas": sorted(area_hits), "prior_verdict": row["verdict"]})
        return impacts


def _terms(text: str) -> set[str]:
    return {term.lower() for term in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text) if term.lower() not in {"the", "and", "for", "with"}}


def _area(path: str) -> str:
    parts = [part for part in re.split(r"[/_.-]+", path.lower()) if part and part not in {"src", "lib", "app", "test", "tests"}]
    return parts[0] if parts else ""
