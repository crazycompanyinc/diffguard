"""Language-aware structural analysis for DiffGuard v2."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from diffguard.v2.models import CodeSymbol, LanguageProfile

LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".java": "java",
    ".rb": "ruby",
    ".rs": "rust",
}

AUTH_RE = re.compile(r"\b(auth|authenticate|authorize|permission|current_user|jwt|rbac|csrf|login_required)\b", re.I)
ROUTE_RE = re.compile(r"(@\w+\.(get|post|put|patch|delete)|app\.(get|post|put|patch|delete)|router\.(get|post|put|patch|delete)|@RequestMapping|@GetMapping|route\s+|\.routes\.draw|actix_web|warp::path)", re.I)
DB_WRITE_RE = re.compile(r"\b(insert|update|delete|save|create|execute|exec|query|select|persist|remove|repository\.save)\b", re.I)
TX_RE = re.compile(r"\b(transaction|atomic|commit|rollback|session\.begin|BEGIN|@Transactional|db\.Transaction|tx\.|ActiveRecord::Base\.transaction)\b", re.I)
ERROR_RE = re.compile(r"\b(try|catch|except|rescue|Result<|Option<|throws|panic!|raise|throw)\b", re.I)


class MultiLanguageAnalyzer:
    """Extracts symbols and contracts across supported languages.

    Python uses the built-in AST. Other languages use deterministic structural
    parsers keyed to declarations, signatures, imports, routes, and contracts;
    they avoid external parser dependencies while still analyzing syntax-level
    constructs rather than raw line counts.
    """

    def analyze_path(self, path: str | Path, text: str) -> LanguageProfile:
        path_str = str(path)
        language = self.detect_language(path_str)
        symbols = self._python_symbols(text) if language == "python" else self._structural_symbols(language, text)
        imports = self._imports(language, text)
        concerns = self._concerns(path_str, text)
        contracts = self._contracts(path_str, language, text, symbols)
        return LanguageProfile(language, path_str, tuple(symbols), tuple(imports), tuple(contracts), tuple(concerns))

    def detect_language(self, path: str) -> str:
        return LANGUAGE_BY_SUFFIX.get(Path(path).suffix.lower(), "unknown")

    def _python_symbols(self, text: str) -> list[CodeSymbol]:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return self._structural_symbols("python", text)
        symbols: list[CodeSymbol] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                returns = ast.unparse(node.returns) if node.returns is not None else None
                args = ", ".join(arg.arg for arg in node.args.args)
                decorators = tuple(self._decorator_name(dec) for dec in node.decorator_list)
                symbols.append(CodeSymbol(node.name, "function", f"{node.name}({args})", returns, None, decorators, node.lineno))
            elif isinstance(node, ast.ClassDef):
                symbols.append(CodeSymbol(node.name, "class", f"class {node.name}", None, None, (), node.lineno))
        return symbols

    def _decorator_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Call):
            return self._decorator_name(node.func)
        if isinstance(node, ast.Attribute):
            return f"{self._decorator_name(node.value)}.{node.attr}"
        if isinstance(node, ast.Name):
            return node.id
        return ""

    def _structural_symbols(self, language: str, text: str) -> list[CodeSymbol]:
        patterns = [
            ("function", re.compile(r"\b(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*(?::\s*([A-Za-z_$][\w$<>,\[\]\s|.?]*))?", re.M)),
            ("function", re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*(?::\s*([A-Za-z_$][\w$<>,\[\]\s|.?]*))?\s*=>", re.M)),
            ("function", re.compile(r"\bfunc\s+(?:\([^)]+\)\s*)?([A-Za-z_]\w*)\s*\(([^)]*)\)\s*([A-Za-z_][\w.\[\]*]*)?", re.M)),
            ("function", re.compile(r"\b(?:public|private|protected|static|\s)+\s*([A-Za-z_][\w<>\[\]]+)\s+([A-Za-z_]\w*)\s*\(([^)]*)\)", re.M)),
            ("function", re.compile(r"\bdef\s+([A-Za-z_]\w*)\s*(?:\(([^)]*)\))?", re.M)),
            ("function", re.compile(r"\b(?:pub\s+)?fn\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*(?:->\s*([A-Za-z_][\w:<>,\s]*))?", re.M)),
            ("class", re.compile(r"\b(?:export\s+)?class\s+([A-Za-z_]\w*)", re.M)),
            ("class", re.compile(r"\b(?:public\s+)?(?:class|interface|enum)\s+([A-Za-z_]\w*)", re.M)),
            ("class", re.compile(r"\b(?:struct|enum|trait)\s+([A-Za-z_]\w*)", re.M)),
        ]
        symbols: list[CodeSymbol] = []
        for kind, pattern in patterns:
            for match in pattern.finditer(text):
                if kind == "class":
                    name = match.group(1)
                    signature = match.group(0).strip()
                    return_type = None
                elif language == "java" and len(match.groups()) >= 3 and match.group(2):
                    return_type = match.group(1)
                    name = match.group(2)
                    signature = match.group(0).strip()
                else:
                    name = match.group(1)
                    signature = match.group(0).strip()
                    return_type = match.group(3).strip() if len(match.groups()) >= 3 and match.group(3) else None
                symbols.append(CodeSymbol(name, kind, signature, return_type, _visibility(signature), (), _line_number(text, match.start())))
        return _dedupe_symbols(symbols)

    def _imports(self, language: str, text: str) -> list[str]:
        patterns = [
            r"\bimport\s+(?:static\s+)?([A-Za-z_][\w./:-]*)",
            r"\bfrom\s+([A-Za-z_][\w./-]*)\s+import\b",
            r"\brequire\([\"']([^\"']+)[\"']\)",
            r"\buse\s+([A-Za-z_][\w:]*);",
            r"\bimport\s+[\"']([^\"']+)[\"']",
        ]
        imports: list[str] = []
        for pattern in patterns:
            imports.extend(re.findall(pattern, text))
        return sorted(set(imports))

    def _concerns(self, path: str, text: str) -> list[str]:
        concerns: list[str] = []
        lowered = f"{path}\n{text}".lower()
        for name, regex in {"auth": AUTH_RE, "route": ROUTE_RE, "db": DB_WRITE_RE, "transaction": TX_RE, "error_handling": ERROR_RE}.items():
            if regex.search(lowered):
                concerns.append(name)
        if re.search(r"(^|/)(tests?|specs?)/|(_test|test_|\.spec\.|\.test\.)", path, re.I):
            concerns.append("test")
        if re.search(r"\b(password|secret|token|credential|ssn|email)\b", lowered):
            concerns.append("sensitive_data")
        return concerns

    def _contracts(self, path: str, language: str, text: str, symbols: list[CodeSymbol]) -> list[dict[str, object]]:
        contracts: list[dict[str, object]] = []
        if ROUTE_RE.search(text) or "/api/" in path:
            contracts.append({"name": "route_requires_auth", "present": bool(AUTH_RE.search(text)), "language": language, "scope": path})
        if DB_WRITE_RE.search(text):
            contracts.append({"name": "db_writes_are_transactional", "present": bool(TX_RE.search(text)), "language": language, "scope": path})
        if symbols:
            contracts.append({"name": "functions_have_error_paths", "present": bool(ERROR_RE.search(text)), "language": language, "scope": path})
        if "sensitive_data" in self._concerns(path, text):
            contracts.append({"name": "sensitive_data_is_guarded", "present": bool(AUTH_RE.search(text)), "language": language, "scope": path})
        return contracts


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _visibility(signature: str) -> str | None:
    match = re.search(r"\b(public|private|protected|pub)\b", signature)
    return match.group(1) if match else None


def _dedupe_symbols(symbols: list[CodeSymbol]) -> list[CodeSymbol]:
    seen: set[tuple[str, str, int]] = set()
    unique: list[CodeSymbol] = []
    for symbol in symbols:
        key = (symbol.name, symbol.kind, symbol.line)
        if key not in seen:
            seen.add(key)
            unique.append(symbol)
    return unique
