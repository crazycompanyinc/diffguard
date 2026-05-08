"""Heuristic intent-to-diff matching."""

from __future__ import annotations

import re
from dataclasses import dataclass

STOPWORDS = {
    "a", "an", "and", "the", "to", "of", "in", "for", "with", "on", "by", "this", "that",
    "fix", "update", "change", "add", "remove", "refactor", "pr", "pull", "request",
}
LOGIC_WORDS = {"if", "else", "return", "raise", "except", "try", "while", "for", "class", "def", "auth", "permission", "transaction"}
COSMETIC_WORDS = {"typo", "comment", "docs", "documentation", "readme", "format", "style", "lint"}


@dataclass
class IntentMatch:
    intent_keywords: set[str]
    diff_keywords: set[str]
    overlap: set[str]
    score: float
    mismatches: list[str]
    changed_symbols: list[str]
    risk_level: str


class IntentMatcher:
    """Compares stated intent with diff content using transparent heuristics."""

    def match(self, intent: str, diff_text: str) -> IntentMatch:
        intent_keywords = extract_keywords(intent)
        diff_keywords = extract_keywords(diff_text)
        changed_symbols = extract_changed_symbols(diff_text)
        overlap = intent_keywords & diff_keywords
        denominator = max(1, len(intent_keywords | set(changed_symbols[:10])))
        score = min(1.0, (len(overlap) + len(set(changed_symbols) & intent_keywords)) / denominator)
        mismatches = self._mismatches(intent, diff_text, changed_symbols, intent_keywords, diff_keywords)
        risk_level = "high" if len(mismatches) >= 2 else "medium" if mismatches else "low"
        return IntentMatch(intent_keywords, diff_keywords, overlap, score, mismatches, changed_symbols, risk_level)

    def _mismatches(
        self,
        intent: str,
        diff_text: str,
        changed_symbols: list[str],
        intent_keywords: set[str],
        diff_keywords: set[str],
    ) -> list[str]:
        lowered_intent = intent.lower()
        added_removed = "\n".join(line for line in diff_text.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---")))
        mismatches: list[str] = []
        if intent_keywords & COSMETIC_WORDS and (diff_keywords & LOGIC_WORDS or changed_symbols):
            mismatches.append("Intent sounds cosmetic, but the diff changes executable logic or symbols.")
        if any(word in lowered_intent for word in ("test", "spec")) and not re.search(r"(^diff --git .*test|/test|_test|test_)", diff_text, re.I | re.M):
            mismatches.append("Intent mentions tests, but no obvious test files changed.")
        if re.search(r"\b(auth|permission|login|token|jwt)\b", added_removed, re.I) and not re.search(r"\b(auth|permission|login|token|jwt)\b", lowered_intent):
            mismatches.append("Diff touches authentication or permission behavior that the intent does not mention.")
        if re.search(r"\b(delete|drop|remove|deactivate)\b", added_removed, re.I) and not re.search(r"\b(delete|drop|remove|deactivate)\b", lowered_intent):
            mismatches.append("Diff removes behavior or data paths that the intent does not disclose.")
        if not (intent_keywords & diff_keywords) and len(diff_keywords) > 5:
            mismatches.append("Intent keywords have little overlap with the changed code.")
        return mismatches


def extract_keywords(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text)
    split_words: list[str] = []
    for word in words:
        split_words.extend(re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|[0-9]+", word.replace("_", " ")))
    return {w.lower() for w in words + split_words if w.lower() not in STOPWORDS and len(w) > 2}


def extract_changed_symbols(diff_text: str) -> list[str]:
    symbols: list[str] = []
    for line in diff_text.splitlines():
        if not line.startswith(("+", "-")) or line.startswith(("+++", "---")):
            continue
        symbols.extend(re.findall(r"\b(?:def|class|function|const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)", line))
        symbols.extend(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", line))
    seen: set[str] = set()
    return [symbol for symbol in symbols if not (symbol in seen or seen.add(symbol))]
