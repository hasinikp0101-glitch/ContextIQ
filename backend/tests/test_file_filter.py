"""Manual checks for FileFilter (stdlib unittest only)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.scanner.filter import DEFAULT_MAX_FILE_SIZE_BYTES, FileFilter


def _file(
    path: str,
    file_type: str,
    size: int = 100,
    extension: str | None = None,
) -> dict:
    suffix = Path(path).suffix.lower() if extension is None else extension
    return {
        "path": path,
        "extension": suffix,
        "file_type": file_type,
        "size": size,
    }


class FileFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.file_filter = FileFilter()

    def _run(self, files: list[dict]) -> dict:
        return self.file_filter.filter({"files": files})

    def test_01_source_file_is_kept(self) -> None:
        result = self._run([_file("auth/jwt.js", "source")])
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["path"], "auth/jwt.js")
        self.assertEqual(result["filtered_count"], 0)

    def test_02_test_file_is_kept(self) -> None:
        result = self._run([_file("tests/test_auth.py", "test")])
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["file_type"], "test")

    def test_03_config_file_is_kept(self) -> None:
        result = self._run([_file("pyproject.toml", "config")])
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["path"], "pyproject.toml")

    def test_04_markdown_documentation_is_kept(self) -> None:
        result = self._run([_file("README.md", "other")])
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["path"], "README.md")

    def test_05_lock_file_is_filtered(self) -> None:
        result = self._run([_file("poetry.lock", "other", extension=".lock")])
        self.assertEqual(result["filtered_count"], 1)
        self.assertEqual(result["filtered_files"][0]["reason"], "ignored extension")

    def test_06_pyc_file_is_filtered(self) -> None:
        result = self._run([_file("__pycache__/app.pyc", "other", extension=".pyc")])
        self.assertEqual(result["filtered_count"], 1)
        self.assertEqual(result["filtered_files"][0]["reason"], "ignored extension")

    def test_07_binary_media_file_is_filtered(self) -> None:
        result = self._run([_file("assets/logo.png", "other")])
        self.assertEqual(result["filtered_count"], 1)
        self.assertEqual(result["filtered_files"][0]["reason"], "binary/media file")

    def test_08_large_file_uses_configured_limit(self) -> None:
        small_limit = FileFilter(max_file_size_bytes=500)
        large = _file("src/huge.py", "source", size=501)
        small = _file("src/ok.py", "source", size=500)
        result = small_limit.filter({"files": [large, small]})
        kept_paths = {item["path"] for item in result["files"]}
        self.assertEqual(kept_paths, {"src/ok.py"})
        self.assertEqual(result["filtered_count"], 1)
        self.assertEqual(result["filtered_files"][0]["reason"], "file exceeds size limit")
        self.assertEqual(DEFAULT_MAX_FILE_SIZE_BYTES, 1_048_576)

    def test_09_empty_scanner_result_works(self) -> None:
        result = self.file_filter.filter({})
        self.assertEqual(result["files"], [])
        self.assertEqual(result["filtered_files"], [])
        self.assertEqual(result["filtered_count"], 0)

        empty_scan = self.file_filter.filter(
            {
                "total_files": 0,
                "source_files": 0,
                "config_files": 0,
                "test_files": 0,
                "ignored_files": 0,
                "files": [],
            }
        )
        self.assertEqual(empty_scan["filtered_count"], 0)

    def test_10_filtered_files_have_clear_reasons(self) -> None:
        result = self._run(
            [
                _file("yarn.lock", "other", extension=".lock"),
                _file("photo.jpg", "other"),
                _file("dist/bundle.js", "source"),
                _file("notes.bin", "other", extension=".bin"),
            ]
        )
        reasons = {item["path"]: item["reason"] for item in result["filtered_files"]}
        self.assertEqual(reasons["yarn.lock"], "ignored extension")
        self.assertEqual(reasons["photo.jpg"], "binary/media file")
        self.assertEqual(reasons["dist/bundle.js"], "generated/build file")
        self.assertEqual(
            reasons["notes.bin"],
            "not a source, config, test, or documentation file",
        )
        for item in result["filtered_files"]:
            self.assertTrue(item["path"])
            self.assertTrue(item["reason"])

    def test_11_does_not_score_relevance(self) -> None:
        files = [
            _file("auth/jwt.js", "source"),
            _file("auth/middleware.js", "source"),
            _file("frontend/Home.jsx", "source"),
            _file("database/schema.sql", "source"),
        ]
        result = self._run(files)
        kept = [item["path"] for item in result["files"]]
        self.assertEqual(
            kept,
            [
                "auth/jwt.js",
                "auth/middleware.js",
                "frontend/Home.jsx",
                "database/schema.sql",
            ],
        )
        self.assertEqual(result["filtered_count"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
