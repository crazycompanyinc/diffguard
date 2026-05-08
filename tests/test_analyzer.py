from diffguard.analyzer.diff_analyzer import SemanticDiffAnalyzer, parse_git_diff
from diffguard.analyzer.intent_matcher import IntentMatcher, extract_changed_symbols, extract_keywords
from diffguard.core.db import DiffGuardDB
from diffguard.core.models import FileContext, FileRelation, ImplicitContract


DIFF = """diff --git a/api/users.py b/api/users.py
--- a/api/users.py
+++ b/api/users.py
@@
+@router.get('/admin')
+def admin_users():
+    return list_all_users()
"""


def test_parse_git_diff_reads_changed_file_and_added_lines():
    changes = parse_git_diff(DIFF)

    assert changes[0].path == "api/users.py"
    assert "def admin_users():" in changes[0].added


def test_intent_matcher_flags_cosmetic_intent_with_logic_change():
    match = IntentMatcher().match("fix typo", DIFF)

    assert match.risk_level in {"medium", "high"}
    assert match.mismatches
    assert "admin_users" in match.changed_symbols


def test_keyword_extraction_splits_identifiers():
    assert "admin" in extract_keywords("admin_users")
    assert "admin_users" in extract_changed_symbols("+def admin_users():")


def test_analyzer_flags_missing_auth_contract(tmp_path):
    db = DiffGuardDB(tmp_path / "db.sqlite3")
    db.upsert_file(FileContext("api/users.py", "existing route with auth"))
    db.upsert_contract(ImplicitContract("api_routes_require_auth", "routes auth", "auth", "repository", 0.9, 5))
    analysis = SemanticDiffAnalyzer(db).analyze(DIFF, "add admin route")

    assert any(issue.type == "implicit_contract" for issue in analysis.issues)


def test_analyzer_predicts_related_file_side_effect(tmp_path):
    db = DiffGuardDB(tmp_path / "db.sqlite3")
    db.upsert_file(FileContext("service.py", "business service"))
    db.replace_relations([FileRelation("service.py", "tests/test_service.py", "tested_by", {"matched_stem": "service"})])
    diff = "diff --git a/service.py b/service.py\n+++ b/service.py\n@@\n+def changed():\n+    return 2\n"

    analysis = SemanticDiffAnalyzer(db).analyze(diff, "change service behavior")

    assert analysis.side_effects[0]["related_file"] == "tests/test_service.py"
