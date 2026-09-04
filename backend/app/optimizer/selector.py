"""Select the highest-ranked files that fit a token budget.

This layer does not score relevance. It consumes already-ranked
``RankedFile`` results, reads file contents safely, estimates tokens with
tiktoken when available, and greedily packs files without exceeding the
budget.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from app.relevance.scorer import RankedFile

DEFAULT_MAX_READ_BYTES = 1_048_576
_BINARY_PROBE_BYTES = 8192
_DEFAULT_ENCODING_NAME = "cl100k_base"

_SENSITIVE_FILENAMES = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    ".env.test",
}

@dataclass
class SelectedFile:
    """One file chosen for the assembled context."""

    path: str
    relevance_score: int
    token_count: int
    selection_order: int
    content: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dictionary."""
        return asdict(self)


@dataclass
class ExcludedFile:
    """One candidate that was not selected, with a reason."""

    path: str
    relevance_score: int
    token_count: int | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dictionary."""
        return asdict(self)


@dataclass
class SelectionResult:
    """Greedy selection outcome for one token budget."""

    token_budget: int
    total_candidate_files: int
    selected_files: list[SelectedFile] = field(default_factory=list)
    excluded_files: list[ExcludedFile] = field(default_factory=list)
    selected_tokens: int = 0
    remaining_tokens: int = 0
    context: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dictionary."""
        return asdict(self)


class ContextSelector:
    """Greedily pack ranked files into a token budget.

    Candidates are evaluated in the given relevance order. A file that
    does not fit is skipped; later smaller files may still be selected.
    """

    def __init__(
        self,
        encoding_name: str = _DEFAULT_ENCODING_NAME,
        max_read_bytes: int = DEFAULT_MAX_READ_BYTES,
        count_tokens: Callable[[str], int] | None = None,
    ) -> None:
        """Create a selector.

        Args:
            encoding_name: tiktoken encoding used when no custom counter
                is supplied (``cl100k_base`` by default).
            max_read_bytes: Maximum bytes to read from one file.
            count_tokens: Optional token counter. Tests may pass this;
                production uses tiktoken.
        """
        self.encoding_name = encoding_name
        self.max_read_bytes = max_read_bytes
        self._count_tokens = count_tokens or _TiktokenCounter(encoding_name)

    def count_tokens(self, text: str) -> int:
        """Return the token count for ``text`` using this selector's tokenizer."""
        return int(self._count_tokens(text))

    def select(
        self,
        project_root: str | Path,
        ranked_files: Iterable[RankedFile | dict[str, Any]],
        token_budget: int,
    ) -> SelectionResult:
        """Select files that fit ``token_budget`` in relevance order."""
        budget = _normalized_budget(token_budget)
        candidates = list(ranked_files)
        root = Path(project_root).expanduser().resolve()

        selected: list[SelectedFile] = []
        excluded: list[ExcludedFile] = []
        used = 0

        for candidate in candidates:
            path, score = _candidate_fields(candidate)
            if score <= 0:
                excluded.append(
                    ExcludedFile(
                        path=path,
                        relevance_score=score,
                        token_count=None,
                        reason="no relevance to query",
                    )
                )
                continue
            loaded = self._load_candidate(root, path)

            if loaded.error is not None:
                excluded.append(
                    ExcludedFile(
                        path=path,
                        relevance_score=score,
                        token_count=loaded.token_count,
                        reason=loaded.error,
                    )
                )
                continue

            token_count = loaded.token_count or 0
            remaining = budget - used
            if token_count > remaining:
                excluded.append(
                    ExcludedFile(
                        path=path,
                        relevance_score=score,
                        token_count=token_count,
                        reason="exceeds token budget",
                    )
                )
                continue

            used += token_count
            selected.append(
                SelectedFile(
                    path=path,
                    relevance_score=score,
                    token_count=token_count,
                    selection_order=len(selected) + 1,
                    content=loaded.content or "",
                )
            )

        remaining_tokens = max(0, budget - used)
        return SelectionResult(
            token_budget=budget,
            total_candidate_files=len(candidates),
            selected_files=selected,
            excluded_files=excluded,
            selected_tokens=used,
            remaining_tokens=remaining_tokens,
            context=_assemble_context(selected),
        )

    def _load_candidate(self, project_root: Path, relative_path: str) -> _LoadedFile:
        target = _safe_resolve(project_root, relative_path)
        if target is None:
            return _LoadedFile(error="path is outside the project root or is invalid")

        if target.name.lower() in _SENSITIVE_FILENAMES:
            return _LoadedFile(error="sensitive file was not selected")

        if not target.exists() or not target.is_file():
            return _LoadedFile(error="file not found or is not a regular file")

        try:
            if target.stat().st_size > self.max_read_bytes:
                return _LoadedFile(error="file exceeds selector read size limit")
            raw = target.read_bytes()
        except OSError as exc:
            return _LoadedFile(error=f"file is unreadable: {exc}")

        if b"\x00" in raw[:_BINARY_PROBE_BYTES]:
            return _LoadedFile(error="file looks binary and was not selected")

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return _LoadedFile(error="file is not valid UTF-8 text")

        text = text.replace("\r\n", "\n").replace("\r", "\n")

        try:
            token_count = self.count_tokens(text)
        except Exception as exc:  # noqa: BLE001 - tokenizer backends vary
            return _LoadedFile(
                content=text,
                token_count=None,
                error=f"tokenization error: {exc}",
            )

        if token_count < 0:
            return _LoadedFile(
                content=text,
                token_count=None,
                error="tokenization error: negative token count",
            )

        return _LoadedFile(content=text, token_count=token_count)


@dataclass
class _LoadedFile:
    content: str | None = None
    token_count: int | None = None
    error: str | None = None


def _fallback_token_count(text: str) -> int:
    """Deterministic token estimate: ceil(chars / 4)."""
    if not text:
        return 0
    return (len(text) + 3) // 4


class _TiktokenCounter:
    """Count tokens with tiktoken, loading the encoding on first use."""

    def __init__(self, encoding_name: str) -> None:
        self.encoding_name = encoding_name
        self._encoding: Any | None = None
        self._load_error: Exception | None = None

    def __call__(self, text: str) -> int:
        try:
            encoding = self._get_encoding()
        except Exception:
            # tiktoken is installed, but encoding files may fail to download
            # in restricted environments. Use a deterministic 4-char estimate
            # so selection can still run; tests compare via count_tokens().
            return _fallback_token_count(text)
        return len(encoding.encode(text))

    def _get_encoding(self) -> Any:
        if self._encoding is not None:
            return self._encoding
        if self._load_error is not None:
            raise self._load_error
        try:
            import tiktoken

            self._encoding = tiktoken.get_encoding(self.encoding_name)
            return self._encoding
        except Exception:
            # tiktoken downloads encoding tables on first use. If that
            # fails (offline or SSL), keep a deterministic fallback so
            # selection still runs. Tests compare counts via count_tokens().
            self._encoding = _CharacterFallbackEncoding()
            return self._encoding


class _CharacterFallbackEncoding:
    """Approximate tokens as ceil(chars / 4) when tiktoken cannot load."""

    def encode(self, text: str) -> list[int]:
        size = _fallback_token_count(text)
        return list(range(size))


def _normalized_budget(token_budget: int) -> int:
    """Treat a missing or negative budget as zero so remaining stays non-negative."""
    try:
        budget = int(token_budget)
    except (TypeError, ValueError):
        return 0
    return max(0, budget)


def _candidate_fields(candidate: RankedFile | dict[str, Any]) -> tuple[str, int]:
    if isinstance(candidate, RankedFile):
        return candidate.path, int(candidate.score)
    if isinstance(candidate, dict):
        path = str(candidate.get("path") or "")
        try:
            score = int(candidate.get("score") or 0)
        except (TypeError, ValueError):
            score = 0
        return path, score
    return "", 0


def _safe_resolve(project_root: Path, relative_path: str) -> Path | None:
    """Resolve ``relative_path`` only if it stays under ``project_root``."""
    if not relative_path:
        return None

    candidate = Path(relative_path)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (project_root / candidate).resolve()

    try:
        resolved.relative_to(project_root)
    except ValueError:
        return None
    return resolved


def _assemble_context(selected: list[SelectedFile]) -> str:
    if not selected:
        return ""
    blocks = [
        f"===== FILE: {item.path} =====\n{item.content}"
        for item in selected
    ]
    return "\n\n".join(blocks)
