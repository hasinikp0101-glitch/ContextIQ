"""Unit and integration tests for ContextForge FastAPI endpoints."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from fastapi import HTTPException

from app.api.routes import analyze_project, health_check, optimize_context
from app.api.schemas import (
    CompressorOptionsRequest,
    ContextOptimizeRequest,
    HealthResponse,
    PricingConfigRequest,
    ProjectAnalyzeRequest,
)
from app.main import app, home


def _write(root: Path, relative: str, content: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


class ApiEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_01_root_home_endpoint(self) -> None:
        res = home()
        self.assertEqual(res, {"message": "ContextForge backend is running!"})

    def test_02_health_endpoint(self) -> None:
        res = health_check()
        self.assertIsInstance(res, HealthResponse)
        self.assertEqual(res.status, "healthy")
        self.assertEqual(res.service, "ContextForge API")
        self.assertEqual(res.version, "0.1.0")

    def test_03_projects_analyze_valid_directory(self) -> None:
        _write(
            self.root,
            "auth/jwt.js",
            "// JWT helper\nimport jwt from 'jsonwebtoken';\nexport function verify() { return true; }\n",
        )
        _write(
            self.root,
            "utils/math.py",
            "# Math utilities\ndef add(a: int, b: int) -> int:\n    return a + b\n",
        )
        _write(self.root, "package.json", '{"name": "test-app"}\n')
        # node_modules should be ignored by scanner
        _write(self.root, "node_modules/pkg/index.js", "console.log(1);")

        req = ProjectAnalyzeRequest(project_path=str(self.root))
        res = analyze_project(req)

        self.assertEqual(res.project_path, str(self.root))
        self.assertGreaterEqual(res.summary.total_files, 3)
        self.assertEqual(res.summary.source_files, 2)
        self.assertEqual(res.summary.config_files, 1)

        paths = [f.path for f in res.files]
        self.assertIn("auth/jwt.js", paths)
        self.assertIn("utils/math.py", paths)

        # Check extracted AST
        jwt_entry = next(f for f in res.files if f.path == "auth/jwt.js")
        self.assertEqual(jwt_entry.language, "javascript")
        self.assertIn("jsonwebtoken", jwt_entry.imports)
        self.assertIn("verify", jwt_entry.functions)

        math_entry = next(f for f in res.files if f.path == "utils/math.py")
        self.assertEqual(math_entry.language, "python")
        self.assertIn("add", math_entry.functions)

    def test_04_projects_analyze_nonexistent_directory(self) -> None:
        req = ProjectAnalyzeRequest(project_path="C:/nonexistent_path_xyz_12345")
        with self.assertRaises(HTTPException) as ctx:
            analyze_project(req)
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("does not exist", ctx.exception.detail)

    def test_05_context_optimize_e2e_pipeline(self) -> None:
        jwt_content = (
            "// Copyright 2026\n"
            "// JWT Verification Service\n"
            "import jwt from 'jsonwebtoken';\n"
            "\n"
            "// Verify authorization token\n"
            "export function verifyToken(token) {\n"
            "  // Validate token signature\n"
            "  return jwt.verify(token, 'secret');\n"
            "}\n"
        )
        mid_content = (
            "// Middleware\n"
            "import { verifyToken } from './jwt';\n"
            "export function authMiddleware(req, res, next) {\n"
            "  return next();\n"
            "}\n"
        )
        home_content = "export default function Home() { return <h1>Home</h1>; }\n"

        _write(self.root, "auth/jwt.js", jwt_content)
        _write(self.root, "auth/middleware.js", mid_content)
        _write(self.root, "frontend/Home.jsx", home_content)

        req = ContextOptimizeRequest(
            project_path=str(self.root),
            query="Why is my JWT authentication failing?",
            token_budget=2000,
        )
        res = optimize_context(req)

        # 1. Query Analysis
        self.assertEqual(res.query_analysis.intent, "debugging")
        self.assertIn("jwt", res.query_analysis.keywords)

        # 2. Selected Files (auth/jwt.js should rank highest)
        selected_paths = [sf.path for sf in res.selected_files]
        self.assertIn("auth/jwt.js", selected_paths)
        self.assertEqual(selected_paths[0], "auth/jwt.js")

        # 3. Optimized Context
        self.assertIn("===== FILE: auth/jwt.js =====", res.optimized_context)
        self.assertIn("export function verifyToken(token)", res.optimized_context)
        # Verify comment compression took place
        self.assertNotIn("// JWT Verification Service", res.optimized_context)
        self.assertNotIn("// Validate token signature", res.optimized_context)

        # 4. Metrics
        self.assertGreater(res.metrics.original_tokens, res.metrics.optimized_tokens)
        self.assertGreater(res.metrics.tokens_saved, 0)
        self.assertGreater(res.metrics.reduction_percentage, 0.0)
        self.assertLess(res.metrics.compression_ratio, 1.0)
        self.assertGreater(res.metrics.characters_saved, 0)

    def test_06_context_optimize_with_pricing(self) -> None:
        _write(
            self.root,
            "service.py",
            "def handler():\n    # Todo comment\n    return True\n" * 20,
        )
        pricing = PricingConfigRequest(input_price_per_1k_tokens=0.002, currency="USD")
        req = ContextOptimizeRequest(
            project_path=str(self.root),
            query="fix handler",
            token_budget=4000,
            pricing=pricing,
        )
        res = optimize_context(req)

        self.assertIsNotNone(res.metrics.estimated_original_cost)
        self.assertIsNotNone(res.metrics.estimated_optimized_cost)
        self.assertIsNotNone(res.metrics.estimated_cost_savings)
        self.assertGreaterEqual(res.metrics.estimated_cost_savings, 0.0)
        self.assertEqual(res.metrics.currency, "USD")

    def test_07_context_optimize_empty_query(self) -> None:
        _write(self.root, "app.py", "print('hello world')\n")
        req = ContextOptimizeRequest(
            project_path=str(self.root),
            query="",
            token_budget=1000,
        )
        res = optimize_context(req)
        self.assertEqual(res.total_selected, 1)
        self.assertIn("app.py", res.selected_files[0].path)

    def test_08_context_optimize_zero_budget(self) -> None:
        _write(self.root, "app.py", "print('hello world')\n")
        req = ContextOptimizeRequest(
            project_path=str(self.root),
            query="run app",
            token_budget=0,
        )
        res = optimize_context(req)
        self.assertEqual(res.total_selected, 0)
        self.assertEqual(res.optimized_context, "")
        self.assertEqual(res.metrics.optimized_tokens, 0)

    def test_09_context_optimize_nonexistent_path(self) -> None:
        req = ContextOptimizeRequest(
            project_path="C:/nonexistent_path_xyz_12345",
            query="test",
        )
        with self.assertRaises(HTTPException) as ctx:
            optimize_context(req)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_10_context_optimize_all_filtered(self) -> None:
        # Repository containing only binary media
        binary_file = self.root / "logo.png"
        binary_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")
        req = ContextOptimizeRequest(
            project_path=str(self.root),
            query="test query",
            token_budget=1000,
        )
        res = optimize_context(req)
        self.assertEqual(res.total_selected, 0)
        self.assertEqual(res.optimized_context, "")

    def test_11_custom_compressor_options(self) -> None:
        _write(
            self.root,
            "app.js",
            "// Keep this comment\nconst a = 1;\n",
        )
        req = ContextOptimizeRequest(
            project_path=str(self.root),
            query="find app",
            compressor_options=CompressorOptionsRequest(strip_comments=False),
        )
        res = optimize_context(req)
        self.assertIn("// Keep this comment", res.optimized_context)

    def test_12_schema_serialization(self) -> None:
        req = ContextOptimizeRequest(
            project_path="./sample",
            query="debugging jwt",
            token_budget=2000,
            pricing=PricingConfigRequest(input_price_per_1k_tokens=0.0015),
            compressor_options=CompressorOptionsRequest(strip_comments=True),
        )
        dumped = req.model_dump()
        reloaded = ContextOptimizeRequest.model_validate(dumped)
        self.assertEqual(req.query, reloaded.query)
        self.assertEqual(req.token_budget, reloaded.token_budget)
        self.assertEqual(
            req.pricing.input_price_per_1k_tokens,
            reloaded.pricing.input_price_per_1k_tokens,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
