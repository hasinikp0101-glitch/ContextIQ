"""Tests for greedy token-budget context selection."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.optimizer.selector import ContextSelector
from app.relevance.scorer import RankedFile


SMALL = "const a = 1;\n"
MEDIUM = "function verifyToken() {\n  return true;\n}\n" * 8
LARGE = ("export function generateToken() {\n  return 'x';\n}\n" * 40)


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _ranked(path: str, score: int) -> RankedFile:
    return RankedFile(
        path=path,
        score=score,
        signal_scores={"path": score, "imports": 0, "symbols": 0, "query_terms": 0, "intent": 0},
        matched_signals=[],
        reason="test rank",
    )


class ContextSelectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        _write(self.root, "auth/jwt.js", MEDIUM)
        _write(self.root, "auth/middleware.js", SMALL)
        _write(self.root, "frontend/Home.jsx", SMALL)
        _write(self.root, "auth/huge.js", LARGE)
        self.selector = ContextSelector()
        self.jwt_tokens = self.selector.count_tokens(
            (self.root / "auth" / "jwt.js").read_text(encoding="utf-8")
        )
        self.mid_tokens = self.selector.count_tokens(
            (self.root / "auth" / "middleware.js").read_text(encoding="utf-8")
        )
        self.home_tokens = self.selector.count_tokens(
            (self.root / "frontend" / "Home.jsx").read_text(encoding="utf-8")
        )
        self.huge_tokens = self.selector.count_tokens(
            (self.root / "auth" / "huge.js").read_text(encoding="utf-8")
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _select(self, budget: int, files: list[RankedFile] | None = None) -> object:
        ranked = files or [
            _ranked("auth/jwt.js", 90),
            _ranked("auth/middleware.js", 80),
            _ranked("frontend/Home.jsx", 10),
        ]
        return self.selector.select(self.root, ranked, budget)

    def test_01_basic_selection(self) -> None:
        budget = self.jwt_tokens + self.mid_tokens + 50
        result = self._select(budget)
        paths = [item.path for item in result.selected_files]
        self.assertIn("auth/jwt.js", paths)
        self.assertGreaterEqual(result.selected_tokens, self.jwt_tokens)
        self.assertLessEqual(result.selected_tokens, budget)

    def test_02_multiple_files_fit_within_budget(self) -> None:
        budget = self.jwt_tokens + self.mid_tokens + self.home_tokens
        result = self._select(budget)
        self.assertEqual(
            [item.path for item in result.selected_files],
            ["auth/jwt.js", "auth/middleware.js", "frontend/Home.jsx"],
        )
        self.assertEqual(result.selected_tokens, budget)
        self.assertEqual(result.remaining_tokens, 0)

    def test_03_token_budget_limits_selection(self) -> None:
        budget = self.jwt_tokens + (self.mid_tokens // 2 if self.mid_tokens > 1 else 0)
        budget = max(self.jwt_tokens, budget)
        if self.mid_tokens == 0:
            budget = self.jwt_tokens
        result = self._select(self.jwt_tokens)
        self.assertEqual([item.path for item in result.selected_files], ["auth/jwt.js"])
        excluded = {item.path for item in result.excluded_files}
        self.assertIn("auth/middleware.js", excluded)
        self.assertTrue(
            all(item.reason == "exceeds token budget" for item in result.excluded_files)
        )

    def test_04_oversized_high_rank_is_skipped_for_smaller_later_files(self) -> None:
        budget = self.mid_tokens + self.home_tokens
        self.assertLess(budget, self.huge_tokens)
        result = self._select(
            budget,
            [
                _ranked("auth/huge.js", 99),
                _ranked("auth/middleware.js", 50),
                _ranked("frontend/Home.jsx", 40),
            ],
        )
        self.assertEqual(
            [item.path for item in result.selected_files],
            ["auth/middleware.js", "frontend/Home.jsx"],
        )
        huge = next(item for item in result.excluded_files if item.path == "auth/huge.js")
        self.assertEqual(huge.reason, "exceeds token budget")
        self.assertEqual(huge.token_count, self.huge_tokens)

    def test_05_exact_budget_boundary(self) -> None:
        budget = self.jwt_tokens + self.mid_tokens
        result = self._select(
            budget,
            [_ranked("auth/jwt.js", 90), _ranked("auth/middleware.js", 80)],
        )
        self.assertEqual(len(result.selected_files), 2)
        self.assertEqual(result.selected_tokens, budget)
        self.assertEqual(result.remaining_tokens, 0)

    def test_06_zero_budget(self) -> None:
        result = self._select(0)
        self.assertEqual(result.token_budget, 0)
        self.assertEqual(result.selected_files, [])
        self.assertEqual(result.selected_tokens, 0)
        self.assertEqual(result.remaining_tokens, 0)
        self.assertEqual(len(result.excluded_files), 3)
        self.assertTrue(
            all(item.reason == "exceeds token budget" for item in result.excluded_files)
        )

    def test_07_negative_budget_is_treated_as_zero(self) -> None:
        result = self._select(-25)
        self.assertEqual(result.token_budget, 0)
        self.assertEqual(result.selected_files, [])
        self.assertEqual(result.selected_tokens, 0)
        self.assertEqual(result.remaining_tokens, 0)

    def test_08_empty_candidates(self) -> None:
        result = self.selector.select(self.root, [], 100)
        self.assertEqual(result.total_candidate_files, 0)
        self.assertEqual(result.selected_files, [])
        self.assertEqual(result.excluded_files, [])
        self.assertEqual(result.selected_tokens, 0)
        self.assertEqual(result.remaining_tokens, 100)
        self.assertEqual(result.context, "")

    def test_09_missing_file(self) -> None:
        result = self.selector.select(
            self.root,
            [_ranked("auth/missing.js", 70)],
            1000,
        )
        self.assertEqual(result.selected_files, [])
        self.assertEqual(len(result.excluded_files), 1)
        self.assertIn("not found", result.excluded_files[0].reason.lower())
        self.assertIsNone(result.excluded_files[0].token_count)

    def test_10_binary_file_is_excluded(self) -> None:
        binary_path = self.root / "assets" / "logo.bin"
        binary_path.parent.mkdir(parents=True, exist_ok=True)
        binary_path.write_bytes(b"png\x00data")
        result = self.selector.select(
            self.root,
            [_ranked("assets/logo.bin", 20)],
            1000,
        )
        self.assertEqual(result.selected_files, [])
        self.assertIn("binary", result.excluded_files[0].reason.lower())

    def test_11_deterministic_ordering(self) -> None:
        budget = self.jwt_tokens + self.mid_tokens + self.home_tokens
        ranked = [
            _ranked("auth/jwt.js", 90),
            _ranked("auth/middleware.js", 80),
            _ranked("frontend/Home.jsx", 10),
        ]
        first = self.selector.select(self.root, ranked, budget)
        second = self.selector.select(self.root, ranked, budget)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(
            [item.selection_order for item in first.selected_files],
            list(range(1, len(first.selected_files) + 1)),
        )

    def test_12_selected_token_total_is_correct(self) -> None:
        budget = self.jwt_tokens + self.mid_tokens + self.home_tokens
        result = self._select(budget)
        summed = sum(item.token_count for item in result.selected_files)
        self.assertEqual(result.selected_tokens, summed)
        self.assertLessEqual(result.selected_tokens, result.token_budget)

    def test_13_remaining_tokens_are_correct(self) -> None:
        extra = 17
        budget = self.jwt_tokens + extra
        result = self._select(budget)
        self.assertEqual(
            result.remaining_tokens,
            result.token_budget - result.selected_tokens,
        )
        self.assertGreaterEqual(result.remaining_tokens, 0)

    def test_14_context_assembly_preserves_boundaries_and_source(self) -> None:
        budget = self.jwt_tokens + self.mid_tokens
        result = self._select(
            budget,
            [_ranked("auth/jwt.js", 90), _ranked("auth/middleware.js", 80)],
        )
        jwt_text = (self.root / "auth" / "jwt.js").read_text(encoding="utf-8")
        mid_text = (self.root / "auth" / "middleware.js").read_text(encoding="utf-8")
        self.assertIn("===== FILE: auth/jwt.js =====", result.context)
        self.assertIn("===== FILE: auth/middleware.js =====", result.context)
        self.assertIn(jwt_text, result.context)
        self.assertIn(mid_text, result.context)
        jwt_pos = result.context.index("===== FILE: auth/jwt.js =====")
        mid_pos = result.context.index("===== FILE: auth/middleware.js =====")
        self.assertLess(jwt_pos, mid_pos)

    def test_15_path_traversal_is_rejected(self) -> None:
        outside = Path(self.temp.name).resolve().parent / "contextforge_selector_secret.js"
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        outside.write_text("SECRET = 1\n", encoding="utf-8")
        result = self.selector.select(
            self.root,
            [_ranked("../" + outside.name, 99)],
            1000,
        )
        self.assertEqual(result.selected_files, [])
        self.assertIn("outside", result.excluded_files[0].reason.lower())
        self.assertNotIn("SECRET", result.context)

    def test_16_tokenization_error_is_handled(self) -> None:
        def boom(_text: str) -> int:
            raise RuntimeError("tokenizer exploded")

        selector = ContextSelector(count_tokens=boom)
        result = selector.select(
            self.root,
            [_ranked("auth/middleware.js", 80)],
            1000,
        )
        self.assertEqual(result.selected_files, [])
        self.assertIn("tokenization error", result.excluded_files[0].reason.lower())

    def test_17_individual_file_larger_than_full_budget(self) -> None:
        budget = max(1, self.huge_tokens // 4)
        self.assertLess(budget, self.huge_tokens)
        result = self._select(
            budget,
            [_ranked("auth/huge.js", 99), _ranked("auth/middleware.js", 40)],
        )
        self.assertNotIn("auth/huge.js", [item.path for item in result.selected_files])
        self.assertEqual(result.excluded_files[0].path, "auth/huge.js")
        self.assertEqual(result.excluded_files[0].reason, "exceeds token budget")
        if self.mid_tokens <= budget:
            self.assertEqual(result.selected_files[0].path, "auth/middleware.js")


if __name__ == "__main__":
    unittest.main(verbosity=2)
