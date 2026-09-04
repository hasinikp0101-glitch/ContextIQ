"""Token and Cost Metrics Engine for ContextForge.

Computes deterministic token savings, compression ratios, text-level reductions,
and configurable cost estimations without external API or LLM dependencies.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable

from app.compressor.compressor import CompressionResult
from app.optimizer.selector import ContextSelector, SelectionResult


@dataclass
class PricingConfig:
    """Configurable pricing model for cost estimation."""

    input_price_per_1k_tokens: float = 0.0
    currency: str = "USD"

    def __post_init__(self) -> None:
        try:
            self.input_price_per_1k_tokens = max(0.0, float(self.input_price_per_1k_tokens))
        except (TypeError, ValueError):
            self.input_price_per_1k_tokens = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dictionary."""
        return asdict(self)


@dataclass
class CostMetrics:
    """Estimated financial cost impact of context optimization."""

    input_price_per_1k_tokens: float
    estimated_original_cost: float
    estimated_optimized_cost: float
    estimated_cost_savings: float
    currency: str = "USD"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dictionary."""
        return asdict(self)


@dataclass
class TokenMetrics:
    """Core token-level optimization measurements."""

    original_tokens: int
    optimized_tokens: int
    tokens_saved: int
    reduction_percentage: float
    compression_ratio: float

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dictionary."""
        return asdict(self)


@dataclass
class TextMetrics:
    """Character and line count reduction measurements."""

    original_characters: int
    optimized_characters: int
    characters_saved: int
    original_lines: int
    optimized_lines: int
    lines_saved: int

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dictionary."""
        return asdict(self)


@dataclass
class OptimizationMetrics:
    """Unified metrics model containing token, text, and cost measurements."""

    tokens: TokenMetrics
    text: TextMetrics
    cost: CostMetrics | None = None

    # Top-level property conveniences
    @property
    def original_tokens(self) -> int:
        return self.tokens.original_tokens

    @property
    def optimized_tokens(self) -> int:
        return self.tokens.optimized_tokens

    @property
    def tokens_saved(self) -> int:
        return self.tokens.tokens_saved

    @property
    def reduction_percentage(self) -> float:
        return self.tokens.reduction_percentage

    @property
    def compression_ratio(self) -> float:
        return self.tokens.compression_ratio

    @property
    def original_characters(self) -> int:
        return self.text.original_characters

    @property
    def optimized_characters(self) -> int:
        return self.text.optimized_characters

    @property
    def characters_saved(self) -> int:
        return self.text.characters_saved

    @property
    def original_lines(self) -> int:
        return self.text.original_lines

    @property
    def optimized_lines(self) -> int:
        return self.text.optimized_lines

    @property
    def lines_saved(self) -> int:
        return self.text.lines_saved

    def to_dict(self) -> dict[str, Any]:
        """Return a flat and nested JSON-friendly dictionary."""
        result: dict[str, Any] = {
            "original_tokens": self.original_tokens,
            "optimized_tokens": self.optimized_tokens,
            "tokens_saved": self.tokens_saved,
            "reduction_percentage": self.reduction_percentage,
            "compression_ratio": self.compression_ratio,
            "original_characters": self.original_characters,
            "optimized_characters": self.optimized_characters,
            "characters_saved": self.characters_saved,
            "original_lines": self.original_lines,
            "optimized_lines": self.optimized_lines,
            "lines_saved": self.lines_saved,
            "tokens": self.tokens.to_dict(),
            "text": self.text.to_dict(),
        }
        if self.cost is not None:
            result["cost"] = self.cost.to_dict()
            result["estimated_original_cost"] = self.cost.estimated_original_cost
            result["estimated_optimized_cost"] = self.cost.estimated_optimized_cost
            result["estimated_cost_savings"] = self.cost.estimated_cost_savings
            result["currency"] = self.cost.currency
        return result


class MetricsEngine:
    """Calculates deterministic optimization metrics for the ContextForge pipeline."""

    def __init__(
        self,
        encoding_name: str = "cl100k_base",
        count_tokens: Callable[[str], int] | None = None,
        pricing: PricingConfig | None = None,
    ) -> None:
        """Create a MetricsEngine.

        Args:
            encoding_name: tiktoken encoding name (cl100k_base by default).
            count_tokens: Optional custom token counter. Defaults to ContextSelector.
            pricing: Optional default pricing model.
        """
        self.encoding_name = encoding_name
        self.pricing = pricing
        if count_tokens is not None:
            self._count_tokens = count_tokens
        else:
            selector = ContextSelector(encoding_name=encoding_name)
            self._count_tokens = selector.count_tokens

    def count_tokens(self, text: str) -> int:
        """Return token count using the configured tokenizer."""
        if not text:
            return 0
        return max(0, int(self._count_tokens(text)))

    def calculate(
        self,
        original: Any,
        optimized: Any,
        pricing: PricingConfig | None = None,
    ) -> OptimizationMetrics:
        """Calculate token, text, and cost optimization metrics.

        Accepts:
            - Strings: ``(original_text, optimized_text)``
            - Pipeline objects: ``(SelectionResult, CompressionResult)``
            - Token counts: ``(orig_token_int, opt_token_int)``
        """
        orig_text, orig_tokens_hint = _extract_text_and_tokens(original)
        opt_text, opt_tokens_hint = _extract_text_and_tokens(optimized)

        # 1. Token Metrics
        if orig_tokens_hint is not None and not orig_text:
            orig_tokens = orig_tokens_hint
        else:
            orig_tokens = self.count_tokens(orig_text) if orig_text else (orig_tokens_hint or 0)

        if opt_tokens_hint is not None and not opt_text:
            opt_tokens = opt_tokens_hint
        else:
            opt_tokens = self.count_tokens(opt_text) if opt_text else (opt_tokens_hint or 0)

        orig_tokens = max(0, int(orig_tokens))
        opt_tokens = max(0, int(opt_tokens))

        tokens_saved = max(0, orig_tokens - opt_tokens)
        if orig_tokens > 0:
            reduction_percentage = round((tokens_saved / orig_tokens) * 100.0, 2)
            compression_ratio = round(opt_tokens / orig_tokens, 4)
        else:
            reduction_percentage = 0.0
            compression_ratio = 1.0

        token_metrics = TokenMetrics(
            original_tokens=orig_tokens,
            optimized_tokens=opt_tokens,
            tokens_saved=tokens_saved,
            reduction_percentage=reduction_percentage,
            compression_ratio=compression_ratio,
        )

        # 2. Text Metrics
        orig_chars = len(orig_text)
        opt_chars = len(opt_text)
        chars_saved = max(0, orig_chars - opt_chars)

        orig_lines = _count_lines(orig_text)
        opt_lines = _count_lines(opt_text)
        lines_saved = max(0, orig_lines - opt_lines)

        text_metrics = TextMetrics(
            original_characters=orig_chars,
            optimized_characters=opt_chars,
            characters_saved=chars_saved,
            original_lines=orig_lines,
            optimized_lines=opt_lines,
            lines_saved=lines_saved,
        )

        # 3. Cost Metrics (optional)
        cost_cfg = pricing if pricing is not None else self.pricing
        cost_metrics: CostMetrics | None = None
        if cost_cfg is not None:
            cost_metrics = self.calculate_cost(orig_tokens, opt_tokens, cost_cfg)

        return OptimizationMetrics(
            tokens=token_metrics,
            text=text_metrics,
            cost=cost_metrics,
        )

    def calculate_cost(
        self,
        original_tokens: int,
        optimized_tokens: int,
        pricing: PricingConfig | None = None,
    ) -> CostMetrics:
        """Calculate estimated dollar cost and savings from token counts."""
        cfg = pricing if pricing is not None else (self.pricing or PricingConfig())
        orig_tok = max(0, int(original_tokens))
        opt_tok = max(0, int(optimized_tokens))

        rate_per_token = cfg.input_price_per_1k_tokens / 1000.0

        orig_cost = round(orig_tok * rate_per_token, 6)
        opt_cost = round(opt_tok * rate_per_token, 6)
        cost_saved = round(max(0.0, orig_cost - opt_cost), 6)

        return CostMetrics(
            input_price_per_1k_tokens=cfg.input_price_per_1k_tokens,
            estimated_original_cost=orig_cost,
            estimated_optimized_cost=opt_cost,
            estimated_cost_savings=cost_saved,
            currency=cfg.currency,
        )


def _extract_text_and_tokens(obj: Any) -> tuple[str, int | None]:
    """Extract string content and optional precomputed token count from input."""
    if obj is None:
        return "", 0

    if isinstance(obj, str):
        return _normalize_newlines(obj), None

    if isinstance(obj, (int, float)):
        val = max(0, int(obj))
        return "", val

    if isinstance(obj, SelectionResult):
        return _normalize_newlines(obj.context), obj.selected_tokens

    if isinstance(obj, CompressionResult):
        return _normalize_newlines(obj.compressed_context), obj.metrics.compressed_tokens

    if isinstance(obj, dict):
        text = str(obj.get("context") or obj.get("compressed_context") or "")
        tokens = obj.get("tokens") or obj.get("token_count") or obj.get("selected_tokens")
        try:
            tokens_int = int(tokens) if tokens is not None else None
        except (ValueError, TypeError):
            tokens_int = None
        return _normalize_newlines(text), tokens_int

    return _normalize_newlines(str(obj)), None


def _normalize_newlines(text: str) -> str:
    """Normalize CRLF and CR to standard LF."""
    if not text:
        return ""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _count_lines(text: str) -> int:
    """Count lines cleanly, treating empty text as 0 lines."""
    if not text:
        return 0
    return len(text.split("\n"))
