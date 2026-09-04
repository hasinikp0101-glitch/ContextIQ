"""Tests for the static Code Analyzer."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.analyzer.code_parser import CodeAnalyzer, FileAnalysis
from app.scanner.filter import FileFilter
from app.scanner.scanner import RepositoryScanner


PYTHON_SAMPLE = '''\
import os
from json import dumps

def helper():
    return dumps({})

async def fetch_user():
    return None

class AuthService:
    def login(self):
        return os.getenv("TOKEN")
'''

JS_SAMPLE = '''\
import jwt from "jsonwebtoken";
import { foo } from "./foo";

const auth = require("./auth");
const jsonwebtoken = require("jsonwebtoken");

function verifyToken() {}
const generateToken = () => {};
class AuthService {}

export function login() {}
export const authenticate = () => {};
'''

TSX_SAMPLE = '''\
import React from "react";

export function Home(): JSX.Element {
  return <div />;
}

export class Page {}
'''


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _meta(relative: str, file_type: str = "source") -> dict:
    return {
        "path": relative.replace("\\", "/"),
        "extension": Path(relative).suffix.lower(),
        "file_type": file_type,
        "size": 1,
    }


class CodeParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.analyzer = CodeAnalyzer()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        _write(self.root, "auth/service.py", PYTHON_SAMPLE)
        _write(self.root, "auth/jwt.js", JS_SAMPLE)
        _write(self.root, "frontend/Home.tsx", TSX_SAMPLE)
        _write(self.root, "broken.py", "def broken(\n")
        _write(self.root, "README.md", "# docs\n")
        _write(self.root, "src/app.py", "print('app')\n")
        _write(self.root, "tests/test_auth.py", "def test_auth():\n    pass\n")
        _write(self.root, "docs/README.md", "# Demo\n")
        _write(self.root, "package.json", "{}\n")
        _write(self.root, "debug.lock", "lock\n")
        _write(self.root, "image.png", "fake-png\n")
        _write(self.root, "__pycache__/dummy.pyc", "pyc\n")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_01_python_imports_are_extracted(self) -> None:
        result = self.analyzer.analyze_file(self.root, _meta("auth/service.py"))
        self.assertIn("os", result.imports)
        self.assertIn("json", result.imports)

    def test_02_python_functions_are_extracted(self) -> None:
        result = self.analyzer.analyze_file(self.root, _meta("auth/service.py"))
        self.assertIn("helper", result.functions)
        self.assertIn("login", result.functions)

    def test_03_python_classes_are_extracted(self) -> None:
        result = self.analyzer.analyze_file(self.root, _meta("auth/service.py"))
        self.assertEqual(result.classes, ["AuthService"])

    def test_04_python_async_functions_are_handled(self) -> None:
        result = self.analyzer.analyze_file(self.root, _meta("auth/service.py"))
        self.assertIn("fetch_user", result.functions)
        self.assertIn("fetch_user", result.symbols)

    def test_05_python_syntax_errors_do_not_crash(self) -> None:
        result = self.analyzer.analyze_file(self.root, _meta("broken.py"))
        self.assertTrue(result.analysis_supported)
        self.assertIsNotNone(result.analysis_error)
        self.assertGreater(result.line_count, 0)
        self.assertEqual(result.functions, [])
        self.assertEqual(result.imports, [])

    def test_06_javascript_imports_are_extracted(self) -> None:
        result = self.analyzer.analyze_file(self.root, _meta("auth/jwt.js"))
        self.assertIn("jsonwebtoken", result.imports)
        self.assertIn("./foo", result.imports)

    def test_07_javascript_require_dependencies_are_extracted(self) -> None:
        result = self.analyzer.analyze_file(self.root, _meta("auth/jwt.js"))
        self.assertIn("./auth", result.imports)
        self.assertIn("jsonwebtoken", result.imports)

    def test_08_javascript_functions_are_extracted(self) -> None:
        result = self.analyzer.analyze_file(self.root, _meta("auth/jwt.js"))
        self.assertIn("verifyToken", result.functions)
        self.assertIn("generateToken", result.functions)
        self.assertIn("login", result.functions)
        self.assertIn("authenticate", result.functions)

    def test_09_javascript_classes_are_extracted(self) -> None:
        result = self.analyzer.analyze_file(self.root, _meta("auth/jwt.js"))
        self.assertIn("AuthService", result.classes)

    def test_10_typescript_tsx_is_classified(self) -> None:
        result = self.analyzer.analyze_file(self.root, _meta("frontend/Home.tsx"))
        self.assertEqual(result.language, "typescript")
        self.assertTrue(result.analysis_supported)
        self.assertIn("react", result.imports)
        self.assertIn("Home", result.functions)
        self.assertIn("Page", result.classes)

    def test_11_unsupported_extensions_are_flagged(self) -> None:
        result = self.analyzer.analyze_file(self.root, _meta("README.md", "other"))
        self.assertEqual(result.language, "unknown")
        self.assertFalse(result.analysis_supported)
        self.assertGreaterEqual(result.line_count, 1)
        self.assertEqual(result.functions, [])

    def test_12_missing_files_are_handled(self) -> None:
        result = self.analyzer.analyze_file(self.root, _meta("missing.py"))
        self.assertIsNotNone(result.analysis_error)
        self.assertIn("not found", result.analysis_error.lower())
        self.assertEqual(result.line_count, 0)

    def test_13_cannot_read_outside_project_root(self) -> None:
        outside = Path(self.temp.name).resolve().parent / "contextforge_outside_secret.py"
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        outside.write_text("SECRET = 1\n", encoding="utf-8")
        result = self.analyzer.analyze_file(
            self.root,
            {
                "path": "../" + outside.name,
                "extension": ".py",
                "file_type": "source",
                "size": 1,
            },
        )
        self.assertIsNotNone(result.analysis_error)
        self.assertIn("outside", result.analysis_error.lower())
        self.assertEqual(result.imports, [])
        self.assertEqual(result.functions, [])

    def test_14_output_is_deterministic(self) -> None:
        first = self.analyzer.analyze_file(self.root, _meta("auth/jwt.js"))
        second = self.analyzer.analyze_file(self.root, _meta("auth/jwt.js"))
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertIsInstance(first, FileAnalysis)

    def test_15_scanner_filter_analyzer_integration(self) -> None:
        scan = RepositoryScanner(self.root).scan()
        filtered = FileFilter().filter(scan)
        analyses = self.analyzer.analyze_files(self.root, filtered)
        by_path = {item.path: item for item in analyses}

        self.assertIn("src/app.py", by_path)
        self.assertIn("auth/jwt.js", by_path)
        self.assertIn("tests/test_auth.py", by_path)
        self.assertIn("docs/README.md", by_path)
        self.assertIn("package.json", by_path)
        self.assertNotIn("debug.lock", by_path)
        self.assertNotIn("image.png", by_path)

        self.assertEqual(by_path["src/app.py"].language, "python")
        self.assertTrue(by_path["src/app.py"].analysis_supported)
        self.assertEqual(by_path["auth/jwt.js"].language, "javascript")
        self.assertTrue(by_path["auth/jwt.js"].analysis_supported)
        self.assertFalse(by_path["docs/README.md"].analysis_supported)
        self.assertFalse(by_path["package.json"].analysis_supported)
        self.assertGreater(by_path["tests/test_auth.py"].line_count, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
