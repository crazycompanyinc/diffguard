"""Semantic diff classification beyond line comparison."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from diffguard.analyzer.diff_analyzer import DiffFileChange, parse_git_diff
from diffguard.v2.languages import MultiLanguageAnalyzer
from diffguard.v2.models import CodeSymbol, SemanticChange


class SemanticDiffEngine:
    """Classifies the meaning of each file change."""

    def __init__(self, language_analyzer: MultiLanguageAnalyzer | None = None) -> None:
        self.language_analyzer = language_analyzer or MultiLanguageAnalyzer()

    def analyze(self, diff_text: str) -> list[SemanticChange]:
        changes: list[SemanticChange] = []
        for file_change in parse_git_diff(diff_text):
            changes.extend(self._classify_file(file_change))
        return changes

    def _classify_file(self, change: DiffFileChange) -> list[SemanticChange]:
        added_text = "\n".join(change.added)
        removed_text = "\n".join(change.removed)
        added_profile = self.language_analyzer.analyze_path(change.path, added_text)
        removed_profile = self.language_analyzer.analyze_path(change.path, removed_text)
        additions = {symbol.name: symbol for symbol in added_profile.symbols}
        removals = {symbol.name: symbol for symbol in removed_profile.symbols}
        semantic: list[SemanticChange] = []

        semantic.extend(self._renames(change.path, list(removals.values()), list(additions.values())))
        for name in sorted(additions.keys() & removals.keys()):
            before = removals[name]
            after = additions[name]
            if _signature_shape(before.signature) != _signature_shape(after.signature):
                semantic.append(SemanticChange("signature_change", change.path, "high", f"{name} changes callable signature.", {"before": before.signature, "after": after.signature}))
            if (before.return_type or "") != (after.return_type or "") and (before.return_type or after.return_type):
                semantic.append(SemanticChange("return_type_change", change.path, "high", f"{name} changes return type.", {"before": before.return_type, "after": after.return_type}))

        for name in sorted(additions.keys() - removals.keys()):
            symbol = additions[name]
            semantic.append(SemanticChange("symbol_added", change.path, "medium" if symbol.kind == "function" else "low", f"Adds {symbol.kind} {name}.", {"signature": symbol.signature, "line": symbol.line}))
        for name in sorted(removals.keys() - additions.keys()):
            symbol = removals[name]
            semantic.append(SemanticChange("symbol_removed", change.path, "high", f"Removes {symbol.kind} {name}.", {"signature": symbol.signature, "line": symbol.line}))

        if _business_logic_changed(added_text, removed_text):
            semantic.append(SemanticChange("business_logic_change", change.path, "medium", "Changes conditions, persistence, or returned behavior.", {"added_keywords": _logic_hits(added_text), "removed_keywords": _logic_hits(removed_text)}))
        if _only_comments_or_docs(added_text, removed_text):
            semantic.append(SemanticChange("documentation_change", change.path, "low", "Only comments or documentation-like lines changed.", {}))
        return _dedupe_changes(semantic)

    def _renames(self, path: str, removed: list[CodeSymbol], added: list[CodeSymbol]) -> list[SemanticChange]:
        changes: list[SemanticChange] = []
        for old in removed:
            for new in added:
                if old.kind == new.kind and old.name != new.name and _parameter_shape(old.signature) == _parameter_shape(new.signature):
                    ratio = SequenceMatcher(None, old.name.lower(), new.name.lower()).ratio()
                    if ratio >= 0.45:
                        changes.append(SemanticChange("symbol_rename", path, "medium", f"Renames {old.kind} {old.name} to {new.name}.", {"before": old.signature, "after": new.signature, "similarity": round(ratio, 3)}))
                        if (old.return_type or "") != (new.return_type or "") and (old.return_type or new.return_type):
                            changes.append(SemanticChange("return_type_change", path, "high", f"{old.name} changes return type while being renamed to {new.name}.", {"before": old.return_type, "after": new.return_type, "old_name": old.name, "new_name": new.name}))
        return changes


def _signature_shape(signature: str) -> str:
    normalized = re.sub(r"\b[A-Za-z_$][\w$]*\b", "id", signature)
    return re.sub(r"\s+", "", normalized)


def _parameter_shape(signature: str) -> str:
    match = re.search(r"\(([^)]*)\)", signature)
    if not match:
        return _signature_shape(signature)
    params = re.sub(r"\b[A-Za-z_$][\w$]*\b", "id", match.group(1))
    return re.sub(r"\s+", "", params)


def _logic_hits(text: str) -> list[str]:
    hits = re.findall(r"\b(if|else|for|while|return|yield|raise|throw|catch|rescue|insert|update|delete|save|permission|auth|price|total|limit)\b", text, re.I)
    return sorted(set(hit.lower() for hit in hits))


def _business_logic_changed(added_text: str, removed_text: str) -> bool:
    return bool(_logic_hits(added_text) or _logic_hits(removed_text)) and not _only_comments_or_docs(added_text, removed_text)


def _only_comments_or_docs(added_text: str, removed_text: str) -> bool:
    lines = [line.strip() for line in (added_text + "\n" + removed_text).splitlines() if line.strip()]
    if not lines:
        return False
    return all(line.startswith(("#", "//", "/*", "*", "--")) or line.lower().startswith(("readme", "docs")) for line in lines)


def _dedupe_changes(changes: list[SemanticChange]) -> list[SemanticChange]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[SemanticChange] = []
    for change in changes:
        key = (change.type, change.path, change.summary)
        if key not in seen:
            seen.add(key)
            unique.append(change)
    return unique
