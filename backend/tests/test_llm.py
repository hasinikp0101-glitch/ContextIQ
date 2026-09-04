"""Unit and integration tests for LLM integration."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.llm.adapter import LLMAdapter, LLMResponse
from app.llm.featherless_client import FeatherlessClient


class TestLLMAdapter(unittest.TestCase):
    """Test the LLM adapter interface."""

    def test_adapter_is_abstract(self) -> None:
        """LLMAdapter should be abstract and not instantiable directly."""
        with self.assertRaises(TypeError):
            LLMAdapter()  # type: ignore


class TestFeatherlessClient(unittest.TestCase):
    """Test the Featherless client implementation."""

    def setUp(self) -> None:
        """Clear environment variables before each test."""
        # Remove API key from environment to test missing key handling
        self.original_api_key = os.environ.get("FEATHERLESS_API_KEY")
        self.original_model = os.environ.get("FEATHERLESS_MODEL")
        if "FEATHERLESS_API_KEY" in os.environ:
            del os.environ["FEATHERLESS_API_KEY"]
        if "FEATHERLESS_MODEL" in os.environ:
            del os.environ["FEATHERLESS_MODEL"]

    def tearDown(self) -> None:
        """Restore environment variables after each test."""
        if self.original_api_key:
            os.environ["FEATHERLESS_API_KEY"] = self.original_api_key
        elif "FEATHERLESS_API_KEY" in os.environ:
            del os.environ["FEATHERLESS_API_KEY"]
        if self.original_model:
            os.environ["FEATHERLESS_MODEL"] = self.original_model
        elif "FEATHERLESS_MODEL" in os.environ:
            del os.environ["FEATHERLESS_MODEL"]

    def test_client_without_api_key_raises_value_error(self) -> None:
        """Client without API key should raise ValueError when calling ask()."""
        client = FeatherlessClient()
        with self.assertRaises(ValueError) as ctx:
            client.ask("context", "query")
        self.assertIn("API key not configured", str(ctx.exception))

    def test_client_with_explicit_api_key(self) -> None:
        """Client should accept explicit API key parameter."""
        client = FeatherlessClient(api_key="test-key")
        self.assertEqual(client.api_key, "test-key")
        self.assertIsNotNone(client._client)

    def test_client_with_env_api_key(self) -> None:
        """Client should read API key from environment variable."""
        os.environ["FEATHERLESS_API_KEY"] = "env-key"
        client = FeatherlessClient()
        self.assertEqual(client.api_key, "env-key")
        self.assertIsNotNone(client._client)

    def test_client_default_model(self) -> None:
        """Client should use default model when not specified."""
        from app.llm.featherless_client import DEFAULT_MODEL

        client = FeatherlessClient()
        self.assertEqual(client.model, DEFAULT_MODEL)

    def test_client_with_explicit_model(self) -> None:
        """Client should accept explicit model parameter."""
        client = FeatherlessClient(model="custom-model")
        self.assertEqual(client.model, "custom-model")

    def test_client_with_env_model(self) -> None:
        """Client should read model from environment variable."""
        os.environ["FEATHERLESS_MODEL"] = "env-model"
        client = FeatherlessClient()
        self.assertEqual(client.model, "env-model")

    def test_extract_files_from_context(self) -> None:
        """Client should extract file names from context."""
        client = FeatherlessClient(api_key="test-key")
        context = """===== FILE: auth/jwt.js =====
code here
===== FILE: utils/math.py =====
more code"""
        files = client._extract_files_from_context(context)
        self.assertEqual(files, ["auth/jwt.js", "utils/math.py"])

    def test_extract_files_from_empty_context(self) -> None:
        """Client should handle empty context gracefully."""
        client = FeatherlessClient(api_key="test-key")
        files = client._extract_files_from_context("")
        self.assertEqual(files, [])

    def test_construct_debugging_prompt(self) -> None:
        """Client should construct proper debugging prompt."""
        client = FeatherlessClient(api_key="test-key")
        prompt = client._construct_debugging_prompt("code context", "my question")
        self.assertIn("my question", prompt)
        self.assertIn("code context", prompt)
        self.assertIn("debugging", prompt.lower())

    @patch("app.llm.featherless_client.OpenAI")
    def test_successful_api_call(self, mock_openai: MagicMock) -> None:
        """Client should successfully call API and return response."""
        # Mock the OpenAI client and response
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test answer"
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = FeatherlessClient(api_key="test-key")
        response = client.ask("context", "query")

        self.assertEqual(response.answer, "Test answer")
        self.assertIsInstance(response, LLMResponse)
        mock_client.chat.completions.create.assert_called_once()

    @patch("app.llm.featherless_client.OpenAI")
    def test_api_error_handling(self, mock_openai: MagicMock) -> None:
        """Client should handle OpenAI API errors gracefully."""
        from openai import OpenAIError

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = OpenAIError("API error")
        mock_openai.return_value = mock_client

        client = FeatherlessClient(api_key="test-key")
        with self.assertRaises(RuntimeError) as ctx:
            client.ask("context", "query")
        self.assertIn("API request failed", str(ctx.exception))
        # Ensure API key is not exposed in error
        self.assertNotIn("test-key", str(ctx.exception))

    @patch("app.llm.featherless_client.OpenAI")
    def test_network_error_handling(self, mock_openai: MagicMock) -> None:
        """Client should handle network errors gracefully."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Network error")
        mock_openai.return_value = mock_client

        client = FeatherlessClient(api_key="test-key")
        with self.assertRaises(RuntimeError) as ctx:
            client.ask("context", "query")
        self.assertIn("Unexpected error", str(ctx.exception))

    @patch("app.llm.featherless_client.OpenAI")
    def test_empty_response_handling(self, mock_openai: MagicMock) -> None:
        """Client should handle empty API response gracefully."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = FeatherlessClient(api_key="test-key")
        response = client.ask("context", "query")
        self.assertEqual(response.answer, "")

    @patch("app.llm.featherless_client.OpenAI")
    def test_api_call_parameters(self, mock_openai: MagicMock) -> None:
        """Client should call API with correct parameters."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Answer"
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = FeatherlessClient(api_key="test-key", model="test-model")
        client.ask("context", "query")

        call_args = mock_client.chat.completions.create.call_args
        self.assertEqual(call_args.kwargs["model"], "test-model")
        self.assertEqual(len(call_args.kwargs["messages"]), 2)
        self.assertEqual(call_args.kwargs["temperature"], 0.3)
        self.assertEqual(call_args.kwargs["max_tokens"], 2048)


if __name__ == "__main__":
    unittest.main(verbosity=2)
