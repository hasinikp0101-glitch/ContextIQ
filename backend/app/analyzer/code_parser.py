"""Static structural analysis for files that survived scanning and filtering.

This layer never executes repository code and never calls an LLM. Python
uses the standard-library ``ast`` module. JavaScript and TypeScript use
conservative regular expressions, not a full language parser, so unusual
syntax may be missed. Results are structured metadata for a later
relevance-ranking engine.
"""

from __future__ import annotations

import ast
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


# Align with the File Filter default: larger files are not useful to parse
# in this hackathon-sized analyzer and may be generated or binary-like.
DEFAULT_MAX_READ_BYTES = 1_048_576

PYTHON_EXTENSIONS = {".py"}
JAVASCRIPT_EXTENSIONS = {".js", ".jsx"}
TYPESCRIPT_EXTENSIONS = {".ts", ".tsx"}

# NUL bytes in the first chunk are a strong sign the file is not text.
_BINARY_PROBE_BYTES = 8192


@dataclass
class FileAnalysis:
    """Structural metadata for one source file."""

    path: str
    language: str
    analysis_supported: bool
    line_count: int = 0
    imports: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    analysis_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dictionary."""
        return asdict(self)


class CodeAnalyzer:
    """Extract structural metadata from filtered file entries.

    The analyzer reads files under ``project_root`` only. It does not
    decide relevance and does not ignore directories (scanner/filter
    already did that).
    """

    def __init__(self, max_read_bytes: int = DEFAULT_MAX_READ_BYTES) -> None:
        """Create an analyzer.

        Args:
            max_read_bytes: Maximum number of bytes to read from one file.
        """
        self.max_read_bytes = max_read_bytes

    def analyze_file(
        self,
        project_root: str | Path,
        file_metadata: dict[str, Any],
    ) -> FileAnalysis:
        """Analyze a single file described by scanner/filter metadata."""
        relative_path = str(file_metadata.get("path", ""))
        extension = self._extension(file_metadata, relative_path)
        language = self._language_for_extension(extension)
        supported = language != "unknown"

        resolved_root = Path(project_root).expanduser().resolve()
        target = self._safe_resolve(resolved_root, relative_path)
        if target is None:
            return FileAnalysis(
                path=relative_path,
                language=language,
                analysis_supported=supported,
                analysis_error="path is outside the project root or is invalid",
            )

        if not target.exists() or not target.is_file():
            return FileAnalysis(
                path=relative_path,
                language=language,
                analysis_supported=supported,
                analysis_error="file not found or is not a regular file",
            )

        try:
            if target.stat().st_size > self.max_read_bytes:
                return FileAnalysis(
                    path=relative_path,
                    language=language,
                    analysis_supported=supported,
                    analysis_error="file exceeds analyzer read size limit",
                )
        except OSError as exc:
            return FileAnalysis(
                path=relative_path,
                language=language,
                analysis_supported=supported,
                analysis_error=f"file is unreadable: {exc}",
            )

        try:
            raw = target.read_bytes()
        except OSError as exc:
            return FileAnalysis(
                path=relative_path,
                language=language,
                analysis_supported=supported,
                analysis_error=f"file is unreadable: {exc}",
            )

        if self._looks_binary(raw):
            return FileAnalysis(
                path=relative_path,
                language=language,
                analysis_supported=supported,
                analysis_error="file looks binary and was not parsed",
            )

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return FileAnalysis(
                path=relative_path,
                language=language,
                analysis_supported=supported,
                analysis_error="file is not valid UTF-8 text",
            )

        line_count = self._line_count(text)

        if not supported:
            return FileAnalysis(
                path=relative_path,
                language=language,
                analysis_supported=False,
                line_count=line_count,
            )

        if language == "python":
            return self._analyze_python(relative_path, text, line_count)

        return self._analyze_javascript_family(
            relative_path,
            language,
            text,
            line_count,
        )

    def analyze_files(
        self,
        project_root: str | Path,
        filtered_files: dict[str, Any] | Iterable[dict[str, Any]],
    ) -> list[FileAnalysis]:
        """Analyze every file from a filter result or a list of file dicts."""
        entries = self._file_entries(filtered_files)
        return [self.analyze_file(project_root, entry) for entry in entries]

    @staticmethod
    def _file_entries(
        filtered_files: dict[str, Any] | Iterable[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if isinstance(filtered_files, dict):
            return list(filtered_files.get("files") or [])
        return list(filtered_files)

    @staticmethod
    def _extension(file_metadata: dict[str, Any], path: str) -> str:
        extension = file_metadata.get("extension")
        if isinstance(extension, str) and extension:
            return extension.lower()
        return Path(path).suffix.lower()

    @staticmethod
    def _language_for_extension(extension: str) -> str:
        if extension in PYTHON_EXTENSIONS:
            return "python"
        if extension in JAVASCRIPT_EXTENSIONS:
            return "javascript"
        if extension in TYPESCRIPT_EXTENSIONS:
            return "typescript"
        return "unknown"

    @staticmethod
    def _safe_resolve(project_root: Path, relative_path: str) -> Path | None:
        """Resolve ``relative_path`` only if it stays under ``project_root``.

        ``Path.resolve()`` follows symlinks. If the final path is outside
        the project root, the read is refused.
        """
        if not relative_path or relative_path.strip() != relative_path:
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

    @staticmethod
    def _looks_binary(raw: bytes) -> bool:
        return b"\x00" in raw[:_BINARY_PROBE_BYTES]

    @staticmethod
    def _line_count(text: str) -> int:
        if not text:
            return 0
        return len(text.splitlines())

    def _analyze_python(
        self,
        relative_path: str,
        text: str,
        line_count: int,
    ) -> FileAnalysis:
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            return FileAnalysis(
                path=relative_path,
                language="python",
                analysis_supported=True,
                line_count=line_count,
                analysis_error=f"Python syntax error: {exc.msg}",
            )

        imports = _unique(_python_imports(tree))
        functions = _unique(_python_functions(tree))
        classes = _unique(_python_classes(tree))
        symbols = _unique(functions + classes + _python_import_aliases(tree))
        return FileAnalysis(
            path=relative_path,
            language="python",
            analysis_supported=True,
            line_count=line_count,
            imports=imports,
            functions=functions,
            classes=classes,
            symbols=symbols,
            exports=[],
        )

    def _analyze_javascript_family(
        self,
        relative_path: str,
        language: str,
        text: str,
        line_count: int,
    ) -> FileAnalysis:
        # Regex extraction is conservative. It will miss dynamic imports,
        # unusual formatting, and many TypeScript-only constructs. It is
        # not a JavaScript or TypeScript parser.
        imports = _unique(_js_imports(text) + _js_requires(text))
        functions = _unique(_js_functions(text))
        classes = _unique(_js_classes(text))
        exports = _unique(_js_exports(text))
        symbols = _unique(functions + classes + exports)
        return FileAnalysis(
            path=relative_path,
            language=language,
            analysis_supported=True,
            line_count=line_count,
            imports=imports,
            functions=functions,
            classes=classes,
            symbols=symbols,
            exports=exports,
        )


def _unique(values: Iterable[str]) -> list[str]:
    """Keep first-seen order so output stays deterministic for the same file."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _python_imports(tree: ast.AST) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            dots = "." * node.level
            if node.module:
                modules.append(f"{dots}{node.module}")
            elif dots:
                modules.append(dots)
    return modules


def _python_import_aliases(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.append(alias.asname or alias.name)
    return names


def _python_functions(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(node.name)
    return names


def _python_classes(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            names.append(node.name)
    return names


# --- JavaScript / TypeScript (conservative regex, not a full parser) ---

_JS_IMPORT_FROM = re.compile(
    r"""(?m)^\s*(?:export\s+)?import\s+(?:type\s+)?(?:[\w*\s{},$]+from\s+)?['"]([^'"]+)['"]"""
)
_JS_REQUIRE = re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""")
_JS_FUNCTION = re.compile(
    r"""(?:^|[\s;{}])(?:export\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\(""",
)
_JS_ARROW_OR_FN_EXPR = re.compile(
    r"""(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*"""
    r"""(?:async\s*)?(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)""",
)
_JS_CLASS = re.compile(
    r"""(?:export\s+)?(?:default\s+)?class\s+([A-Za-z_$][\w$]*)""",
)
_JS_EXPORT_DECL = re.compile(
    r"""export\s+(?:default\s+)?(?:async\s+)?(?:function\s*\*?\s*|class\s+|const\s+|let\s+|var\s+)"""
    r"""([A-Za-z_$][\w$]*)""",
)
_JS_EXPORT_LIST = re.compile(r"""export\s*\{([^}]+)\}""")
_JS_EXPORT_NAME = re.compile(r"""([A-Za-z_$][\w$]*)(?:\s+as\s+[A-Za-z_$][\w$]*)?""")


def _js_imports(text: str) -> list[str]:
    return [match.group(1) for match in _JS_IMPORT_FROM.finditer(text)]


def _js_requires(text: str) -> list[str]:
    return [match.group(1) for match in _JS_REQUIRE.finditer(text)]


def _js_functions(text: str) -> list[str]:
    names = [match.group(1) for match in _JS_FUNCTION.finditer(text)]
    names.extend(match.group(1) for match in _JS_ARROW_OR_FN_EXPR.finditer(text))
    return names


def _js_classes(text: str) -> list[str]:
    return [match.group(1) for match in _JS_CLASS.finditer(text)]


def _js_exports(text: str) -> list[str]:
    names = [match.group(1) for match in _JS_EXPORT_DECL.finditer(text)]
    for match in _JS_EXPORT_LIST.finditer(text):
        for name_match in _JS_EXPORT_NAME.finditer(match.group(1)):
            names.append(name_match.group(1))
    return names
