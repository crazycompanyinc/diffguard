"""Top-level DiffGuard v2 review orchestration."""

from __future__ import annotations

from diffguard.analyzer.diff_analyzer import parse_git_diff
from diffguard.core.db import DiffGuardDB
from diffguard.core.models import PRReview
from diffguard.debater.debater import PRDebater
from diffguard.v2.autofix import AutoFixSuggester
from diffguard.v2.conversation import ConversationSimulator
from diffguard.v2.history import CrossPRImpactAnalyzer, HistoricalLearner
from diffguard.v2.knowledge_graph import KnowledgeGraphBuilder
from diffguard.v2.models import V2ReviewResult
from diffguard.v2.performance import PerformanceAnalyzer
from diffguard.v2.policies import AgentPolicyReviewer
from diffguard.v2.reviewer import ReviewerAssigner
from diffguard.v2.scoring import PRQualityScorer
from diffguard.v2.security import SecurityAuditor
from diffguard.v2.semantic_engine import SemanticDiffEngine


class V2ReviewEngine:
    """Runs full DiffGuard v2 analysis while preserving v1 review output."""

    def __init__(self, db: DiffGuardDB | None = None) -> None:
        self.db = db or DiffGuardDB()
        self.base = PRDebater(self.db)
        self.semantic = SemanticDiffEngine()
        self.security = SecurityAuditor()
        self.performance = PerformanceAnalyzer()
        self.graph = KnowledgeGraphBuilder(self.db)
        self.history = HistoricalLearner(self.db)
        self.cross_pr = CrossPRImpactAnalyzer(self.db)
        self.policy = AgentPolicyReviewer()
        self.fixes = AutoFixSuggester()
        self.reviewers = ReviewerAssigner()
        self.scorer = PRQualityScorer()
        self.conversation = ConversationSimulator()

    def review_diff(self, diff_text: str, intent: str, pr_number: int = 0, repo: str = "local", agent: str | None = None) -> V2ReviewResult:
        base_result = self.base.review_diff(diff_text, intent, pr_number=0, repo=repo).to_dict()
        semantic_changes = self.semantic.analyze(diff_text)
        security_findings = self.security.audit(diff_text)
        performance_findings = self.performance.analyze(diff_text)
        graph_impacts = self.graph.impacts_for_changes(semantic_changes)
        historical_matches = self.history.similar_reviews(semantic_changes)
        cross_pr_impacts = self.cross_pr.analyze(pr_number, repo, semantic_changes) if pr_number else []
        changed_paths = [change.path for change in parse_git_diff(diff_text)]
        agent_findings = self.policy.review(agent, semantic_changes, changed_paths)
        combined_findings = security_findings + performance_findings + agent_findings + graph_impacts + cross_pr_impacts
        auto_fixes = self.fixes.suggest(semantic_changes, security_findings, performance_findings)
        quality_score = self.scorer.score(diff_text, intent, semantic_changes, combined_findings)
        reviewer_recommendations = self.reviewers.recommend(changed_paths, semantic_changes, combined_findings)
        conversation = self.conversation.simulate(semantic_changes, combined_findings, quality_score)
        result = V2ReviewResult(
            base_review=base_result,
            semantic_changes=semantic_changes,
            graph_impacts=graph_impacts,
            historical_matches=historical_matches,
            cross_pr_impacts=cross_pr_impacts,
            agent_findings=agent_findings,
            auto_fixes=auto_fixes,
            reviewer_recommendations=reviewer_recommendations,
            quality_score=quality_score,
            conversation=conversation,
            security_findings=security_findings,
            performance_findings=performance_findings,
        )
        if pr_number:
            self.db.save_review(PRReview(pr_number, repo, base_result["arguments"], base_result["verdict"], base_result["confidence"]))
        return result
