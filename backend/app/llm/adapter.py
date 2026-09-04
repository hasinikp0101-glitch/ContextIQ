"""LLM service adapter interface for ContextForge."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class LLMResponse:
    """Response from an LLM service."""

    answer: str
    files_used: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dictionary."""
        return asdict(self)


class LLMAdapter(ABC):
    """Abstract base class for LLM service adapters."""

    @abstractmethod
    def ask(self, optimized_context: str, query: str) -> LLMResponse:
        """Ask the LLM a question with optimized context.

        Args:
            optimized_context: The compressed context from ContextForge.
            query: The user's debugging question.

        Returns:
            An LLMResponse with the answer and files used.
        """
        pass
