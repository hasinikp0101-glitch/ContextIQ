"""Pydantic schemas for the ContextForge FastAPI application."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Health Schemas
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    """Healthcheck endpoint response."""

    status: str = "healthy"
    service: str = "ContextForge API"
    version: str = "0.1.0"


# ---------------------------------------------------------------------------
# Project Analysis Schemas
# ---------------------------------------------------------------------------

class ProjectAnalyzeRequest(BaseModel):
    """Request payload for /api/projects/analyze."""

    project_path: str = Field(
        ...,
        description="Absolute or relative path to the project root directory.",
    )
    max_file_size_bytes: int = Field(
        default=1_048_576,
        description="Maximum file size in bytes to include for analysis.",
    )


class FileAnalysisItem(BaseModel):
    """Structural analysis for a single source file."""

    path: str
    language: str
    analysis_supported: bool
    line_count: int = 0
    imports: list[str] = Field(default_factory=list)
    functions: list[str] = Field(default_factory=list)
    classes: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    exports: list[str] = Field(default_factory=list)
    analysis_error: str | None = None


class FilteredFileItem(BaseModel):
    """Information about a file excluded during noise filtering."""

    path: str
    reason: str


class ProjectAnalyzeSummary(BaseModel):
    """Summary counts for scanned and filtered project files."""

    total_files: int
    source_files: int
    config_files: int
    test_files: int
    ignored_files: int
    kept_files_count: int
    filtered_files_count: int
    analyzed_files_count: int


class ProjectAnalyzeResponse(BaseModel):
    """Response payload for /api/projects/analyze."""

    project_path: str
    summary: ProjectAnalyzeSummary
    files: list[FileAnalysisItem]
    filtered_files: list[FilteredFileItem]


# ---------------------------------------------------------------------------
# Context Optimization Schemas
# ---------------------------------------------------------------------------

class PricingConfigRequest(BaseModel):
    """Optional token pricing configuration."""

    input_price_per_1k_tokens: float = Field(
        default=0.0,
        description="Price in currency per 1,000 input tokens.",
    )
    currency: str = Field(
        default="USD",
        description="Currency code (e.g. USD, EUR).",
    )


class CompressorOptionsRequest(BaseModel):
    """Optional configuration for the Context Compressor."""

    strip_comments: bool = True
    collapse_blank_lines: bool = True
    strip_trailing_whitespace: bool = True
    strip_license_headers: bool = True
    preserve_pragmas: bool = True
    max_consecutive_blank_lines: int = 1


class ContextOptimizeRequest(BaseModel):
    """Request payload for /api/context/optimize."""

    project_path: str = Field(
        ...,
        description="Path to the repository to optimize context for.",
    )
    query: str = Field(
        ...,
        description="The developer debugging query or question.",
    )
    token_budget: int = Field(
        default=4000,
        description="Maximum prompt token budget for selected context.",
    )
    pricing: PricingConfigRequest | None = Field(
        default=None,
        description="Optional pricing model for cost calculation.",
    )
    compressor_options: CompressorOptionsRequest | None = Field(
        default=None,
        description="Optional compressor configuration.",
    )


class QueryAnalysisResponse(BaseModel):
    """Parsed query metadata and developer intent."""

    original_query: str
    intent: str
    keywords: list[str] = Field(default_factory=list)
    technical_terms: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    valid: bool = True


class SelectedFileResponse(BaseModel):
    """A file selected by the Context Selector."""

    path: str
    relevance_score: int
    token_count: int
    selection_order: int


class ExcludedFileResponse(BaseModel):
    """A file excluded by the Context Selector."""

    path: str
    relevance_score: int
    token_count: int | None = None
    reason: str


class MetricsResponse(BaseModel):
    """Token, text, and financial optimization measurements."""

    original_tokens: int
    optimized_tokens: int
    tokens_saved: int
    reduction_percentage: float
    compression_ratio: float
    original_characters: int
    optimized_characters: int
    characters_saved: int
    original_lines: int
    optimized_lines: int
    lines_saved: int
    estimated_original_cost: float | None = None
    estimated_optimized_cost: float | None = None
    estimated_cost_savings: float | None = None
    currency: str | None = None


class ContextOptimizeResponse(BaseModel):
    """Response payload for /api/context/optimize."""

    project_path: str
    query_analysis: QueryAnalysisResponse
    selected_files: list[SelectedFileResponse]
    excluded_files: list[ExcludedFileResponse]
    optimized_context: str
    metrics: MetricsResponse
    total_candidates: int
    total_selected: int
    total_excluded: int
