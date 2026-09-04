"""Context Compressor for optimizing selected code context before LLM submission.

Removes clearly redundant and non-essential content (such as license headers,
standalone comments, trailing whitespace, and excessive blank lines) while
preserving code structure, indentation, and file boundary delimiters.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from app.optimizer.selector import ContextSelector, SelectedFile, SelectionResult

_FILE_HEADER_PATTERN = re.compile(r"^===== FILE: (.+?) =====$", re.MULTILINE)

# Common license / copyright markers found at the start of source files
_LICENSE_MARKERS = (
    "copyright",
    "license",
    "spdx-license-identifier",
    "all rights reserved",
    "mit license",
    "apache license",
    "mozilla public license",
    "bsd license",
    "gnu general public",
)

# File extensions that use '#' for comments
_HASH_COMMENT_EXTENSIONS = {
    ".py",
    ".sh",
    ".bash",
    ".zsh",
    ".rb",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".dockerfile",
    "dockerfile",
}

# File extensions that use '//' and '/*' for comments
_C_STYLE_COMMENT_EXTENSIONS = {
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".java",
    ".go",
    ".rs",
    ".cs",
    ".swift",
    ".kt",
    ".php",
    ".css",
    ".scss",
    ".less",
}

# Pragmas and directives that must be preserved
_HASH_PRAGMAS = (
    "#!",
    "# -*-",
    "# coding:",
    "# type:",
    "# noqa",
    "# pylint:",
    "# pragma:",
    "# fmt:",
    "# mypy:",
)

_SLASH_PRAGMAS = (
    "// @ts-",
    "// @ts-ignore",
    "// @ts-nocheck",
    "// @ts-expect-error",
    "// eslint-",
    "// istanbul",
    "// @flow",
    "// nolint",
    "// +build",
    "//go:",
)


@dataclass
class CompressorOptions:
    """Configuration options for ContextCompressor."""

    strip_comments: bool = True
    collapse_blank_lines: bool = True
    strip_trailing_whitespace: bool = True
    strip_license_headers: bool = True
    preserve_pragmas: bool = True
    max_consecutive_blank_lines: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dictionary."""
        return asdict(self)


@dataclass
class CompressionMetrics:
    """Metrics comparing original and compressed context."""

    original_tokens: int
    compressed_tokens: int
    tokens_saved: int
    compression_ratio: float
    saving_percentage: float
    original_characters: int
    compressed_characters: int
    lines_removed: int

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dictionary."""
        return asdict(self)


@dataclass
class CompressedFile:
    """Compression outcome for a single file."""

    path: str
    original_tokens: int
    compressed_tokens: int
    original_content: str
    compressed_content: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dictionary."""
        return asdict(self)


@dataclass
class CompressionResult:
    """Outcome of context compression including assembled text and metrics."""

    original_context: str
    compressed_context: str
    metrics: CompressionMetrics
    files: list[CompressedFile] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dictionary."""
        return asdict(self)


class ContextCompressor:
    """Safely compress selected code context to fit LLM prompt budgets."""

    def __init__(
        self,
        encoding_name: str = "cl100k_base",
        count_tokens: Callable[[str], int] | None = None,
        options: CompressorOptions | None = None,
    ) -> None:
        """Create a compressor.

        Args:
            encoding_name: tiktoken encoding name (cl100k_base by default).
            count_tokens: Optional token counter. If not provided, delegates
                to ContextSelector's tokenizer for consistent token counts.
            options: Optional compression options.
        """
        self.encoding_name = encoding_name
        self.options = options or CompressorOptions()
        if count_tokens is not None:
            self._count_tokens = count_tokens
        else:
            selector = ContextSelector(encoding_name=encoding_name)
            self._count_tokens = selector.count_tokens

    def count_tokens(self, text: str) -> int:
        """Return token count using the configured tokenizer."""
        if not text:
            return 0
        return int(self._count_tokens(text))

    def compress(
        self,
        target: str | SelectionResult | list[SelectedFile] | dict[str, Any] | None,
    ) -> CompressionResult:
        """Compress code context from various supported input representations.

        Accepts:
            - A ``SelectionResult`` from ``ContextSelector.select()``
            - A list of ``SelectedFile`` objects
            - A dictionary representing a ``SelectionResult``
            - A raw string containing assembled context or source code
        """
        if target is None:
            return self._empty_result()

        file_items: list[tuple[str, str]] = []
        raw_context = ""

        if isinstance(target, SelectionResult):
            raw_context = target.context
            file_items = [(f.path, f.content) for f in target.selected_files]
        elif isinstance(target, list):
            for item in target:
                if isinstance(item, SelectedFile):
                    file_items.append((item.path, item.content))
                elif isinstance(item, dict):
                    path = str(item.get("path") or "")
                    content = str(item.get("content") or "")
                    file_items.append((path, content))
            raw_context = _assemble_blocks(file_items)
        elif isinstance(target, dict):
            if "selected_files" in target and isinstance(target["selected_files"], list):
                for item in target["selected_files"]:
                    if isinstance(item, dict):
                        file_items.append((str(item.get("path") or ""), str(item.get("content") or "")))
                raw_context = str(target.get("context") or _assemble_blocks(file_items))
            else:
                raw_context = str(target.get("context") or "")
                file_items = _extract_file_blocks(raw_context)
        elif isinstance(target, str):
            raw_context = target
            file_items = _extract_file_blocks(target)
        else:
            raw_context = str(target)
            file_items = _extract_file_blocks(raw_context)

        # Normalize line endings
        raw_context = _normalize_newlines(raw_context)

        if not raw_context.strip() and not file_items:
            return self._empty_result()

        compressed_files: list[CompressedFile] = []

        if file_items:
            for path, content in file_items:
                compressed_file = self.compress_file(path, content)
                compressed_files.append(compressed_file)

            compressed_context = _assemble_blocks(
                [(cf.path, cf.compressed_content) for cf in compressed_files]
            )
        else:
            # Standalone single string without file boundaries
            single_cf = self.compress_file("", raw_context)
            compressed_files.append(single_cf)
            compressed_context = single_cf.compressed_content

        metrics = self._calculate_metrics(raw_context, compressed_context)

        return CompressionResult(
            original_context=raw_context,
            compressed_context=compressed_context,
            metrics=metrics,
            files=compressed_files,
        )

    def compress_file(self, path: str, content: str) -> CompressedFile:
        """Compress a single file's content while preserving its code semantics."""
        normalized = _normalize_newlines(content)
        if not normalized.strip():
            orig_tokens = self.count_tokens(normalized)
            return CompressedFile(
                path=path,
                original_tokens=orig_tokens,
                compressed_tokens=0,
                original_content=normalized,
                compressed_content="",
            )

        orig_tokens = self.count_tokens(normalized)
        compressed_text = self._compress_source(path, normalized)
        comp_tokens = self.count_tokens(compressed_text)

        return CompressedFile(
            path=path,
            original_tokens=orig_tokens,
            compressed_tokens=comp_tokens,
            original_content=normalized,
            compressed_content=compressed_text,
        )

    def _compress_source(self, path: str, text: str) -> str:
        """Apply deterministic compression rules to source code."""
        lines = text.split("\n")
        extension = Path(path).suffix.lower() if path else ""

        # Step 1: Strip license/copyright header if requested
        if self.options.strip_license_headers:
            lines = _strip_license_header(lines, extension)

        # Step 2: Strip comments if requested
        if self.options.strip_comments:
            lines = self._strip_comments(lines, extension)

        # Step 3: Strip trailing whitespace
        if self.options.strip_trailing_whitespace:
            lines = [line.rstrip() for line in lines]

        # Step 4: Collapse blank lines
        if self.options.collapse_blank_lines:
            lines = _collapse_blank_lines(lines, self.options.max_consecutive_blank_lines)

        return "\n".join(lines).strip()

    def _strip_comments(self, lines: list[str], extension: str) -> list[str]:
        """Strip pure comment lines while preserving pragmas and code."""
        result: list[str] = []
        is_hash = extension in _HASH_COMMENT_EXTENSIONS or not extension
        is_c_style = extension in _C_STYLE_COMMENT_EXTENSIONS or not extension
        in_block_comment = False

        for line in lines:
            stripped = line.strip()

            # Handle C-style block comments
            if is_c_style:
                if in_block_comment:
                    if "*/" in line:
                        in_block_comment = False
                    continue

                if stripped.startswith("/*"):
                    if "*/" in stripped:
                        # Single-line block comment
                        continue
                    in_block_comment = True
                    continue

                # C-style single-line comment
                if stripped.startswith("//"):
                    if self.options.preserve_pragmas and any(
                        stripped.startswith(p) for p in _SLASH_PRAGMAS
                    ):
                        result.append(line)
                    continue

            # Handle hash comments
            if is_hash:
                if stripped.startswith("#"):
                    if self.options.preserve_pragmas and any(
                        stripped.startswith(p) for p in _HASH_PRAGMAS
                    ):
                        result.append(line)
                    continue

            result.append(line)

        return result

    def _calculate_metrics(
        self, original_context: str, compressed_context: str
    ) -> CompressionMetrics:
        """Compute token and character reduction metrics."""
        orig_tokens = self.count_tokens(original_context)
        comp_tokens = self.count_tokens(compressed_context)
        tokens_saved = max(0, orig_tokens - comp_tokens)

        ratio = round(comp_tokens / orig_tokens, 4) if orig_tokens > 0 else 1.0
        percentage = round((tokens_saved / orig_tokens) * 100, 2) if orig_tokens > 0 else 0.0

        orig_chars = len(original_context)
        comp_chars = len(compressed_context)

        orig_lines = len(original_context.splitlines()) if original_context else 0
        comp_lines = len(compressed_context.splitlines()) if compressed_context else 0
        lines_removed = max(0, orig_lines - comp_lines)

        return CompressionMetrics(
            original_tokens=orig_tokens,
            compressed_tokens=comp_tokens,
            tokens_saved=tokens_saved,
            compression_ratio=ratio,
            saving_percentage=percentage,
            original_characters=orig_chars,
            compressed_characters=comp_chars,
            lines_removed=lines_removed,
        )

    def _empty_result(self) -> CompressionResult:
        """Return a blank result for empty context."""
        return CompressionResult(
            original_context="",
            compressed_context="",
            metrics=CompressionMetrics(
                original_tokens=0,
                compressed_tokens=0,
                tokens_saved=0,
                compression_ratio=1.0,
                saving_percentage=0.0,
                original_characters=0,
                compressed_characters=0,
                lines_removed=0,
            ),
            files=[],
        )


def _normalize_newlines(text: str) -> str:
    """Normalize CRLF and CR to standard LF."""
    if not text:
        return ""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _extract_file_blocks(text: str) -> list[tuple[str, str]]:
    """Extract (path, content) blocks from an assembled context string.

    Looks for delimiter format:
        ===== FILE: <path> =====
        <content>
    """
    matches = list(_FILE_HEADER_PATTERN.finditer(text))
    if not matches:
        return []

    blocks: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        path = match.group(1).strip()
        start = match.end()
        # If followed by a newline, skip it
        if start < len(text) and text[start] == "\n":
            start += 1

        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].rstrip("\n")
        blocks.append((path, content))

    return blocks


def _assemble_blocks(items: Iterable[tuple[str, str]]) -> str:
    """Assemble file blocks into standard context string."""
    blocks: list[str] = []
    for path, content in items:
        if path:
            blocks.append(f"===== FILE: {path} =====\n{content}")
        else:
            blocks.append(content)
    return "\n\n".join(blocks)


def _strip_license_header(lines: list[str], extension: str) -> list[str]:
    """Strip leading license/copyright header comments if present."""
    if not lines:
        return lines

    # Find the boundary of the leading comment block
    header_end_idx = 0
    in_block = False
    has_license_keyword = False

    for i, line in enumerate(lines):
        stripped = line.strip().lower()
        if not stripped:
            continue

        is_comment = False
        if stripped.startswith(("#", "//", "/*", "*")):
            is_comment = True
            if "/*" in stripped:
                in_block = True
            if "*/" in stripped:
                in_block = False
        elif in_block:
            is_comment = True
            if "*/" in stripped:
                in_block = False

        if not is_comment:
            # First non-comment code line reached
            header_end_idx = i
            break

        if any(marker in stripped for marker in _LICENSE_MARKERS):
            has_license_keyword = True
    else:
        header_end_idx = len(lines)

    # Only strip if the header actually contains license/copyright markers
    if has_license_keyword and header_end_idx > 0:
        # Check if there is a shebang at line 0 to preserve
        first_line = lines[0].strip()
        if first_line.startswith("#!"):
            return [lines[0]] + lines[header_end_idx:]
        return lines[header_end_idx:]

    return lines


def _collapse_blank_lines(lines: list[str], max_consecutive: int = 1) -> list[str]:
    """Collapse consecutive blank lines to at most ``max_consecutive``."""
    result: list[str] = []
    blank_count = 0

    for line in lines:
        if not line.strip():
            blank_count += 1
            if blank_count <= max_consecutive:
                result.append("")
        else:
            blank_count = 0
            result.append(line)

    # Strip leading blank lines
    while result and not result[0].strip():
        result.pop(0)

    # Strip trailing blank lines
    while result and not result[-1].strip():
        result.pop()

    return result
