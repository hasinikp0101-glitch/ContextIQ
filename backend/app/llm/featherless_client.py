"""Featherless.ai client for ContextForge LLM integration."""

from __future__ import annotations

import os
import re
from typing import Any

from openai import OpenAI, OpenAIError

from .adapter import LLMAdapter, LLMResponse


# Default model if FEATHERLESS_MODEL is not set
DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct"
# Featherless OpenAI-compatible endpoint
BASE_URL = "https://api.featherless.ai/v1"


class FeatherlessClient(LLMAdapter):
    """Featherless.ai client using OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str = BASE_URL,
    ) -> None:
        """Initialize the Featherless client.

        Args:
            api_key: Optional API key. If not provided, reads from FEATHERLESS_API_KEY env var.
            model: Optional model name. If not provided, reads from FEATHERLESS_MODEL env var.
            base_url: Base URL for the API. Defaults to Featherless endpoint.
        """
        self.api_key = api_key or os.environ.get("FEATHERLESS_API_KEY")
        self.model = model or os.environ.get("FEATHERLESS_MODEL", DEFAULT_MODEL)
        self.base_url = base_url

        # Initialize OpenAI client only if API key is available
        self._client: OpenAI | None = None
        if self.api_key:
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def ask(self, optimized_context: str, query: str) -> LLMResponse:
        """Ask the LLM a question with optimized context.

        Args:
            optimized_context: The compressed context from ContextForge.
            query: The user's debugging question.

        Returns:
            An LLMResponse with the answer and files used.

        Raises:
            ValueError: If API key is not configured.
            RuntimeError: If API call fails.
        """
        if not self.api_key or not self._client:
            raise ValueError(
                "Featherless API key not configured. "
                "Set FEATHERLESS_API_KEY environment variable."
            )

        files_used = self._extract_files_from_context(optimized_context)
        prompt = self._construct_debugging_prompt(optimized_context, query)

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert debugging assistant. "
                        "Analyze the provided code context and help diagnose the issue. "
                        "Be concise and specific in your answer.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=2048,
            )

            answer = response.choices[0].message.content or ""

            return LLMResponse(answer=answer, files_used=files_used)

        except OpenAIError as e:
            # Never expose API key in error messages
            raise RuntimeError(f"Featherless API request failed: {type(e).__name__}") from e
        except Exception as e:
            raise RuntimeError(f"Unexpected error during LLM request: {type(e).__name__}") from e

    def _construct_debugging_prompt(self, optimized_context: str, query: str) -> str:
        """Construct a developer-focused debugging prompt.

        Args:
            optimized_context: The compressed code context.
            query: The user's debugging question.

        Returns:
            A formatted prompt string.
        """
        return f"""I need help debugging an issue in my codebase.

**My Question:**
{query}

**Relevant Code Context:**
{optimized_context}

Please analyze the code and provide a diagnosis. Focus on:
1. Identifying the root cause of the issue
2. Suggesting specific fixes
3. Explaining why the issue occurs

Be concise and specific."""

    def _extract_files_from_context(self, optimized_context: str) -> list[str]:
        """Extract file names from the optimized context.

        Looks for the pattern: ===== FILE: <path> =====

        Args:
            optimized_context: The compressed context string.

        Returns:
            A list of file paths found in the context.
        """
        pattern = r"===== FILE: (.+?) ====="
        matches = re.findall(pattern, optimized_context)
        return matches
