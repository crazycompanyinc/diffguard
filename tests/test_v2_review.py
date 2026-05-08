from diffguard.core.db import DiffGuardDB
from diffguard.core.models import FileContext, FileRelation, PRReview
from diffguard.v2.review import V2ReviewEngine
from diffguard.v2.semantic_engine import SemanticDiffEngine


DIFF = """diff --git a/src/auth/users.ts b/src/auth/users.ts
--- a/src/auth/users.ts
+++ b/src/auth/users.ts
@@
-export function getUser(id: string): User {
-  return repo.find(id);
-}
+export function fetchUser(id: string): Promise<User> {
+  db.execute("select * from users where id = " + id);
+  for (const group of groups) {
+    for (const user of group.users) {
+      console.log(user.token);
+    }
+  }
+  return repo.find(id);
+}
"""


def test_semantic_diff_engine_classifies_rename_and_return_type_change():
    changes = SemanticDiffEngine().analyze(DIFF)
    change_types = {change.type for change in changes}

    assert "symbol_rename" in change_types
    assert "return_type_change" in change_types
    assert "business_logic_change" in change_types


def test_v2_review_runs_all_major_lanes(tmp_path):
    db = DiffGuardDB(tmp_path / "db.sqlite3")
    db.upsert_file(FileContext("src/auth/users.ts", "auth user service"))
    db.upsert_file(FileContext("tests/users.spec.ts", "tests for auth user service"))
    db.replace_relations([FileRelation("src/auth/users.ts", "tests/users.spec.ts", "tested_by", {"matched_stem": "users"})])
    db.save_review(
        PRReview(
            142,
            "o/r",
            [{"message": "src/auth/users.ts auth change required tests", "path": "src/auth/users.ts"}],
            "concern",
            0.7,
        )
    )

    result = V2ReviewEngine(db).review_diff(DIFF, "refactor user lookup", pr_number=143, repo="o/r", agent="Agent-Alpha")
    data = result.to_dict()

    assert data["semantic_changes"]
    assert any(finding["type"] == "sql_injection" for finding in data["security_findings"])
    assert any(finding["type"] == "nested_loop" for finding in data["performance_findings"])
    assert data["graph_impacts"]
    assert data["historical_matches"]
    assert data["cross_pr_impacts"]
    assert data["agent_findings"]
    assert data["auto_fixes"]
    assert data["reviewer_recommendations"][0]["reviewer"] in {"security-reviewer", "backend-reviewer"}
    assert 0 <= data["quality_score"]["overall"] <= 1
    assert data["conversation"]
