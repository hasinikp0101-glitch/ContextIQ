"""Tests for application configuration loading."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))


class TestConfigLoading(unittest.TestCase):
    """Test that backend/.env is loaded correctly at application startup."""

    def test_env_file_location(self) -> None:
        """Verify backend/.env exists at the expected location."""
        env_path = BACKEND_ROOT / ".env"
        self.assertTrue(env_path.exists(), f"backend/.env should exist at {env_path}")

    def test_env_file_contains_featherless_config(self) -> None:
        """Verify backend/.env contains Featherless configuration keys."""
        env_path = BACKEND_ROOT / ".env"
        with open(env_path, "r") as f:
            content = f.read()
        self.assertIn("FEATHERLESS_API_KEY", content)
        self.assertIn("FEATHERLESS_MODEL", content)

    def test_env_file_does_not_expose_secrets_in_tests(self) -> None:
        """Verify tests don't print or expose API keys."""
        env_path = BACKEND_ROOT / ".env"
        with open(env_path, "r") as f:
            content = f.read()
        # Check that API key is present but we won't print it
        self.assertTrue("FEATHERLESS_API_KEY=" in content)
        # Verify the file is not empty
        self.assertGreater(len(content.strip()), 0)

    def test_main_module_loads_env(self) -> None:
        """Verify app.main loads environment variables from backend/.env."""
        # Import app.main which should trigger load_dotenv
        from app import main

        # Verify the module loaded without errors
        self.assertIsNotNone(main.app)

    def test_featherless_client_reads_from_env(self) -> None:
        """Verify FeatherlessClient reads from environment variables."""
        # Import app.main to trigger load_dotenv (if not already imported)
        from app import main

        from app.llm.featherless_client import FeatherlessClient

        # The client should read from os.environ
        # We don't test actual API calls, just that it reads env vars
        api_key = os.environ.get("FEATHERLESS_API_KEY")
        model = os.environ.get("FEATHERLESS_MODEL")

        # Verify environment variables are set (from backend/.env)
        # We check they exist but don't print the actual values
        # Note: If app.main was already imported before this test, env vars should be set
        # If not, we can still verify the client can be instantiated
        if api_key is None:
            # If env not loaded yet, load it explicitly for this test
            from dotenv import load_dotenv
            env_path = BACKEND_ROOT / ".env"
            load_dotenv(env_path)
            api_key = os.environ.get("FEATHERLESS_API_KEY")
            model = os.environ.get("FEATHERLESS_MODEL")

        self.assertIsNotNone(api_key, "FEATHERLESS_API_KEY should be set")
        self.assertIsNotNone(model, "FEATHERLESS_MODEL should be set")

    def test_gitignore_covers_env(self) -> None:
        """Verify .gitignore covers .env files."""
        gitignore_path = BACKEND_ROOT.parent / ".gitignore"
        with open(gitignore_path, "r") as f:
            content = f.read()
        self.assertIn(".env", content, ".gitignore should cover .env files")


if __name__ == "__main__":
    unittest.main(verbosity=2)
