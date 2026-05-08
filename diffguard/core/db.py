"""SQLite persistence for DiffGuard."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from diffguard.core.models import FileContext, FileRelation, ImplicitContract, PRReview


DEFAULT_DB_PATH = Path(".diffguard") / "diffguard.sqlite3"


class DiffGuardDB:
    """Small SQLite storage layer with typed helpers."""

    def __init__(self, path: str | Path = DEFAULT_DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.initialize()

    def close(self) -> None:
        self.conn.close()

    def initialize(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                summary TEXT NOT NULL,
                contracts_json TEXT NOT NULL,
                patterns_json TEXT NOT NULL,
                last_analyzed TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS file_relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file TEXT NOT NULL,
                target_file TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                evidence_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pr_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pr_number INTEGER NOT NULL,
                repo TEXT NOT NULL,
                arguments_json TEXT NOT NULL,
                verdict TEXT NOT NULL,
                confidence REAL NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS implicit_contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT NOT NULL,
                pattern_regex TEXT NOT NULL,
                scope TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence_count INTEGER NOT NULL
            );
            """
        )
        self.conn.commit()

    def upsert_file(self, context: FileContext) -> None:
        self.conn.execute(
            """
            INSERT INTO files(path, summary, contracts_json, patterns_json, last_analyzed)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                summary=excluded.summary,
                contracts_json=excluded.contracts_json,
                patterns_json=excluded.patterns_json,
                last_analyzed=excluded.last_analyzed
            """,
            (
                context.path,
                context.summary,
                json.dumps(context.contracts, sort_keys=True),
                json.dumps(context.patterns, sort_keys=True),
                context.last_analyzed,
            ),
        )
        self.conn.commit()

    def get_file(self, path: str) -> FileContext | None:
        row = self.conn.execute("SELECT * FROM files WHERE path = ?", (path,)).fetchone()
        return self._file_from_row(row) if row else None

    def list_files(self) -> list[FileContext]:
        rows = self.conn.execute("SELECT * FROM files ORDER BY path").fetchall()
        return [self._file_from_row(row) for row in rows]

    def replace_relations(self, relations: Iterable[FileRelation]) -> None:
        self.conn.execute("DELETE FROM file_relations")
        self.conn.executemany(
            """
            INSERT INTO file_relations(source_file, target_file, relation_type, evidence_json)
            VALUES (?, ?, ?, ?)
            """,
            [
                (rel.source_file, rel.target_file, rel.relation_type, json.dumps(rel.evidence, sort_keys=True))
                for rel in relations
            ],
        )
        self.conn.commit()

    def list_relations_for(self, path: str) -> list[FileRelation]:
        rows = self.conn.execute(
            """
            SELECT * FROM file_relations
            WHERE source_file = ? OR target_file = ?
            ORDER BY source_file, target_file
            """,
            (path, path),
        ).fetchall()
        return [self._relation_from_row(row) for row in rows]

    def upsert_contract(self, contract: ImplicitContract) -> None:
        self.conn.execute(
            """
            INSERT INTO implicit_contracts(name, description, pattern_regex, scope, confidence, evidence_count)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                description=excluded.description,
                pattern_regex=excluded.pattern_regex,
                scope=excluded.scope,
                confidence=excluded.confidence,
                evidence_count=excluded.evidence_count
            """,
            (
                contract.name,
                contract.description,
                contract.pattern_regex,
                contract.scope,
                contract.confidence,
                contract.evidence_count,
            ),
        )
        self.conn.commit()

    def list_contracts(self) -> list[ImplicitContract]:
        rows = self.conn.execute("SELECT * FROM implicit_contracts ORDER BY name").fetchall()
        return [self._contract_from_row(row) for row in rows]

    def save_review(self, review: PRReview) -> None:
        self.conn.execute(
            """
            INSERT INTO pr_reviews(pr_number, repo, arguments_json, verdict, confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                review.pr_number,
                review.repo,
                json.dumps(review.arguments, sort_keys=True),
                review.verdict,
                review.confidence,
                review.created_at,
            ),
        )
        self.conn.commit()

    def stats(self) -> dict[str, int]:
        return {
            "files": self._count("files"),
            "relations": self._count("file_relations"),
            "contracts": self._count("implicit_contracts"),
            "reviews": self._count("pr_reviews"),
        }

    def _count(self, table: str) -> int:
        return int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    @staticmethod
    def _file_from_row(row: sqlite3.Row) -> FileContext:
        return FileContext(
            id=row["id"],
            path=row["path"],
            summary=row["summary"],
            contracts=json.loads(row["contracts_json"]),
            patterns=json.loads(row["patterns_json"]),
            last_analyzed=row["last_analyzed"],
        )

    @staticmethod
    def _relation_from_row(row: sqlite3.Row) -> FileRelation:
        return FileRelation(
            id=row["id"],
            source_file=row["source_file"],
            target_file=row["target_file"],
            relation_type=row["relation_type"],
            evidence=json.loads(row["evidence_json"]),
        )

    @staticmethod
    def _contract_from_row(row: sqlite3.Row) -> ImplicitContract:
        return ImplicitContract(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            pattern_regex=row["pattern_regex"],
            scope=row["scope"],
            confidence=float(row["confidence"]),
            evidence_count=int(row["evidence_count"]),
        )


def load_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default
