from diffguard.analyzer.diff_analyzer import SemanticDiffAnalyzer
from diffguard.core.db import DiffGuardDB
from diffguard.debater.debater import PRDebater
from diffguard.learner.context_learner import CodebaseContextLearner
from diffguard.server.app import format_review_comment
from diffguard.server.webhooks import should_review_pull_request, verify_signature


def test_end_to_end_learning_review_and_comment(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "accounts.py").write_text(
        "@router.get('/accounts')\ndef accounts():\n    current_user()\n    return []\n",
        encoding="utf-8",
    )
    db = DiffGuardDB(tmp_path / "db.sqlite3")
    CodebaseContextLearner(db).learn(tmp_path)
    diff = """diff --git a/api/accounts.py b/api/accounts.py
+++ b/api/accounts.py
@@
+@router.get('/accounts/admin')
+def admin_accounts():
+    return all_accounts()
"""

    result = PRDebater(db, SemanticDiffAnalyzer(db)).review_diff(diff, "add account admin route")
    comment = format_review_comment(result.to_dict())

    assert result.verdict in {"concern", "block"}
    assert "DiffGuard verdict" in comment
    assert "auth" in comment.lower()


def test_webhook_helpers():
    assert verify_signature(b"{}", None, secret=None)
    assert not verify_signature(b"{}", "bad", secret="secret")
    assert should_review_pull_request({"action": "opened", "pull_request": {}})
    assert not should_review_pull_request({"action": "closed", "pull_request": {}})
