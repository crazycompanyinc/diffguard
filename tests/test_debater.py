from diffguard.core.db import DiffGuardDB
from diffguard.core.models import ImplicitContract
from diffguard.debater.debater import PRDebater


def test_debater_returns_structured_blocking_result_for_high_risk_diff(tmp_path):
    db = DiffGuardDB(tmp_path / "db.sqlite3")
    db.upsert_contract(ImplicitContract("api_routes_require_auth", "routes auth", "auth", "repository", 0.9, 4))
    diff = """diff --git a/api/admin.py b/api/admin.py
+++ b/api/admin.py
@@
+@router.get('/admin')
+def admin():
+    return all_users()
"""

    result = PRDebater(db).review_diff(diff, "fix typo")
    data = result.to_dict()

    assert data["verdict"] == "block"
    assert data["arguments"]
    assert {"verdict", "confidence", "arguments", "suggestions"} <= set(data)


def test_debate_mode_generates_back_and_forth(tmp_path):
    db = DiffGuardDB(tmp_path / "db.sqlite3")
    diff = "diff --git a/auth.py b/auth.py\n+++ b/auth.py\n@@\n-def check():\n+def check():\n+    return True\n"
    transcript = PRDebater(db).debate(diff, "fix typo", rounds=1)

    assert transcript[0]["speaker"] == "DiffGuard"
    assert any(turn["speaker"] == "Author" for turn in transcript)
