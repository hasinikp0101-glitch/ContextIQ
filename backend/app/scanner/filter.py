"""Filter scanner file metadata before later analysis stages.

This module does not read file contents and does not score relevance.
It only decides which files are valid candidates for later components.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any


# Default cap: 1 MiB. Source, config, test, and markdown files are almost
# always smaller than this. Files above 1 MiB are often generated bundles,
# dumps, or vendor artifacts that would dominate later analysis. Callers
# can pass a different ``max_file_size_bytes`` when constructing FileFilter.
DEFAULT_MAX_FILE_SIZE_BYTES = 1_048_576

IGNORE_EXTENSIONS = {
    ".pyc",
    ".lock",
}

BINARY_MEDIA_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".mp3",
    ".mp4",
    ".wav",
    ".zip",
    ".tar",
    ".gz",
    ".exe",
    ".dll",
    ".so",
}

# Directory names that mean generated, vendored, or build output.
# The scanner already skips many of these; the filter still checks in case
# such paths appear in scanner output.
GENERATED_DIRECTORY_NAMES = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".idea",
    ".vscode",
    "coverage",
    ".next",
    "out",
    "target",
    "vendor",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".cache",
    "site-packages",
}

DOCUMENTATION_EXTENSIONS = {
    ".md",
    ".mdx",
    ".rst",
    ".adoc",
}

KEEP_FILE_TYPES = {
    "source",
    "config",
    "test",
}


class FileFilter:
    """Drop files that should not continue to code analysis.

    The filter works only on metadata from ``RepositoryScanner``. It does
    not open files and does not decide which files are relevant to a query.
    """

    def __init__(self, max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES) -> None:
        """Create a filter with a size limit for very large files.

        Args:
            max_file_size_bytes: Maximum kept file size in bytes. The
                default is 1 MiB (see ``DEFAULT_MAX_FILE_SIZE_BYTES``).
        """
        self.max_file_size_bytes = max_file_size_bytes

    def filter(self, scanner_result: dict[str, Any]) -> dict[str, Any]:
        """Keep candidate files and record why others were removed.

        Args:
            scanner_result: Output from ``RepositoryScanner.scan()``.
                Missing or empty ``files`` is treated as an empty list.

        Returns:
            A dictionary with kept ``files``, ``filtered_files`` (each
            with a path and reason), and ``filtered_count``.
        """
        incoming_files = scanner_result.get("files") or []

        kept_files: list[dict[str, Any]] = []
        filtered_files: list[dict[str, str]] = []

        for file_entry in incoming_files:
            reason = self._rejection_reason(file_entry)
            if reason is None:
                kept_files.append(file_entry)
            else:
                filtered_files.append(
                    {
                        "path": str(file_entry.get("path", "")),
                        "reason": reason,
                    }
                )

        return {
            "files": kept_files,
            "filtered_files": filtered_files,
            "filtered_count": len(filtered_files),
        }

    def _rejection_reason(self, file_entry: dict[str, Any]) -> str | None:
        """Return a human-readable removal reason, or None to keep the file."""
        path = str(file_entry.get("path", ""))
        extension = self._extension(file_entry, path)
        size = file_entry.get("size", 0)
        file_type = str(file_entry.get("file_type", "other"))

        if extension in IGNORE_EXTENSIONS:
            return "ignored extension"

        if extension in BINARY_MEDIA_EXTENSIONS:
            return "binary/media file"

        if self._is_generated_or_build_path(path):
            return "generated/build file"

        if isinstance(size, int) and size > self.max_file_size_bytes:
            return "file exceeds size limit"

        if file_type in KEEP_FILE_TYPES:
            return None

        if extension in DOCUMENTATION_EXTENSIONS:
            return None

        return "not a source, config, test, or documentation file"

    @staticmethod
    def _extension(file_entry: dict[str, Any], path: str) -> str:
        """Prefer scanner extension metadata; fall back to the path suffix."""
        extension = file_entry.get("extension")
        if isinstance(extension, str) and extension:
            return extension.lower()
        return Path(path).suffix.lower()

    @staticmethod
    def _is_generated_or_build_path(path: str) -> bool:
        """Return True if any path segment is a generated or build directory."""
        parts = [part.lower() for part in PurePosixPath(path).parts]
        if not parts:
            return False

        directory_parts = parts[:-1]
        return any(part in GENERATED_DIRECTORY_NAMES for part in directory_parts)
