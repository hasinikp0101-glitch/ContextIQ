"""Recursively scan a project directory and collect file metadata."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


IGNORE_DIRECTORIES = {
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
}

IGNORE_EXTENSIONS = {
    ".pyc",
    ".lock",
}

SOURCE_EXTENSIONS = {
    ".py",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".kts",
    ".scala",
    ".vue",
    ".svelte",
    ".html",
    ".css",
    ".scss",
    ".sass",
    ".sql",
    ".sh",
    ".bash",
    ".ps1",
}

CONFIG_EXTENSIONS = {
    ".json",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".xml",
    ".env",
}

CONFIG_FILENAMES = {
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "pipfile",
    "cargo.toml",
    "go.mod",
    "go.sum",
    "pom.xml",
    "build.gradle",
    "tsconfig.json",
    "jsconfig.json",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".gitignore",
    ".dockerignore",
    "makefile",
    "cmakelists.txt",
    ".env",
    ".env.example",
    "tox.ini",
    "pytest.ini",
}

TEST_DIRECTORY_NAMES = {
    "test",
    "tests",
    "__tests__",
    "spec",
    "specs",
}


class RepositoryScanner:
    """Discover files in a project directory and classify them.

    The scanner walks the given path, skips common repository noise,
    and returns metadata only (no file contents are read).
    """

    def __init__(self, project_path: str | Path) -> None:
        """Create a scanner for ``project_path``.

        Args:
            project_path: Absolute or relative path to the project root.
        """
        self.project_path = Path(project_path).expanduser().resolve()

    def scan(self) -> dict[str, Any]:
        """Scan the project directory and return file metadata plus counts.

        If the path does not exist or is not a directory, an empty result
        is returned instead of raising an error.

        Returns:
            A dictionary with summary counts and a ``files`` list. Each
            file entry uses a path relative to the project root.
        """
        if not self.project_path.exists() or not self.project_path.is_dir():
            return self._empty_result()

        files: list[dict[str, Any]] = []
        ignored_files = 0

        for current, dir_names, file_names in os.walk(self.project_path):
            current_dir = Path(current)
            ignored_files += self._prune_and_count_ignored_dirs(current_dir, dir_names)

            for file_name in file_names:
                file_path = current_dir / file_name

                if not file_path.is_file():
                    continue

                if self._should_ignore_file(file_path):
                    ignored_files += 1
                    continue

                files.append(self._build_file_entry(file_path))

        return {
            "total_files": len(files),
            "source_files": self._count_by_type(files, "source"),
            "config_files": self._count_by_type(files, "config"),
            "test_files": self._count_by_type(files, "test"),
            "ignored_files": ignored_files,
            "files": files,
        }

    def _prune_and_count_ignored_dirs(
        self,
        current_dir: Path,
        dir_names: list[str],
    ) -> int:
        """Remove ignored directories from the walk and count files inside them."""
        ignored_count = 0
        kept: list[str] = []

        for dir_name in dir_names:
            if dir_name in IGNORE_DIRECTORIES:
                ignored_count += self._count_files_recursively(current_dir / dir_name)
            else:
                kept.append(dir_name)

        dir_names[:] = kept
        return ignored_count

    def _count_files_recursively(self, directory: Path) -> int:
        """Count regular files under ``directory`` (used for ignored folders)."""
        count = 0
        if not directory.exists():
            return 0

        for path in directory.rglob("*"):
            if path.is_file():
                count += 1
        return count

    def _should_ignore_file(self, file_path: Path) -> bool:
        """Return True if the file should not be included in scan results."""
        return file_path.suffix.lower() in IGNORE_EXTENSIONS

    def _build_file_entry(self, file_path: Path) -> dict[str, Any]:
        """Build metadata for a single discovered file."""
        relative_path = file_path.relative_to(self.project_path).as_posix()
        extension = file_path.suffix.lower()

        try:
            size = file_path.stat().st_size
        except OSError:
            size = 0

        return {
            "path": relative_path,
            "extension": extension,
            "file_type": self._classify_file(relative_path, file_path.name, extension),
            "size": size,
        }

    def _classify_file(self, relative_path: str, file_name: str, extension: str) -> str:
        """Classify a file as source, config, test, or other."""
        if self._is_test_file(relative_path, file_name):
            return "test"

        if self._is_config_file(file_name, extension):
            return "config"

        if extension in SOURCE_EXTENSIONS:
            return "source"

        return "other"

    def _is_test_file(self, relative_path: str, file_name: str) -> bool:
        """Return True if the file looks like a test file."""
        parent_parts = {part.lower() for part in Path(relative_path).parts[:-1]}
        if parent_parts & TEST_DIRECTORY_NAMES:
            return True

        lower_name = file_name.lower()
        stem = Path(file_name).stem.lower()

        if lower_name.startswith("test_"):
            return True

        if stem.endswith("_test"):
            return True

        if stem.endswith(".test") or stem.endswith(".spec"):
            return True

        return False

    def _is_config_file(self, file_name: str, extension: str) -> bool:
        """Return True if the file looks like a configuration file."""
        if file_name.lower() in CONFIG_FILENAMES:
            return True

        if extension in CONFIG_EXTENSIONS:
            return True

        return False

    @staticmethod
    def _count_by_type(files: list[dict[str, Any]], file_type: str) -> int:
        """Count files that match a given classification."""
        return sum(1 for item in files if item["file_type"] == file_type)

    @staticmethod
    def _empty_result() -> dict[str, Any]:
        """Return a zeroed scan result for invalid project paths."""
        return {
            "total_files": 0,
            "source_files": 0,
            "config_files": 0,
            "test_files": 0,
            "ignored_files": 0,
            "files": [],
        }
