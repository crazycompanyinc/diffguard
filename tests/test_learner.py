from pathlib import Path

from diffguard.core.db import DiffGuardDB
from diffguard.learner.context_learner import CodebaseContextLearner


def test_learner_extracts_file_context_and_contracts(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "users.py").write_text(
        """
from auth import require_user
@router.get('/users')
def list_users():
    require_user()
    try:
        return []
    except Exception:
        raise
""",
        encoding="utf-8",
    )
    db = DiffGuardDB(tmp_path / ".diffguard" / "db.sqlite3")
    stats = CodebaseContextLearner(db).learn(tmp_path)

    context = db.get_file("api/users.py")
    assert stats["files"] == 1
    assert "list_users" in context.summary
    assert any(contract.name == "api_routes_require_auth" for contract in db.list_contracts())


def test_learner_builds_test_relation(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "service.py").write_text("def calculate_total():\n    return 1\n", encoding="utf-8")
    (tmp_path / "tests" / "test_service.py").write_text("from service import calculate_total\n", encoding="utf-8")
    db = DiffGuardDB(tmp_path / "db.sqlite3")
    CodebaseContextLearner(db).learn(tmp_path)

    relations = db.list_relations_for("service.py")
    assert any(rel.relation_type in {"imports", "tested_by"} for rel in relations)


def test_learner_detects_db_transaction_pattern(tmp_path):
    (tmp_path / "repo.py").write_text(
        "def save_user(session):\n    with session.begin():\n        session.execute('insert into users')\n",
        encoding="utf-8",
    )
    db = DiffGuardDB(tmp_path / "db.sqlite3")
    CodebaseContextLearner(db).learn(tmp_path)

    contract = [c for c in db.list_contracts() if c.name == "db_writes_use_transactions"][0]
    assert contract.confidence == 1.0
