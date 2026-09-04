"""Deterministic tests for Query Analyzer and Relevance Scorer."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.analyzer.code_parser import CodeAnalyzer, FileAnalysis
from app.relevance.query_analyzer import QueryAnalyzer
from app.relevance.scorer import RelevanceScorer


JWT_JS = '''\
import jwt from "jsonwebtoken";

function verifyToken() {}
const generateToken = () => {};
class AuthService {}

export function login() {}
'''

HOME_JSX = '''\
import React from "react";

function renderHome() {
  return <div />;
}

export function Navbar() {}
export class Dashboard {}
'''

DB_JS = '''\
const mongoose = require("mongoose");

function connectDatabase() {}
async function runQuery() {}
'''

SCHEMA_SQL = '''\
CREATE TABLE users (
  id INTEGER PRIMARY KEY
);
'''

ENV_PY = '''\
import os
from dotenv import load_dotenv

def load_environment():
    return os.getenv("SECRET")
'''


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _meta(relative: str) -> dict:
    return {
        "path": relative.replace("\\", "/"),
        "extension": Path(relative).suffix.lower(),
        "file_type": "source",
        "size": 1,
    }


class RelevanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        _write(self.root, "auth/jwt.js", JWT_JS)
        _write(self.root, "frontend/Home.jsx", HOME_JSX)
        _write(self.root, "database/connection.js", DB_JS)
        _write(self.root, "database/schema.sql", SCHEMA_SQL)
        _write(self.root, "config/env.py", ENV_PY)
        self.analyzer = CodeAnalyzer()
        self.queries = QueryAnalyzer()
        self.scorer = RelevanceScorer(self.queries)
        self.files = {
            relative: self.analyzer.analyze_file(self.root, _meta(relative))
            for relative in (
                "auth/jwt.js",
                "frontend/Home.jsx",
                "database/connection.js",
                "database/schema.sql",
                "config/env.py",
            )
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_01_jwt_query_ranks_auth_above_frontend(self) -> None:
        ranked = self.scorer.rank(
            "Why is my JWT authentication failing?",
            [self.files["auth/jwt.js"], self.files["frontend/Home.jsx"]],
        )
        self.assertEqual(ranked[0].path, "auth/jwt.js")
        self.assertEqual(ranked[1].path, "frontend/Home.jsx")
        self.assertGreater(ranked[0].score, ranked[1].score)

    def test_02_authentication_terms_are_recognized(self) -> None:
        analysis = self.queries.analyze("Why is my JWT authentication failing?")
        self.assertEqual(analysis.intent, "debugging")
        self.assertIn("authentication", analysis.topics)
        self.assertIn("jwt", analysis.keywords)
        self.assertIn("authentication", analysis.keywords)
        self.assertIn("failing", analysis.keywords)
        self.assertIn("jwt", analysis.technical_terms)
        self.assertIn("authentication", analysis.technical_terms)
        self.assertIn("diagnose", analysis.actions)

    def test_03_database_query_ranks_database_files_higher(self) -> None:
        ranked = self.scorer.rank(
            "Why are my database queries slow?",
            [
                self.files["database/connection.js"],
                self.files["database/schema.sql"],
                self.files["frontend/Home.jsx"],
            ],
        )
        self.assertEqual(ranked[-1].path, "frontend/Home.jsx")
        self.assertIn(ranked[0].path, {"database/connection.js", "database/schema.sql"})
        self.assertGreater(ranked[0].score, ranked[-1].score)

    def test_04_import_relevance_works(self) -> None:
        ranked = self.scorer.rank(
            "JWT authentication failing",
            [self.files["auth/jwt.js"], self.files["frontend/Home.jsx"]],
        )
        jwt_result = next(item for item in ranked if item.path == "auth/jwt.js")
        self.assertGreater(jwt_result.signal_scores["imports"], 0)
        self.assertTrue(any("jsonwebtoken" in signal for signal in jwt_result.matched_signals))

    def test_05_path_relevance_works(self) -> None:
        ranked = self.scorer.rank(
            "JWT authentication failing",
            [self.files["auth/jwt.js"], self.files["frontend/Home.jsx"]],
        )
        jwt_result = next(item for item in ranked if item.path == "auth/jwt.js")
        home = next(item for item in ranked if item.path == "frontend/Home.jsx")
        self.assertGreater(jwt_result.signal_scores["path"], home.signal_scores["path"])
        self.assertTrue(any("jwt" in signal.lower() or "auth" in signal.lower() for signal in jwt_result.matched_signals))

    def test_06_function_symbol_relevance_works(self) -> None:
        ranked = self.scorer.rank(
            "Why is JWT token verification failing?",
            [self.files["auth/jwt.js"], self.files["frontend/Home.jsx"]],
        )
        jwt_result = next(item for item in ranked if item.path == "auth/jwt.js")
        home = next(item for item in ranked if item.path == "frontend/Home.jsx")
        self.assertGreater(jwt_result.signal_scores["symbols"], home.signal_scores["symbols"])
        self.assertTrue(
            any("verifyToken" in signal or "generateToken" in signal for signal in jwt_result.matched_signals)
        )

    def test_07_intent_classification_works(self) -> None:
        jwt = self.queries.analyze("Why is my JWT authentication failing?")
        slow = self.queries.analyze("Why are my database queries slow?")
        api = self.queries.analyze("Why is the login API returning 401?")
        test = self.queries.analyze("How do I test this function?")
        env = self.queries.analyze("Why isn't my environment variable loading?")
        self.assertEqual(jwt.intent, "debugging")
        self.assertIn("authentication", jwt.topics)
        self.assertEqual(slow.intent, "performance")
        self.assertIn("database", slow.topics)
        self.assertEqual(api.intent, "debugging")
        self.assertIn("api", api.topics)
        self.assertIn("authentication", api.topics)
        self.assertEqual(test.intent, "testing")
        self.assertEqual(env.intent, "debugging")
        self.assertIn("configuration", env.topics)

    def test_08_empty_query_is_handled_safely(self) -> None:
        for query in ("", "   ", "the a an is"):
            ranked = self.scorer.rank(query, [self.files["auth/jwt.js"]])
            self.assertEqual(ranked[0].score, 0)
            self.assertEqual(ranked[0].matched_signals, [])
            self.assertIn("no usable terms", ranked[0].reason.lower())

    def test_09_unknown_technical_terms_do_not_crash(self) -> None:
        analysis = self.queries.analyze("Why is the frobnicator widget failing?")
        ranked = self.scorer.rank(analysis, [self.files["auth/jwt.js"]])
        self.assertIn("frobnicator", analysis.keywords)
        self.assertEqual(len(ranked), 1)
        self.assertGreaterEqual(ranked[0].score, 0)

    def test_10_scores_stay_between_0_and_100(self) -> None:
        ranked = self.scorer.rank(
            "Why is my JWT authentication failing?",
            list(self.files.values()),
        )
        for item in ranked:
            self.assertGreaterEqual(item.score, 0)
            self.assertLessEqual(item.score, 100)
            for value in item.signal_scores.values():
                self.assertGreaterEqual(value, 0)
                self.assertLessEqual(value, 100)

    def test_11_results_are_sorted_descending(self) -> None:
        ranked = self.scorer.rank(
            "Why is my JWT authentication failing?",
            list(self.files.values()),
        )
        scores = [item.score for item in ranked]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_12_ties_are_deterministic(self) -> None:
        empty_a = FileAnalysis(path="z_empty.py", language="python", analysis_supported=True)
        empty_b = FileAnalysis(path="a_empty.py", language="python", analysis_supported=True)
        first = self.scorer.rank("database connection failing", [empty_a, empty_b])
        second = self.scorer.rank("database connection failing", [empty_b, empty_a])
        self.assertEqual([item.path for item in first], [item.path for item in second])
        self.assertEqual(first[0].path, "a_empty.py")

    def test_13_duplicate_terms_do_not_multiply_scores(self) -> None:
        once = self.scorer.rank("jwt authentication", [self.files["auth/jwt.js"]])[0]
        many = self.scorer.rank("jwt jwt jwt jwt authentication", [self.files["auth/jwt.js"]])[0]
        self.assertEqual(once.score, many.score)
        self.assertEqual(once.signal_scores, many.signal_scores)

    def test_14_incomplete_file_analysis_is_safe(self) -> None:
        ranked = self.scorer.rank(
            "Why is JWT authentication failing?",
            [{"path": "mystery.bin"}],
        )
        self.assertEqual(len(ranked), 1)
        self.assertGreaterEqual(ranked[0].score, 0)
        self.assertLessEqual(ranked[0].score, 100)
        error_file = FileAnalysis(
            path="auth/broken.py",
            language="python",
            analysis_supported=True,
            analysis_error="Python syntax error: unexpected EOF",
        )
        scored = self.scorer.score_file("JWT authentication failing", error_file)
        self.assertTrue(any("error" in signal for signal in scored.matched_signals))

    def test_15_query_analyzer_is_deterministic(self) -> None:
        query = "Why is my JWT authentication failing?"
        self.assertEqual(
            self.queries.analyze(query).to_dict(),
            self.queries.analyze(query).to_dict(),
        )

    def test_16_jwt_maps_to_jsonwebtoken(self) -> None:
        ranked = self.scorer.rank("JWT failing", [self.files["auth/jwt.js"]])[0]
        self.assertGreater(ranked.signal_scores["imports"], 0)
        self.assertTrue(any("jsonwebtoken" in signal for signal in ranked.matched_signals))
        db = self.scorer.rank("database connection failing", [self.files["database/connection.js"]])[0]
        self.assertTrue(any("mongoose" in signal for signal in db.matched_signals))

    def test_17_explanations_contain_matched_evidence(self) -> None:
        ranked = self.scorer.rank(
            "Why is my JWT authentication failing?",
            [self.files["auth/jwt.js"]],
        )[0]
        self.assertTrue(ranked.matched_signals)
        blob = " ".join(ranked.matched_signals).lower()
        self.assertTrue("jwt" in blob or "auth" in blob)
        self.assertIn("jsonwebtoken", blob)
        self.assertTrue(ranked.reason)
        self.assertIn("path", ranked.signal_scores)
        self.assertIn("imports", ranked.signal_scores)
        self.assertIn("symbols", ranked.signal_scores)
        self.assertIn("query_terms", ranked.signal_scores)
        self.assertIn("intent", ranked.signal_scores)

    def test_18_end_to_end_query_analyzer_code_analyzer_scorer(self) -> None:
        query = "Why is my JWT authentication failing?"
        analysis = self.queries.analyze(query)
        file_analyses = list(self.files.values())
        ranked = self.scorer.rank(analysis, file_analyses)
        self.assertEqual(analysis.original_query, query)
        self.assertEqual(ranked[0].path, "auth/jwt.js")
        self.assertGreater(ranked[0].score, 0)
        self.assertTrue(ranked[0].matched_signals)
        self.assertEqual(
            [item.path for item in ranked],
            [item.path for item in self.scorer.rank(analysis, file_analyses)],
        )

    def test_19_long_query_is_capped_and_safe(self) -> None:
        long_query = "jwt authentication failing " + (" widget" * 200)
        ranked = self.scorer.rank(long_query, [self.files["auth/jwt.js"]])
        self.assertEqual(len(ranked), 1)
        self.assertGreaterEqual(ranked[0].score, 0)

    def test_20_jwt_still_matches_jsonwebtoken_concept(self) -> None:
        ranked = self.scorer.rank("JWT failing", [self.files["auth/jwt.js"]])[0]
        self.assertGreater(ranked.signal_scores["imports"], 0)
        self.assertTrue(any("jsonwebtoken" in signal for signal in ranked.matched_signals))

    def test_21_unrelated_token_containing_jwt_does_not_match(self) -> None:
        decoy = FileAnalysis(
            path="frontend/foojwtbar.jsx",
            language="javascript",
            analysis_supported=True,
            imports=["foojwtbar-utils"],
            functions=["foojwtbar"],
            classes=[],
            symbols=["foojwtbar"],
            exports=["foojwtbar"],
        )
        ranked = self.scorer.rank(
            "Why is JWT failing?",
            [decoy, self.files["auth/jwt.js"]],
        )
        by_path = {item.path: item for item in ranked}
        self.assertEqual(by_path["auth/jwt.js"].path, "auth/jwt.js")
        self.assertGreater(by_path["auth/jwt.js"].score, by_path["frontend/foojwtbar.jsx"].score)
        self.assertEqual(by_path["frontend/foojwtbar.jsx"].signal_scores["path"], 0)
        self.assertEqual(by_path["frontend/foojwtbar.jsx"].signal_scores["imports"], 0)
        self.assertEqual(by_path["frontend/foojwtbar.jsx"].signal_scores["symbols"], 0)
        self.assertFalse(
            any("jsonwebtoken" in signal for signal in by_path["frontend/foojwtbar.jsx"].matched_signals)
        )

    def test_22_auth_database_api_matching_still_works(self) -> None:
        auth_ranked = self.scorer.rank(
            "Why is my JWT authentication failing?",
            [self.files["auth/jwt.js"], self.files["frontend/Home.jsx"]],
        )
        self.assertEqual(auth_ranked[0].path, "auth/jwt.js")

        db_ranked = self.scorer.rank(
            "Why are my database queries slow?",
            [self.files["database/connection.js"], self.files["frontend/Home.jsx"]],
        )
        self.assertEqual(db_ranked[0].path, "database/connection.js")
        self.assertTrue(any("mongoose" in signal for signal in db_ranked[0].matched_signals))

        api_file = FileAnalysis(
            path="api/routes.js",
            language="javascript",
            analysis_supported=True,
            imports=["express"],
            functions=["createRouter"],
            classes=[],
            symbols=["createRouter"],
            exports=["createRouter"],
        )
        api_ranked = self.scorer.rank(
            "Why is the login API returning 401?",
            [api_file, self.files["frontend/Home.jsx"]],
        )
        self.assertEqual(api_ranked[0].path, "api/routes.js")
        self.assertGreater(api_ranked[0].score, api_ranked[1].score)

    def test_23_duplicate_terms_still_do_not_inflate_scores(self) -> None:
        once = self.scorer.rank("jwt authentication", [self.files["auth/jwt.js"]])[0]
        many = self.scorer.rank(
            "jwt jwt jwt jwt authentication",
            [self.files["auth/jwt.js"]],
        )[0]
        self.assertEqual(once.score, many.score)
        self.assertEqual(once.signal_scores, many.signal_scores)


if __name__ == "__main__":
    unittest.main(verbosity=2)
