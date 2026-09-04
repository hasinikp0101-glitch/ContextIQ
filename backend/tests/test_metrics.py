"""Tests for Token and Cost Metrics Engine."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.compressor import ContextCompressor
from app.metrics import (
    CostMetrics,
    MetricsEngine,
    OptimizationMetrics,
    PricingConfig,
    TextMetrics,
    TokenMetrics,
)
from app.optimizer.selector import SelectedFile, SelectionResult


class MetricsEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = MetricsEngine()

    def test_01_normal_optimization(self) -> None:
        original = (
            "// Very long comment block\n"
            "// Line 2\n"
            "// Line 3\n"
            "\n"
            "function add(a, b) {\n"
            "  return a + b;\n"
            "}\n"
        )
        optimized = "function add(a, b) {\n  return a + b;\n}"
        metrics = self.engine.calculate(original, optimized)

        self.assertGreater(metrics.original_tokens, metrics.optimized_tokens)
        self.assertEqual(
            metrics.tokens_saved,
            metrics.original_tokens - metrics.optimized_tokens,
        )
        self.assertGreater(metrics.reduction_percentage, 0.0)
        self.assertLess(metrics.compression_ratio, 1.0)
        self.assertGreater(metrics.original_characters, metrics.optimized_characters)
        self.assertEqual(
            metrics.characters_saved,
            metrics.original_characters - metrics.optimized_characters,
        )
        self.assertGreater(metrics.original_lines, metrics.optimized_lines)
        self.assertEqual(
            metrics.lines_saved,
            metrics.original_lines - metrics.optimized_lines,
        )

    def test_02_zero_tokens_and_empty_context(self) -> None:
        for empty_a, empty_b in [("", ""), (None, None), (0, 0)]:
            metrics = self.engine.calculate(empty_a, empty_b)
            self.assertEqual(metrics.original_tokens, 0)
            self.assertEqual(metrics.optimized_tokens, 0)
            self.assertEqual(metrics.tokens_saved, 0)
            self.assertEqual(metrics.reduction_percentage, 0.0)
            self.assertEqual(metrics.compression_ratio, 1.0)
            self.assertEqual(metrics.original_characters, 0)
            self.assertEqual(metrics.characters_saved, 0)
            self.assertEqual(metrics.original_lines, 0)
            self.assertEqual(metrics.lines_saved, 0)

    def test_03_no_optimization_identical_contexts(self) -> None:
        code = "const x = 42;\n"
        metrics = self.engine.calculate(code, code)
        self.assertEqual(metrics.tokens_saved, 0)
        self.assertEqual(metrics.reduction_percentage, 0.0)
        self.assertEqual(metrics.compression_ratio, 1.0)
        self.assertEqual(metrics.characters_saved, 0)
        self.assertEqual(metrics.lines_saved, 0)

    def test_04_optimized_larger_than_original(self) -> None:
        # e.g. 50 original tokens, 100 optimized tokens
        metrics = self.engine.calculate(50, 100)
        self.assertEqual(metrics.original_tokens, 50)
        self.assertEqual(metrics.optimized_tokens, 100)
        self.assertEqual(metrics.tokens_saved, 0)
        self.assertEqual(metrics.reduction_percentage, 0.0)
        self.assertEqual(metrics.compression_ratio, 2.0)

    def test_05_optimization_percentage_and_ratio_formulas(self) -> None:
        # Exact values: 1000 original, 400 optimized
        metrics = self.engine.calculate(1000, 400)
        self.assertEqual(metrics.original_tokens, 1000)
        self.assertEqual(metrics.optimized_tokens, 400)
        self.assertEqual(metrics.tokens_saved, 600)
        self.assertEqual(metrics.reduction_percentage, 60.0)
        self.assertEqual(metrics.compression_ratio, 0.4)

    def test_06_character_metrics(self) -> None:
        orig = "1234567890"
        opt = "12345"
        metrics = self.engine.calculate(orig, opt)
        self.assertEqual(metrics.original_characters, 10)
        self.assertEqual(metrics.optimized_characters, 5)
        self.assertEqual(metrics.characters_saved, 5)

    def test_07_line_metrics(self) -> None:
        orig = "line1\nline2\nline3\nline4\nline5"
        opt = "line1\nline2"
        metrics = self.engine.calculate(orig, opt)
        self.assertEqual(metrics.original_lines, 5)
        self.assertEqual(metrics.optimized_lines, 2)
        self.assertEqual(metrics.lines_saved, 3)

    def test_08_cost_estimation_configurable(self) -> None:
        pricing = PricingConfig(input_price_per_1k_tokens=0.002)  # $0.002 per 1k tokens
        engine = MetricsEngine(pricing=pricing)

        # 10,000 tokens -> $0.020
        # 4,000 tokens  -> $0.008
        # Savings       -> $0.012
        metrics = engine.calculate(10000, 4000)
        self.assertIsNotNone(metrics.cost)
        cost = metrics.cost
        self.assertEqual(cost.input_price_per_1k_tokens, 0.002)
        self.assertAlmostEqual(cost.estimated_original_cost, 0.020, places=6)
        self.assertAlmostEqual(cost.estimated_optimized_cost, 0.008, places=6)
        self.assertAlmostEqual(cost.estimated_cost_savings, 0.012, places=6)
        self.assertEqual(cost.currency, "USD")

    def test_09_cost_estimation_zero_and_negative_rates(self) -> None:
        # Zero rate
        zero_pricing = PricingConfig(input_price_per_1k_tokens=0.0)
        cost_zero = self.engine.calculate_cost(5000, 2000, zero_pricing)
        self.assertEqual(cost_zero.estimated_cost_savings, 0.0)

        # Negative rate clamps to 0.0
        neg_pricing = PricingConfig(input_price_per_1k_tokens=-0.5)
        self.assertEqual(neg_pricing.input_price_per_1k_tokens, 0.0)

        # When optimized > original, cost savings must be 0.0 (no negative savings)
        pricing = PricingConfig(input_price_per_1k_tokens=0.001)
        cost_over = self.engine.calculate_cost(2000, 5000, pricing)
        self.assertEqual(cost_over.estimated_cost_savings, 0.0)

    def test_10_pipeline_object_integration(self) -> None:
        sel_file = SelectedFile(
            path="auth/jwt.js",
            relevance_score=90,
            token_count=100,
            selection_order=1,
            content="// Some comment\nconst secret = 'xyz';\n",
        )
        sel_result = SelectionResult(
            token_budget=500,
            total_candidate_files=1,
            selected_files=[sel_file],
            selected_tokens=100,
            remaining_tokens=400,
            context="===== FILE: auth/jwt.js =====\n// Some comment\nconst secret = 'xyz';\n",
        )

        compressor = ContextCompressor()
        comp_result = compressor.compress(sel_result)

        metrics = self.engine.calculate(sel_result, comp_result)
        self.assertGreater(metrics.original_tokens, metrics.optimized_tokens)
        self.assertGreater(metrics.tokens_saved, 0)
        self.assertIn("===== FILE: auth/jwt.js =====", comp_result.compressed_context)

    def test_11_invalid_and_edge_values(self) -> None:
        # Dict with invalid types
        bad_dict = {"tokens": "not_a_number"}
        metrics = self.engine.calculate(bad_dict, bad_dict)
        self.assertEqual(metrics.original_tokens, 0)
        self.assertEqual(metrics.optimized_tokens, 0)

        # Negative token count clamped to 0
        metrics_neg = self.engine.calculate(-50, -100)
        self.assertEqual(metrics_neg.original_tokens, 0)
        self.assertEqual(metrics_neg.optimized_tokens, 0)

    def test_12_deterministic_results(self) -> None:
        pricing = PricingConfig(input_price_per_1k_tokens=0.0015)
        text_a = "def compute():\n    return 42\n" * 10
        text_b = "def compute():\n    return 42\n" * 5

        run1 = self.engine.calculate(text_a, text_b, pricing).to_dict()
        run2 = self.engine.calculate(text_a, text_b, pricing).to_dict()
        self.assertEqual(run1, run2)

    def test_13_crlf_and_lf_line_counting(self) -> None:
        lf_text = "line1\nline2\nline3"
        crlf_text = "line1\r\nline2\r\nline3"
        m_lf = self.engine.calculate(lf_text, "line1")
        m_crlf = self.engine.calculate(crlf_text, "line1")

        self.assertEqual(m_lf.original_lines, 3)
        self.assertEqual(m_crlf.original_lines, 3)
        self.assertEqual(m_lf.lines_saved, 2)
        self.assertEqual(m_crlf.lines_saved, 2)

    def test_14_custom_token_counter(self) -> None:
        def word_counter(text: str) -> int:
            return len(text.split())

        engine = MetricsEngine(count_tokens=word_counter)
        m = engine.calculate("one two three four five", "one two")
        self.assertEqual(m.original_tokens, 5)
        self.assertEqual(m.optimized_tokens, 2)
        self.assertEqual(m.tokens_saved, 3)

    def test_15_to_dict_serialization(self) -> None:
        pricing = PricingConfig(input_price_per_1k_tokens=0.001)
        m = self.engine.calculate(100, 50, pricing)
        d = m.to_dict()

        # Check flat fields
        self.assertEqual(d["original_tokens"], 100)
        self.assertEqual(d["optimized_tokens"], 50)
        self.assertEqual(d["tokens_saved"], 50)
        self.assertEqual(d["reduction_percentage"], 50.0)
        self.assertEqual(d["compression_ratio"], 0.5)
        self.assertEqual(d["currency"], "USD")
        self.assertAlmostEqual(d["estimated_original_cost"], 0.0001, places=6)

        # Check nested structures
        self.assertIn("tokens", d)
        self.assertIn("text", d)
        self.assertIn("cost", d)


if __name__ == "__main__":
    unittest.main(verbosity=2)
