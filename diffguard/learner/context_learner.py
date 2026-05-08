"""Codebase context learning for DiffGuard."""

from __future__ import annotations

import ast
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from diffguard.core.db import DiffGuardDB
from diffguard.core.models import FileContext, FileRelation, ImplicitContract

CODE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".rb"}
AUTH_RE = re.compile(r"\b(auth|authenticate|authorize|login_required|permission|current_user|jwt)\b", re.I)
ROUTE_RE = re.compile(r"(@app\.route|@router\.|FastAPI\(|APIRouter\(|express\.Router|route\()", re.I)
DB_RE = re.compile(r"\b(commit|rollback|transaction|atomic|session\.begin|BEGIN)\b", re.I)
DB_WRITE_RE = re.compile(r"\b(insert|update|delete|save|create|bulk_create|execute\()\b", re.I)
ERROR_RE = re.compile(r"\b(try:|except |catch \(|raise |throw )\b", re.I)
TEST_RE = re.compile(r"(^|/)(tests?|specs?)/|(_test|test_|\.spec\.)", re.I)


class CodebaseContextLearner:
    """Scans a repository and records summaries, contracts, and relations."""

    def __init__(self, db: DiffGuardDB | None = None) -> None:
        self.db = db or DiffGuardDB()

    def learn(self, repo_path: str | Path) -> dict[str, int]:
        root = Path(repo_path).resolve()
        if not root.exists():
            raise FileNotFoundError(f"Repository path does not exist: {root}")

        files = [path for path in root.rglob("*") if self._should_scan(path)]
        contexts: list[FileContext] = []
        for path in files:
            rel = path.relative_to(root).as_posix()
            text = path.read_text(encoding="utf-8", errors="ignore")
            context = self._analyze_file(rel, text)
            contexts.append(context)
            self.db.upsert_file(context)

        relations = self._build_relations(contexts, root)
        self.db.replace_relations(relations)
        for contract in self._derive_global_contracts(contexts):
            self.db.upsert_contract(contract)
        return self.db.stats()

    def _should_scan(self, path: Path) -> bool:
        if not path.is_file() or path.suffix not in CODE_EXTENSIONS:
            return False
        ignored = {".git", ".diffguard", "__pycache__", "node_modules", ".venv", "venv"}
        return not any(part in ignored for part in path.parts)

    def _analyze_file(self, path: str, text: str) -> FileContext:
        symbols = self._extract_python_symbols(text) if path.endswith(".py") else self._extract_symbols(text)
        contracts = self._extract_contracts(path, text, symbols)
        patterns = self._extract_patterns(path, text, symbols)
        summary = self._summarize(path, symbols, contracts, patterns)
        return FileContext(
            path=path,
            summary=summary,
            contracts=contracts,
            patterns=patterns,
            last_analyzed=datetime.now(UTC).isoformat(),
        )

    def _extract_python_symbols(self, text: str) -> dict[str, list[str]]:
        symbols: dict[str, list[str]] = {"functions": [], "classes": [], "imports": [], "routes": []}
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return self._extract_symbols(text)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols["functions"].append(node.name)
                if any(self._decorator_name(dec).endswith(("route", "get", "post", "put", "delete", "patch")) for dec in node.decorator_list):
                    symbols["routes"].append(node.name)
            elif isinstance(node, ast.ClassDef):
                symbols["classes"].append(node.name)
            elif isinstance(node, ast.Import):
                symbols["imports"].extend(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                symbols["imports"].append(node.module.split(".")[0])
        return symbols

    def _extract_symbols(self, text: str) -> dict[str, list[str]]:
        return {
            "functions": re.findall(r"\b(?:def|function|func)\s+([A-Za-z_][A-Za-z0-9_]*)", text),
            "classes": re.findall(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)", text),
            "imports": re.findall(r"\b(?:import|from|require)\s+[\"']?([A-Za-z_][A-Za-z0-9_./-]*)", text),
            "routes": re.findall(r"\b(?:get|post|put|delete|patch)\s*\(\s*[\"']([^\"']+)", text),
        }

    def _decorator_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Call):
            return self._decorator_name(node.func)
        if isinstance(node, ast.Attribute):
            return f"{self._decorator_name(node.value)}.{node.attr}"
        if isinstance(node, ast.Name):
            return node.id
        return ""

    def _extract_contracts(self, path: str, text: str, symbols: dict[str, list[str]]) -> list[dict[str, object]]:
        contracts: list[dict[str, object]] = []
        is_route = bool(symbols["routes"] or ROUTE_RE.search(text) or "/api/" in path)
        if is_route:
            contracts.append({"name": "api_routes_require_auth", "present": bool(AUTH_RE.search(text)), "scope": path})
        if DB_WRITE_RE.search(text):
            contracts.append({"name": "db_writes_use_transactions", "present": bool(DB_RE.search(text)), "scope": path})
        if symbols["functions"]:
            contracts.append({"name": "functions_have_error_handling", "present": bool(ERROR_RE.search(text)), "scope": path})
        if TEST_RE.search(path):
            contracts.append({"name": "test_file", "present": True, "scope": path})
        return contracts

    def _extract_patterns(self, path: str, text: str, symbols: dict[str, list[str]]) -> list[dict[str, object]]:
        return [
            {"name": "symbols", "functions": symbols["functions"], "classes": symbols["classes"], "routes": symbols["routes"]},
            {"name": "imports", "imports": symbols["imports"]},
            {"name": "concerns", "auth": bool(AUTH_RE.search(text)), "db": bool(DB_WRITE_RE.search(text)), "tests": bool(TEST_RE.search(path))},
        ]

    def _summarize(self, path: str, symbols: dict[str, list[str]], contracts: list[dict[str, object]], patterns: list[dict[str, object]]) -> str:
        parts = [f"{path}"]
        if symbols["classes"]:
            parts.append(f"classes: {', '.join(symbols['classes'][:5])}")
        if symbols["functions"]:
            parts.append(f"functions: {', '.join(symbols['functions'][:8])}")
        concerns = patterns[-1]
        active = [name for name in ("auth", "db", "tests") if concerns.get(name)]
        if active:
            parts.append(f"concerns: {', '.join(active)}")
        broken = [c["name"] for c in contracts if c.get("present") is False]
        if broken:
            parts.append(f"missing: {', '.join(broken)}")
        return "; ".join(parts)

    def _build_relations(self, contexts: list[FileContext], root: Path) -> list[FileRelation]:
        by_stem = defaultdict(list)
        for context in contexts:
            by_stem[Path(context.path).stem].append(context.path)
        relations: list[FileRelation] = []
        for context in contexts:
            imports = next((p["imports"] for p in context.patterns if p["name"] == "imports"), [])
            for imported in imports:
                for target in by_stem.get(Path(str(imported)).name, []):
                    if target != context.path:
                        relations.append(FileRelation(context.path, target, "imports", {"import": imported}))
            if not TEST_RE.search(context.path):
                stem = Path(context.path).stem
                for target in contexts:
                    if TEST_RE.search(target.path) and stem in target.summary:
                        relations.append(FileRelation(context.path, target.path, "tested_by", {"matched_stem": stem}))
        return relations

    def _derive_global_contracts(self, contexts: list[FileContext]) -> list[ImplicitContract]:
        contracts: list[ImplicitContract] = []
        grouped: dict[str, list[bool]] = defaultdict(list)
        for context in contexts:
            for contract in context.contracts:
                grouped[str(contract["name"])].append(bool(contract["present"]))
        descriptions = {
            "api_routes_require_auth": "API route files normally include an auth or permission check.",
            "db_writes_use_transactions": "Database write files normally use transaction controls.",
            "functions_have_error_handling": "Function-heavy files normally include explicit error handling.",
            "test_file": "Test files are tracked as evidence for change coverage.",
        }
        for name, values in grouped.items():
            evidence_count = len(values)
            confidence = sum(values) / evidence_count if evidence_count else 0.0
            if evidence_count >= 1:
                contracts.append(
                    ImplicitContract(
                        name=name,
                        description=descriptions.get(name, name.replace("_", " ")),
                        pattern_regex=name,
                        scope="repository",
                        confidence=confidence,
                        evidence_count=evidence_count,
                    )
                )
        return contracts


def summarize_changes_by_area(paths: list[str]) -> Counter[str]:
    areas: Counter[str] = Counter()
    for path in paths:
        lowered = path.lower()
        if "auth" in lowered or "permission" in lowered:
            areas["auth"] += 1
        if "test" in lowered or "spec" in lowered:
            areas["tests"] += 1
        if "db" in lowered or "model" in lowered or "migration" in lowered:
            areas["db"] += 1
        if "api" in lowered or "route" in lowered or "view" in lowered:
            areas["api"] += 1
    return areas
