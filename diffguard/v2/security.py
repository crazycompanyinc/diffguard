"""Dedicated security audit checks."""

from __future__ import annotations

import re

from diffguard.analyzer.diff_analyzer import parse_git_diff


class SecurityAuditor:
    """Detects common vulnerability patterns in added diff lines."""

    CHECKS = [
        ("sql_injection", "high", re.compile(r"(execute|query|raw)\s*\([^)]*(\+|f[\"']|\$\{|%s)", re.I), "Parameterized queries should be used instead of string-built SQL."),
        ("xss", "high", re.compile(r"(innerHTML|dangerouslySetInnerHTML|html_safe|raw\()", re.I), "Untrusted HTML rendering needs sanitization or escaping."),
        ("auth_bypass", "high", re.compile(r"(skip_auth|without_auth|permit_all|return\s+true|TODO.*auth)", re.I), "Auth bypasses need explicit justification and tests."),
        ("secret_leakage", "high", re.compile(r"(api[_-]?key|secret|password|token)\s*[:=]\s*[\"'][^\"']{8,}", re.I), "Secrets must not be committed."),
        ("sensitive_logging", "medium", re.compile(r"(log|logger|console)\.[a-z]+\([^)]*(password|token|secret|ssn|credential)", re.I), "Sensitive values should not be logged."),
    ]

    def audit(self, diff_text: str) -> list[dict[str, object]]:
        findings: list[dict[str, object]] = []
        for change in parse_git_diff(diff_text):
            for line_no, line in enumerate(change.added, start=1):
                for finding_type, severity, pattern, guidance in self.CHECKS:
                    if pattern.search(line):
                        findings.append({"type": finding_type, "severity": severity, "path": change.path, "line": line_no, "message": guidance, "evidence": line.strip()[:220]})
        return findings
