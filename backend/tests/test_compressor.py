"""Tests for ContextCompressor."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.compressor import (
    CompressedFile,
    CompressionMetrics,
    CompressionResult,
    CompressorOptions,
    ContextCompressor,
)
from app.optimizer.selector import SelectedFile, SelectionResult


class ContextCompressorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.compressor = ContextCompressor()

    def test_01_empty_context(self) -> None:
        for empty_val in [None, "", "   \n\n  \t  "]:
            result = self.compressor.compress(empty_val)
            self.assertEqual(result.compressed_context, "")
            self.assertEqual(result.metrics.original_tokens, 0)
            self.assertEqual(result.metrics.compressed_tokens, 0)
            self.assertEqual(result.metrics.tokens_saved, 0)
            self.assertEqual(result.metrics.saving_percentage, 0.0)
            self.assertEqual(result.metrics.compression_ratio, 1.0)
            self.assertEqual(result.files, [])

        # Empty SelectionResult
        empty_sel = SelectionResult(token_budget=100, total_candidate_files=0)
        res_sel = self.compressor.compress(empty_sel)
        self.assertEqual(res_sel.compressed_context, "")
        self.assertEqual(res_sel.metrics.original_tokens, 0)

    def test_02_whitespace_and_blank_line_collapse(self) -> None:
        code = (
            "def foo():    \n"
            "    return 1    \n"
            "\n"
            "\n"
            "\n"
            "\n"
            "def bar():\n"
            "    return 2\n"
        )
        result = self.compressor.compress(code)
        expected = "def foo():\n    return 1\n\ndef bar():\n    return 2"
        self.assertEqual(result.compressed_context, expected)
        self.assertGreater(result.metrics.tokens_saved, 0)
        self.assertGreater(result.metrics.saving_percentage, 0)

    def test_03_python_comment_stripping_and_pragma_preservation(self) -> None:
        code = (
            "#!/usr/bin/env python3\n"
            "# Regular comment explaining module\n"
            "# Another comment\n"
            "import os\n"
            "\n"
            "# Function comment\n"
            "def run():\n"
            "    x = 10  # inline comment\n"
            "    # type: ignore\n"
            "    return x\n"
        )
        res = self.compressor.compress_file("script.py", code)
        self.assertIn("#!/usr/bin/env python3", res.compressed_content)
        self.assertIn("import os", res.compressed_content)
        self.assertIn("def run():", res.compressed_content)
        self.assertIn("# type: ignore", res.compressed_content)
        self.assertNotIn("# Regular comment explaining module", res.compressed_content)
        self.assertNotIn("# Function comment", res.compressed_content)
        # Inline comment on code line is preserved
        self.assertIn("x = 10  # inline comment", res.compressed_content)

    def test_04_javascript_comment_stripping(self) -> None:
        code = (
            "// Single-line comment at top\n"
            "import jwt from 'jsonwebtoken';\n"
            "\n"
            "/* Single line block comment */\n"
            "/* Multi-line\n"
            "   block comment\n"
            "*/\n"
            "// @ts-ignore\n"
            "export function verify(token) {\n"
            "  // check token\n"
            "  return true;\n"
            "}\n"
        )
        res = self.compressor.compress_file("auth/jwt.js", code)
        self.assertIn("import jwt from 'jsonwebtoken';", res.compressed_content)
        self.assertIn("// @ts-ignore", res.compressed_content)
        self.assertIn("export function verify(token) {", res.compressed_content)
        self.assertIn("return true;", res.compressed_content)
        self.assertNotIn("Single-line comment at top", res.compressed_content)
        self.assertNotIn("Single line block comment", res.compressed_content)
        self.assertNotIn("Multi-line", res.compressed_content)
        self.assertNotIn("// check token", res.compressed_content)

    def test_05_license_header_removal(self) -> None:
        code = (
            "/*\n"
            " * Copyright (c) 2026 ContextForge Contributors\n"
            " * SPDX-License-Identifier: MIT\n"
            " * All rights reserved.\n"
            " */\n"
            "export const PORT = 8080;\n"
        )
        res = self.compressor.compress_file("config.ts", code)
        self.assertEqual(res.compressed_content, "export const PORT = 8080;")
        self.assertNotIn("Copyright", res.compressed_content)
        self.assertNotIn("SPDX", res.compressed_content)

    def test_06_code_structure_and_indentation_preserved(self) -> None:
        code = (
            "class AuthService:\n"
            "    def __init__(self, secret: str):\n"
            "        self.secret = secret\n"
            "\n"
            "    def authenticate(self, user: str) -> bool:\n"
            "        if not user:\n"
            "            return False\n"
            "        return True\n"
        )
        result = self.compressor.compress_file("auth.py", code)
        # Indentation should be exactly 4 spaces and 8 spaces
        lines = result.compressed_content.split("\n")
        self.assertTrue(lines[1].startswith("    def __init__"))
        self.assertTrue(lines[2].startswith("        self.secret"))
        self.assertTrue(lines[5].startswith("        if not user:"))
        self.assertTrue(lines[6].startswith("            return False"))

    def test_07_token_metrics_calculation(self) -> None:
        original = (
            "// Copyright 2026\n"
            "// Very detailed explanation\n"
            "// Line 1\n"
            "// Line 2\n"
            "// Line 3\n"
            "\n"
            "\n"
            "const x = 1;\n"
        )
        result = self.compressor.compress(original)
        metrics = result.metrics
        self.assertGreater(metrics.original_tokens, metrics.compressed_tokens)
        self.assertEqual(metrics.tokens_saved, metrics.original_tokens - metrics.compressed_tokens)
        self.assertGreater(metrics.saving_percentage, 0.0)
        self.assertLessEqual(metrics.compression_ratio, 1.0)
        self.assertGreater(metrics.lines_removed, 0)
        self.assertEqual(metrics.original_characters, len(original))
        self.assertEqual(metrics.compressed_characters, len(result.compressed_context))

    def test_08_selection_result_integration(self) -> None:
        file1 = SelectedFile(
            path="auth/jwt.js",
            relevance_score=90,
            token_count=50,
            selection_order=1,
            content="// Verify token\nfunction verify() {\n  return true;\n}\n",
        )
        file2 = SelectedFile(
            path="auth/middleware.js",
            relevance_score=80,
            token_count=30,
            selection_order=2,
            content="// Middleware\nconst a = 1;\n",
        )
        sel_result = SelectionResult(
            token_budget=1000,
            total_candidate_files=2,
            selected_files=[file1, file2],
            selected_tokens=80,
            remaining_tokens=920,
            context=(
                "===== FILE: auth/jwt.js =====\n"
                "// Verify token\nfunction verify() {\n  return true;\n}\n\n"
                "===== FILE: auth/middleware.js =====\n"
                "// Middleware\nconst a = 1;\n"
            ),
        )

        comp_res = self.compressor.compress(sel_result)
        self.assertEqual(len(comp_res.files), 2)
        self.assertEqual(comp_res.files[0].path, "auth/jwt.js")
        self.assertEqual(comp_res.files[1].path, "auth/middleware.js")
        self.assertIn("===== FILE: auth/jwt.js =====", comp_res.compressed_context)
        self.assertIn("===== FILE: auth/middleware.js =====", comp_res.compressed_context)
        self.assertNotIn("// Verify token", comp_res.compressed_context)
        self.assertNotIn("// Middleware", comp_res.compressed_context)
        self.assertIn("function verify() {\n  return true;\n}", comp_res.compressed_context)
        self.assertIn("const a = 1;", comp_res.compressed_context)

    def test_09_assembled_context_string_parsing(self) -> None:
        context_str = (
            "===== FILE: src/index.ts =====\n"
            "// App entry\n"
            "console.log('start');\n\n"
            "===== FILE: src/utils.ts =====\n"
            "// Utility functions\n"
            "export const add = (a: number, b: number) => a + b;\n"
        )
        comp_res = self.compressor.compress(context_str)
        self.assertEqual(len(comp_res.files), 2)
        self.assertEqual(comp_res.files[0].path, "src/index.ts")
        self.assertEqual(comp_res.files[1].path, "src/utils.ts")
        self.assertIn("===== FILE: src/index.ts =====", comp_res.compressed_context)
        self.assertIn("===== FILE: src/utils.ts =====", comp_res.compressed_context)
        self.assertNotIn("// App entry", comp_res.compressed_context)
        self.assertNotIn("// Utility functions", comp_res.compressed_context)

    def test_10_crlf_and_lf_consistency(self) -> None:
        lf_code = "function test() {\n  // comment\n  return 42;\n}\n"
        crlf_code = "function test() {\r\n  // comment\r\n  return 42;\r\n}\r\n"

        res_lf = self.compressor.compress(lf_code)
        res_crlf = self.compressor.compress(crlf_code)

        self.assertEqual(res_lf.compressed_context, res_crlf.compressed_context)
        self.assertEqual(res_lf.metrics.compressed_tokens, res_crlf.metrics.compressed_tokens)

    def test_11_very_small_files(self) -> None:
        one_liner = "const a = 1;\n"
        res = self.compressor.compress_file("tiny.js", one_liner)
        self.assertEqual(res.compressed_content, "const a = 1;")
        self.assertGreaterEqual(res.original_tokens, res.compressed_tokens)

    def test_12_malformed_and_edge_inputs(self) -> None:
        # Non-string object
        res_num = self.compressor.compress(12345)  # type: ignore
        self.assertEqual(res_num.compressed_context, "12345")

        # Dict with missing keys
        res_dict = self.compressor.compress({"foo": "bar"})
        self.assertEqual(res_dict.compressed_context, "")

    def test_13_deterministic_output(self) -> None:
        sample = (
            "===== FILE: a.py =====\n"
            "# Header\n"
            "def a(): return 1\n\n"
            "===== FILE: b.py =====\n"
            "# Header\n"
            "def b(): return 2\n"
        )
        first = self.compressor.compress(sample)
        second = self.compressor.compress(sample)
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_14_custom_options(self) -> None:
        code = (
            "# Keep this comment\n"
            "\n"
            "\n"
            "x = 1\n"
        )
        opts = CompressorOptions(strip_comments=False, collapse_blank_lines=False)
        compressor = ContextCompressor(options=opts)
        res = compressor.compress_file("app.py", code)
        self.assertIn("# Keep this comment", res.compressed_content)
        self.assertIn("\n\n\nx = 1", res.compressed_content)

    def test_15_custom_token_counter(self) -> None:
        def word_counter(text: str) -> int:
            return len(text.split())

        compressor = ContextCompressor(count_tokens=word_counter)
        res = compressor.compress("hello world\n// comment\nfoo bar")
        self.assertEqual(compressor.count_tokens("hello world"), 2)
        self.assertGreater(res.metrics.original_tokens, res.metrics.compressed_tokens)
        self.assertEqual(res.metrics.original_tokens, 6)
        self.assertEqual(res.metrics.compressed_tokens, 4)

    def test_16_inline_strings_with_comment_markers_preserved(self) -> None:
        code = (
            'const url = "https://example.com//path";\n'
            'const color = "#ff0000";\n'
            'const pattern = "/* not a comment */";\n'
        )
        res = self.compressor.compress_file("app.js", code)
        self.assertIn('const url = "https://example.com//path";', res.compressed_content)
        self.assertIn('const color = "#ff0000";', res.compressed_content)
        self.assertIn('const pattern = "/* not a comment */";', res.compressed_content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
