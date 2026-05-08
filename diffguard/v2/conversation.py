"""Review conversation simulation."""

from __future__ import annotations

from diffguard.v2.models import ConversationTurn, QualityScore, SemanticChange


class ConversationSimulator:
    """Simulates reviewer and author turns for the highest-value concerns."""

    def simulate(self, changes: list[SemanticChange], findings: list[dict[str, object]], score: QualityScore, rounds: int = 4) -> list[ConversationTurn]:
        turns: list[ConversationTurn] = []
        topics = [change.summary for change in changes if change.severity in {"medium", "high"}]
        topics.extend(str(finding.get("message", finding)) for finding in findings)
        topics.append(f"Quality score is {score.overall}; tests score {score.test_coverage}.")
        for index, topic in enumerate(topics[:rounds], start=1):
            turns.append(ConversationTurn("DiffGuard", f"Question {index}: {topic} What evidence proves this is safe for callers and users?"))
            turns.append(ConversationTurn("Author", "I would need to point to tests, rollout constraints, or updated callers to close that concern."))
            turns.append(ConversationTurn("DiffGuard", "Please add that evidence to the PR or narrow the change before approval."))
        return turns
