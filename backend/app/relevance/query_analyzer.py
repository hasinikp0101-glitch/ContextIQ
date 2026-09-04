"""Turn a developer question into deterministic ranking signals.

This is not full natural-language understanding. It normalizes text,
removes stop words, detects a few phrases, looks up a fixed technical
vocabulary, and applies transparent intent rules.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .concepts import PHRASES, TECHNICAL_TERMS

STOP_WORDS = {
    "a",
    "an",
    "the",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "am",
    "my",
    "me",
    "we",
    "our",
    "you",
    "your",
    "it",
    "its",
    "this",
    "that",
    "these",
    "those",
    "to",
    "of",
    "for",
    "in",
    "on",
    "at",
    "with",
    "from",
    "as",
    "by",
    "or",
    "and",
    "but",
    "if",
    "then",
    "so",
    "do",
    "does",
    "did",
    "how",
    "what",
    "when",
    "where",
    "who",
    "why",
    "not",
    "no",
    "nor",
    "too",
    "very",
    "can",
    "could",
    "should",
    "would",
    "i",
    "im",
    "isn't",
    "isnt",
    "aren't",
    "dont",
    "don't",
    "doesn't",
    "won't",
    "can't",
    "please",
    "function",
}

# Intent labels are checked with these cue words. Primary intent is chosen
# by the rule block in QueryAnalyzer._classify_intent, not by an LLM.
INTENT_CUES: dict[str, set[str]] = {
    "debugging": {
        "why",
        "failing",
        "fail",
        "failed",
        "error",
        "exception",
        "bug",
        "broken",
        "crash",
        "issue",
        "wrong",
        "401",
        "500",
        "loading",
        "isn't",
        "isnt",
        "not",
    },
    "authentication": {
        "authentication",
        "authorization",
        "auth",
        "jwt",
        "login",
        "logout",
        "password",
        "session",
        "token",
        "401",
    },
    "performance": {
        "slow",
        "slowness",
        "latency",
        "performance",
        "timeout",
        "timeouts",
        "delay",
        "fast",
    },
    "testing": {
        "test",
        "tests",
        "testing",
        "unittest",
        "pytest",
        "spec",
        "assert",
    },
    "configuration": {
        "configuration",
        "config",
        "environment",
        "env",
        "variable",
        "dotenv",
        "settings",
    },
    "database": {
        "database",
        "databases",
        "db",
        "sql",
        "query",
        "queries",
        "mongodb",
        "postgres",
        "postgresql",
        "redis",
        "mongoose",
    },
    "api": {
        "api",
        "http",
        "endpoint",
        "route",
        "request",
        "response",
        "rest",
        "cors",
        "401",
        "500",
    },
}

ACTION_CUES: dict[str, set[str]] = {
    "diagnose": {
        "why",
        "failing",
        "fail",
        "error",
        "bug",
        "broken",
        "issue",
        "wrong",
        "401",
        "500",
    },
    "test": {"test", "tests", "testing"},
    "optimize": {"slow", "latency", "performance", "timeout"},
    "configure": {"configuration", "config", "environment", "env", "variable"},
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_MAX_TOKENS = 120


@dataclass
class QueryAnalysis:
    """Deterministic signals extracted from a developer query."""

    original_query: str
    intent: str
    keywords: list[str]
    technical_terms: list[str]
    actions: list[str]
    topics: list[str] = field(default_factory=list)
    valid: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dictionary."""
        return asdict(self)


class QueryAnalyzer:
    """Convert a natural-language query into structured ranking signals."""

    def analyze(self, query: str) -> QueryAnalysis:
        """Analyze ``query`` with vocabulary lookup and intent rules."""
        original = query if isinstance(query, str) else ""
        lowered = original.lower().replace("'", "")
        phrases = _detect_phrases(lowered)
        tokens = _tokenize(lowered)
        tokens = tokens[:_MAX_TOKENS]

        keywords = _unique(
            [token for token in tokens if token not in STOP_WORDS] + phrases
        )
        technical_terms = _unique(
            [token for token in keywords if token in TECHNICAL_TERMS] + phrases
        )

        if not original.strip() or not keywords:
            return QueryAnalysis(
                original_query=original,
                intent="general",
                keywords=[],
                technical_terms=[],
                actions=[],
                topics=[],
                valid=False,
            )

        intent, topics = self._classify_intent(tokens, keywords)
        actions = _classify_actions(tokens)
        return QueryAnalysis(
            original_query=original,
            intent=intent,
            keywords=keywords,
            technical_terms=technical_terms,
            actions=actions or ["inspect"],
            topics=topics,
            valid=True,
        )

    @staticmethod
    def _classify_intent(tokens: list[str], keywords: list[str]) -> tuple[str, list[str]]:
        """Pick one primary intent and any extra topics.

        Debugging words like "why" are cues, but a more specific topic such
        as performance or testing wins when those cues are clearly present.
        """
        haystack = set(tokens) | set(keywords)
        hits: dict[str, int] = {}
        for intent, cues in INTENT_CUES.items():
            hits[intent] = len(haystack & cues)

        debugging = hits.get("debugging", 0) > 0
        performance = hits.get("performance", 0) > 0
        testing = hits.get("testing", 0) > 0

        domain_order = (
            "authentication",
            "database",
            "api",
            "configuration",
            "performance",
            "testing",
        )
        topics = [name for name in domain_order if hits.get(name, 0) > 0]

        if testing and not debugging:
            primary = "testing"
        elif testing and _looks_like_test_question(tokens):
            primary = "testing"
        elif performance:
            primary = "performance"
        elif debugging:
            primary = "debugging"
        elif topics:
            primary = topics[0]
        else:
            primary = "general"

        extra = [name for name in topics if name != primary]
        return primary, extra


def _looks_like_test_question(tokens: list[str]) -> bool:
    return "test" in tokens or "testing" in tokens or "tests" in tokens


def _detect_phrases(text: str) -> list[str]:
    found: list[str] = []
    for phrase in sorted(PHRASES, key=len, reverse=True):
        if phrase in text:
            found.append(phrase)
    return _unique(found)


def _tokenize(text: str) -> list[str]:
    collapsed = text
    for phrase in sorted(PHRASES, key=len, reverse=True):
        collapsed = collapsed.replace(phrase, phrase.replace(" ", "_"))
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(collapsed):
        token = raw.replace("_", " ").strip() if "_" in raw else raw
        if " " in token:
            tokens.append(token)
            tokens.extend(token.split())
        else:
            tokens.append(token)
    return tokens


def _classify_actions(tokens: list[str]) -> list[str]:
    haystack = set(tokens)
    actions: list[str] = []
    for action, cues in ACTION_CUES.items():
        if haystack & cues:
            actions.append(action)
    return _unique(actions)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
