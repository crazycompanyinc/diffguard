"""Semantic diff analysis against learned context."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from diffguard.analyzer.intent_matcher import IntentMatch, IntentMatcher
from diffguard.core.db import DiffGuardDB


@dataclass
class DiffFileChange:
    path: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


@dataclass
class SemanticIssue:
    type: str
    severity: str
    message: str
    evidence: dict[str, object]


@dataclass
class DiffAnalysis:
    changed_files: list[DiffFileChange]
    intent_match: IntentMatch
    issues: list[SemanticIssue]
    side_effects: list[dict[str, object]]


class SemanticDiffAnalyzer:
    """Analyzes a git diff using learned file context and implicit contracts."""

    def __init__(self, db: DiffGuardDB | None = None, matcher: IntentMatcher | None = None) -> None:
        self.db = db or DiffGuardDB()
        self.matcher = matcher or IntentMatcher()

    def analyze(self, diff_text: str, intent: str) -> DiffAnalysis:
        changed_files = parse_git_diff(diff_text)
        intent_match = self.matcher.match(intent, diff_text)
        issues = self._intent_issues(intent_match) + self._contract_issues(changed_files)
        side_effects = self._predict_side_effects(changed_files, intent)
        for side_effect in side_effects:
            if side_effect.get("risk") == "unmentioned_related_file":
                issues.append(
                    SemanticIssue(
                        "side_effect",
                        "medium",
                        f"{side_effect['changed_file']} is related to {side_effect['related_file']}, but the intent does not mention that area.",
                        side_effect,
                    )
                )
        return DiffAnalysis(changed_files, intent_match, issues, side_effects)

    def _intent_issues(self, match: IntentMatch) -> list[SemanticIssue]:
        severity = "high" if match.risk_level == "high" else "medium"
        return [
            SemanticIssue(
                "intent_mismatch",
                severity,
                mismatch,
                {
                    "intent_keywords": sorted(match.intent_keywords),
                    "diff_keywords": sorted(list(match.diff_keywords))[:20],
                    "changed_symbols": match.changed_symbols,
                    "score": match.score,
                },
            )
            for mismatch in match.mismatches
        ]

    def _contract_issues(self, changed_files: list[DiffFileChange]) -> list[SemanticIssue]:
        issues: list[SemanticIssue] = []
        contracts = {contract.name: contract for contract in self.db.list_contracts()}
        for change in changed_files:
            added_text = "\n".join(change.added)
            removed_text = "\n".join(change.removed)
            context = self.db.get_file(change.path)
            if self._looks_like_route(change.path, added_text) and not re.search(r"\b(auth|permission|current_user|jwt|login_required)\b", added_text, re.I):
                contract = contracts.get("api_routes_require_auth")
                if contract and contract.confidence >= 0.6:
                    issues.append(
                        SemanticIssue(
                            "implicit_contract",
                            "high",
                            f"{change.path} adds or changes API route behavior without an obvious auth check.",
                            {"contract": contract.description, "confidence": contract.confidence, "file_summary": context.summary if context else None},
                        )
                    )
            if re.search(r"\b(insert|update|delete|save|create|execute\()\b", added_text, re.I) and not re.search(r"\b(transaction|atomic|commit|rollback|session\.begin)\b", added_text, re.I):
                contract = contracts.get("db_writes_use_transactions")
                if contract and contract.confidence >= 0.5:
                    issues.append(
                        SemanticIssue(
                            "implicit_contract",
                            "high",
                            f"{change.path} changes DB write behavior without matching the repository transaction pattern.",
                            {"contract": contract.description, "confidence": contract.confidence},
                        )
                    )
            if re.search(r"\b(auth|permission|middleware)\b", added_text + removed_text, re.I) and not any("test" in f.path.lower() for f in changed_files):
                issues.append(
                    SemanticIssue(
                        "historical_pattern",
                        "medium",
                        f"{change.path} modifies auth-sensitive code, but this diff does not include test updates.",
                        {"pattern": "Auth and permission changes should include nearby tests.", "changed_file": change.path},
                    )
                )
        return issues

    def _predict_side_effects(self, changed_files: list[DiffFileChange], intent: str) -> list[dict[str, object]]:
        effects: list[dict[str, object]] = []
        intent_lower = intent.lower()
        changed_paths = {change.path for change in changed_files}
        for change in changed_files:
            for relation in self.db.list_relations_for(change.path):
                related = relation.target_file if relation.source_file == change.path else relation.source_file
                if related in changed_paths:
                    continue
                area = related.split("/")[-1].split(".")[0].lower()
                if area not in intent_lower:
                    effects.append(
                        {
                            "risk": "unmentioned_related_file",
                            "changed_file": change.path,
                            "related_file": related,
                            "relation_type": relation.relation_type,
                            "evidence": relation.evidence,
                        }
                    )
        return effects

    def _looks_like_route(self, path: str, text: str) -> bool:
        return bool(re.search(r"(@app\.route|@router\.|APIRouter|FastAPI|/api/|route\()", text, re.I) or "/api/" in path)


def parse_git_diff(diff_text: str) -> list[DiffFileChange]:
    changes: list[DiffFileChange] = []
    current: DiffFileChange | None = None
    for line in diff_text.splitlines():
        match = re.match(r"diff --git a/(.*?) b/(.*)", line)
        if match:
            if current:
                changes.append(current)
            current = DiffFileChange(path=match.group(2))
            continue
        if current is None:
            continue
        if line.startswith("+++ b/"):
            current.path = line[6:]
        elif line.startswith("+") and not line.startswith("+++"):
            current.added.append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            current.removed.append(line[1:])
    if current:
        changes.append(current)
    return changes
