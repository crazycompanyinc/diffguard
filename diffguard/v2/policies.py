"""Agent-specific review policies."""

from __future__ import annotations

import re

from diffguard.v2.models import SemanticChange


DEFAULT_AGENT_POLICIES = {
    "agent-alpha": {"strict_areas": ("auth", "permission", "jwt", "session"), "min_tests_for_sensitive": True},
    "agent-beta": {"strict_areas": ("billing", "payment", "invoice"), "min_tests_for_sensitive": True},
    "agent-perf": {"strict_areas": ("query", "cache", "loop", "batch"), "min_tests_for_sensitive": False},
}


class AgentPolicyReviewer:
    """Applies per-agent review rules to a semantic change set."""

    def __init__(self, policies: dict[str, dict[str, object]] | None = None) -> None:
        self.policies = policies or DEFAULT_AGENT_POLICIES

    def review(self, agent: str | None, changes: list[SemanticChange], changed_paths: list[str]) -> list[dict[str, object]]:
        if not agent:
            return []
        policy = self.policies.get(agent.lower())
        if not policy:
            return []
        joined = "\n".join([change.summary + " " + change.path for change in changes] + changed_paths)
        strict_areas = tuple(str(area) for area in policy.get("strict_areas", ()))
        findings: list[dict[str, object]] = []
        for area in strict_areas:
            if re.search(rf"\b{re.escape(area)}\b", joined, re.I):
                findings.append({"agent": agent, "severity": "high", "area": area, "message": f"{agent}'s PRs require stricter review for {area} changes."})
        if findings and policy.get("min_tests_for_sensitive") and not any("test" in path.lower() or "spec" in path.lower() for path in changed_paths):
            findings.append({"agent": agent, "severity": "medium", "area": "tests", "message": f"{agent}'s sensitive change does not include test files."})
        return findings
