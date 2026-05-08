from diffguard.core.db import DiffGuardDB
from diffguard.core.models import FileContext, FileRelation, ImplicitContract, PRReview


def test_db_stores_files_contracts_relations_and_reviews(tmp_path):
    db = DiffGuardDB(tmp_path / "dg.sqlite3")
    db.upsert_file(FileContext("app.py", "summary", [{"name": "c", "present": True}], [{"name": "p"}]))
    db.replace_relations([FileRelation("app.py", "tests/test_app.py", "tested_by", {"matched_stem": "app"})])
    db.upsert_contract(ImplicitContract("api_routes_require_auth", "desc", "regex", "repository", 0.9, 3))
    db.save_review(PRReview(1, "o/r", [{"message": "m"}], "concern", 0.7))

    assert db.get_file("app.py").summary == "summary"
    assert db.list_relations_for("app.py")[0].target_file == "tests/test_app.py"
    assert db.list_contracts()[0].confidence == 0.9
    assert db.stats() == {"files": 1, "relations": 1, "contracts": 1, "reviews": 1}


def test_upsert_file_updates_existing_row(tmp_path):
    db = DiffGuardDB(tmp_path / "dg.sqlite3")
    db.upsert_file(FileContext("app.py", "old"))
    db.upsert_file(FileContext("app.py", "new"))

    assert db.stats()["files"] == 1
    assert db.get_file("app.py").summary == "new"
