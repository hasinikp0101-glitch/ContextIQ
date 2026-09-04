"""Weighted, explainable relevance ranking over Code Analyzer metadata.

The scorer never executes code and never calls an LLM. Each file gets five
normalized signal scores (0-100) that are combined with fixed weights,
followed by a small developer-aware file-role adjustment.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from app.analyzer.code_parser import FileAnalysis

from .concepts import DOMAIN_TOKENS, related_tokens
from .query_analyzer import QueryAnalysis, QueryAnalyzer

# Transparent weights. They sum to 1.0.
WEIGHT_PATH = 0.25
WEIGHT_IMPORTS = 0.25
WEIGHT_SYMBOLS = 0.20
WEIGHT_QUERY_TERMS = 0.20
WEIGHT_INTENT = 0.10

_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".json"}

_IMPLEMENTATION_PATH_MARKERS = {
    "app",
    "src",
    "lib",
    "core",
    "service",
    "services",
    "api",
    "backend",
}

_TEST_PATH_MARKERS = {
    "test",
    "tests",
    "__tests__",
    "spec",
}

# Queries that normally ask about implementation/debugging rather than
# testing behavior. These are deliberately explicit and deterministic.
_IMPLEMENTATION_INTENTS = {
    "debugging",
    "implementation",
    "architecture",
    "explanation",
    "code",
}


@dataclass
class RankedFile:
    """One file's relevance score plus the evidence behind it."""

    path: str
    score: int
    signal_scores: dict[str, int]
    matched_signals: list[str]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dictionary for later UI display."""
        return asdict(self)


class RelevanceScorer:
    """Score FileAnalysis objects against a QueryAnalysis."""

    def __init__(self, query_analyzer: QueryAnalyzer | None = None) -> None:
        self.query_analyzer = query_analyzer or QueryAnalyzer()

    def rank(
        self,
        query: str | QueryAnalysis,
        files: Iterable[FileAnalysis | dict[str, Any]],
    ) -> list[RankedFile]:
        """Score every file and return a stable descending ranking."""
        analysis = self._as_query(query)
        ranked = [self.score_file(analysis, item) for item in files]
        ranked.sort(
            key=lambda item: (-item.score, -len(item.matched_signals), item.path),
        )
        return ranked

    def score_file(
        self,
        query: str | QueryAnalysis,
        file_analysis: FileAnalysis | dict[str, Any],
    ) -> RankedFile:
        """Score a single file. Incomplete metadata is treated as empty."""
        analysis = self._as_query(query)
        file_data = _as_file(file_analysis)
        path = file_data["path"] or ""

        if not analysis.valid:
            return RankedFile(
                path=path,
                score=0,
                signal_scores={
                    "path": 0,
                    "imports": 0,
                    "symbols": 0,
                    "query_terms": 0,
                    "intent": 0,
                },
                matched_signals=[],
                reason="Query is empty or has no usable terms",
            )

        query_terms = _unique(analysis.keywords + analysis.technical_terms)
        path_tokens = _path_tokens(path)
        import_tokens = _import_tokens(file_data["imports"])
        symbol_tokens, symbol_names = _symbol_tokens(
            file_data["functions"],
            file_data["classes"],
            file_data["symbols"],
            file_data["exports"],
        )

        path_score, path_hits = _coverage_score(query_terms, path_tokens)
        import_score, import_hits = _coverage_score(query_terms, import_tokens)
        symbol_score, symbol_hits = _coverage_score(query_terms, symbol_tokens)
        query_score, query_hits = _coverage_score(
            query_terms,
            path_tokens | import_tokens | symbol_tokens,
        )
        intent_score, intent_hits = _intent_score(
            analysis,
            path_tokens | import_tokens | symbol_tokens,
        )

        path_score = _filename_boost(path_score, query_terms, path)

        final = _weighted_total(
            path_score,
            import_score,
            symbol_score,
            query_score,
            intent_score,
        )

        # Developer-aware role adjustment.
        role_adjustment, role_signal = _file_role_adjustment(
            path=path,
            intent=analysis.intent,
            query_terms=query_terms,
        )

        final = max(0, min(100, final + role_adjustment))

        matched = _build_matched_signals(
            path=path,
            path_tokens=path_tokens,
            path_hits=path_hits,
            import_hits=import_hits,
            import_values=file_data["imports"],
            symbol_hits=symbol_hits,
            symbol_names=symbol_names,
            query_hits=query_hits,
            intent_hits=intent_hits,
            intent=analysis.intent,
        )

        if role_signal:
            matched.append(role_signal)

        reason = _reason(
            matched,
            final,
            analysis.intent,
            role_adjustment,
        )

        if file_data["analysis_error"]:
            matched.append(
                "code analysis reported an error; scored from available metadata"
            )

        return RankedFile(
            path=path,
            score=final,
            signal_scores={
                "path": path_score,
                "imports": import_score,
                "symbols": symbol_score,
                "query_terms": query_score,
                "intent": intent_score,
            },
            matched_signals=matched,
            reason=reason,
        )

    def _as_query(self, query: str | QueryAnalysis) -> QueryAnalysis:
        if isinstance(query, QueryAnalysis):
            return query
        return self.query_analyzer.analyze(query)


def _as_file(file_analysis: FileAnalysis | dict[str, Any]) -> dict[str, Any]:
    if isinstance(file_analysis, FileAnalysis):
        data = file_analysis.to_dict()
    elif isinstance(file_analysis, dict):
        data = dict(file_analysis)
    else:
        data = {}

    return {
        "path": str(data.get("path") or ""),
        "imports": list(data.get("imports") or []),
        "functions": list(data.get("functions") or []),
        "classes": list(data.get("classes") or []),
        "symbols": list(data.get("symbols") or []),
        "exports": list(data.get("exports") or []),
        "analysis_error": data.get("analysis_error"),
        "language": data.get("language") or "unknown",
        "analysis_supported": bool(data.get("analysis_supported", False)),
    }


def _weighted_total(
    path_score: int,
    import_score: int,
    symbol_score: int,
    query_score: int,
    intent_score: int,
) -> int:
    total = (
        path_score * WEIGHT_PATH
        + import_score * WEIGHT_IMPORTS
        + symbol_score * WEIGHT_SYMBOLS
        + query_score * WEIGHT_QUERY_TERMS
        + intent_score * WEIGHT_INTENT
    )

    return max(0, min(100, int(round(total))))


def _coverage_score(
    query_terms: list[str],
    candidates: set[str],
) -> tuple[int, list[str]]:
    """Share of query terms that match candidate tokens, counting each term once."""
    if not query_terms:
        return 0, []

    hits: list[str] = []

    for term in query_terms:
        if _term_matches(term, candidates):
            hits.append(term)

    score = int(round(100.0 * len(hits) / len(query_terms)))

    return max(0, min(100, score)), hits


def _term_matches(term: str, candidates: set[str]) -> bool:
    """Match a query term to candidate tokens without naive substrings.

    A hit is an exact token, a concept-map neighbor (JWT → jsonwebtoken),
    or a multi-word phrase whose words all appear as exact tokens.
    """
    normalized = term.lower().strip()

    if not normalized or not candidates:
        return False

    lowered = {item.lower() for item in candidates}

    if " " in normalized:
        if normalized in lowered:
            return True

        words = [word for word in normalized.split() if word]

        if words and all(
            _exact_or_related(word, lowered)
            for word in words
        ):
            return True

    return _exact_or_related(normalized, lowered)


def _exact_or_related(
    term: str,
    candidates: set[str],
) -> bool:
    """True when the term or a concept-map relative equals a candidate token."""
    needles = {
        token.lower()
        for token in related_tokens(term)
        if len(token) >= 2
    }

    needles.add(term.lower())

    return bool(needles & candidates)


def _intent_score(
    analysis: QueryAnalysis,
    candidates: set[str],
) -> tuple[int, list[str]]:
    domains = [analysis.intent, *analysis.topics]

    wanted: set[str] = set()

    for domain in domains:
        wanted |= {
            token.lower()
            for token in DOMAIN_TOKENS.get(domain, set())
        }

    if not wanted:
        return 0, []

    hits = sorted(
        token
        for token in wanted
        if token in candidates or _term_matches(token, candidates)
    )

    if not hits:
        return 0, []

    score = max(
        0,
        min(100, 40 + 20 * min(len(hits), 3)),
    )

    return score, hits[:8]


def _filename_boost(
    path_score: int,
    query_terms: list[str],
    path: str,
) -> int:
    stem = Path(path).stem.lower()

    if not stem:
        return path_score

    stem_tokens = {
        stem,
        *_split_identifier(stem),
    }

    for term in query_terms:
        if _term_matches(term, stem_tokens):
            return max(
                path_score,
                min(100, path_score + 25),
            )

    return path_score


def _file_role_adjustment(
    path: str,
    intent: str,
    query_terms: list[str],
) -> tuple[int, str | None]:
    """Apply a small deterministic adjustment based on developer file role.

    Implementation files receive a modest boost for implementation/debugging
    questions. Test files receive a modest penalty in those cases.

    Explicit test-related queries do not receive the penalty.
    """
    components = _path_components(path)

    is_test = _is_test_path(components)
    is_implementation = _is_implementation_path(components)

    test_query = _is_test_query(query_terms)

    if test_query:
        if is_test:
            return 8, "file is test-focused and matches a test-related query"
        return 0, None

    if intent not in _IMPLEMENTATION_INTENTS:
        return 0, None

    if is_implementation and not is_test:
        return 8, "implementation file prioritized for developer query"

    if is_test:
        return -8, "test file deprioritized for implementation-focused query"

    return 0, None


def _path_components(path: str) -> set[str]:
    """Return normalized path components without file extensions."""
    normalized = path.replace("\\", "/")

    components: set[str] = set()

    for piece in normalized.split("/"):
        if not piece:
            continue

        suffix = Path(piece).suffix.lower()

        if suffix:
            piece = Path(piece).stem

        components.update(
            token.lower()
            for token in _split_identifier(piece)
            if token
        )

    return components


def _is_test_path(components: set[str]) -> bool:
    """Return True when a path clearly belongs to test/spec infrastructure."""
    return bool(components & _TEST_PATH_MARKERS)


def _is_implementation_path(components: set[str]) -> bool:
    """Return True when a path clearly belongs to application code."""
    return bool(components & _IMPLEMENTATION_PATH_MARKERS)


def _is_test_query(query_terms: list[str]) -> bool:
    """Detect explicit test-oriented queries."""
    test_terms = {
        "test",
        "tests",
        "testing",
        "pytest",
        "unittest",
        "spec",
        "specs",
        "coverage",
        "assertion",
        "assertions",
        "fixture",
        "fixtures",
    }

    return any(
        term.lower() in test_terms
        for term in query_terms
    )


def _path_tokens(path: str) -> set[str]:
    normalized = path.replace("\\", "/")

    parts: list[str] = []

    for piece in normalized.split("/"):
        suffix = Path(piece).suffix.lower()

        stem = (
            Path(piece).stem
            if suffix in _EXTENSIONS
            else piece
        )

        parts.extend(_split_identifier(stem))

        if suffix == ".sql":
            parts.append("sql")

    return {
        part
        for part in parts
        if part and len(part) > 1
    }


def _import_tokens(imports: list[str]) -> set[str]:
    tokens: set[str] = set()

    for item in imports:
        raw = str(item).replace("\\", "/").lower()

        tokens.add(raw)

        name = raw.rsplit("/", 1)[-1]
        name = name.rsplit(".", 1)[0]

        tokens.update(_split_identifier(name))

        tokens.update(
            _split_identifier(
                raw.replace(".", " ").replace("/", " ")
            )
        )

    return {
        token
        for token in tokens
        if token and len(token) > 1
    }


def _symbol_tokens(
    functions: list[str],
    classes: list[str],
    symbols: list[str],
    exports: list[str],
) -> tuple[set[str], list[str]]:
    names = _unique(
        [
            str(item)
            for item in functions
            + classes
            + symbols
            + exports
        ]
    )

    tokens: set[str] = set()

    for name in names:
        tokens.add(name.lower())
        tokens.update(_split_identifier(name))

    return {
        token
        for token in tokens
        if token and len(token) > 1
    }, names


def _split_identifier(name: str) -> list[str]:
    cleaned = (
        name
        .replace("-", " ")
        .replace("_", " ")
        .replace(".", " ")
    )

    pieces: list[str] = []

    for chunk in cleaned.split():
        parts = re.findall(
            r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+",
            chunk,
        )

        if parts:
            pieces.extend(
                part.lower()
                for part in parts
            )
        else:
            pieces.append(chunk.lower())

    return [
        piece
        for piece in pieces
        if piece
    ]


def _build_matched_signals(
    path: str,
    path_tokens: set[str],
    path_hits: list[str],
    import_hits: list[str],
    import_values: list[str],
    symbol_hits: list[str],
    symbol_names: list[str],
    query_hits: list[str],
    intent_hits: list[str],
    intent: str,
) -> list[str]:
    evidence: list[str] = []

    posix = path.replace("\\", "/")

    for term in path_hits:
        for part in posix.split("/"):
            part_tokens = _path_tokens(part)

            if _term_matches(term, part_tokens):
                evidence.append(
                    f"path contains '{part}'"
                )
                break
        else:
            evidence.append(
                f"path matches query term '{term}'"
            )

    for term in import_hits:
        matched_import = _best_import(
            term,
            import_values,
        )

        if matched_import:
            evidence.append(
                f"imports '{matched_import}'"
            )
        else:
            evidence.append(
                f"import metadata matches '{term}'"
            )

    for term in symbol_hits:
        matched_symbol = _best_symbol(
            term,
            symbol_names,
        )

        if matched_symbol:
            evidence.append(
                f"symbol '{matched_symbol}' matches {term} concept"
            )
        else:
            evidence.append(
                f"symbol metadata matches '{term}'"
            )

    for token in intent_hits:
        evidence.append(
            f"intent '{intent}' supported by token '{token}'"
        )

    covered = " ".join(evidence).lower()

    for term in query_hits:
        if term not in covered:
            evidence.append(
                f"query term '{term}' appears in file metadata"
            )

    return _unique(evidence)


def _best_import(
    term: str,
    imports: list[str],
) -> str | None:
    for item in imports:
        if _term_matches(
            term,
            _import_tokens([item]),
        ):
            return str(item)

    return None


def _best_symbol(
    term: str,
    names: list[str],
) -> str | None:
    for name in names:
        pieces = {
            name.lower(),
            *_split_identifier(name),
        }

        if _term_matches(term, pieces):
            return name

    return None


def _reason(
    matched: list[str],
    score: int,
    intent: str,
    role_adjustment: int = 0,
) -> str:
    if not matched:
        return f"Little structural overlap with the {intent} query"

    if score >= 70:
        base = f"Strong structural match for {intent}"
    elif score >= 40:
        base = f"Partial structural match for {intent}"
    else:
        base = f"Weak structural match for {intent}"

    if role_adjustment > 0:
        return f"{base}; implementation role prioritized"

    if role_adjustment < 0:
        return f"{base}; test role deprioritized"

    return base


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)

    return result