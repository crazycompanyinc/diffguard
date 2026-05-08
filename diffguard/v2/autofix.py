"""Auto-fix suggestions with concrete snippets."""

from __future__ import annotations

from diffguard.v2.models import AutoFix, SemanticChange


class AutoFixSuggester:
    """Creates actionable remediation snippets for common findings."""

    def suggest(self, changes: list[SemanticChange], security_findings: list[dict[str, object]], performance_findings: list[dict[str, object]]) -> list[AutoFix]:
        fixes: list[AutoFix] = []
        for finding in security_findings:
            path = str(finding["path"])
            if finding["type"] == "sql_injection":
                fixes.append(AutoFix("Use parameterized SQL", path, "db.execute(\"SELECT * FROM users WHERE id = ?\", [user_id])", "Avoid string interpolation in SQL calls."))
            elif finding["type"] == "xss":
                fixes.append(AutoFix("Sanitize rendered HTML", path, "element.textContent = userProvidedValue", "Prefer text rendering or a trusted sanitizer over raw HTML injection."))
            elif finding["type"] == "auth_bypass":
                fixes.append(AutoFix("Require explicit authorization", path, "if (!currentUser.can(action, resource)) {\n  throw new ForbiddenError();\n}", "Replace bypasses with policy checks."))
            elif finding["type"] == "secret_leakage":
                fixes.append(AutoFix("Move secret to environment", path, "const token = process.env.SERVICE_TOKEN", "Secrets should be loaded from secret storage or environment variables."))
        for finding in performance_findings:
            path = str(finding["path"])
            if finding["type"] == "nested_loop":
                fixes.append(AutoFix("Index inner collection", path, "const byId = new Map(items.map(item => [item.id, item]));\nfor (const row of rows) {\n  use(byId.get(row.itemId));\n}", "Convert repeated scans into indexed lookups."))
            elif finding["type"] == "query_in_loop":
                fixes.append(AutoFix("Batch query outside loop", path, "const records = await repo.findByIds(ids);\nconst byId = new Map(records.map(record => [record.id, record]));", "Avoid N+1 query behavior."))
        for change in changes:
            if change.type in {"signature_change", "return_type_change"}:
                fixes.append(AutoFix("Update callers and tests", change.path, "# Update all callers to match the new signature and add regression tests for old and new behavior.", "Interface changes need call-site and test updates."))
        return fixes[:8]
