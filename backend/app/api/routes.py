"""FastAPI route handlers for ContextForge endpoints."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, NamedTuple

from fastapi import APIRouter, HTTPException, status

from app.analyzer import CodeAnalyzer
from app.compressor import CompressorOptions, ContextCompressor
from app.llm import FeatherlessClient
from app.metrics import MetricsEngine, PricingConfig
from app.optimizer import ContextSelector
from app.relevance import QueryAnalyzer, RelevanceScorer
from app.remote import (
    GitHubRepoNotFoundError,
    GitHubSourceError,
    checkout_github_repository,
    parse_github_url,
)
from app.scanner import RepositoryScanner
from app.scanner.filter import FileFilter

from .schemas import (
    ContextOptimizeRequest,
    ContextOptimizeResponse,
    ExcludedFileResponse,
    FileAnalysisItem,
    FilteredFileItem,
    HealthResponse,
    LLMAskRequest,
    LLMAskResponse,
    MetricsResponse,
    ProjectAnalyzeRequest,
    ProjectAnalyzeResponse,
    ProjectAnalyzeSummary,
    QueryAnalysisResponse,
    SelectedFileResponse,
)

router = APIRouter(prefix="/api", tags=["ContextForge"])


class _ProjectSource(NamedTuple):
    """Resolved pipeline input: a local directory and the path to report back."""

    root: Path
    display_path: str


@contextmanager
def _open_project_source(
    project_path: str | None, repository_url: str | None
) -> Iterator[_ProjectSource]:
    """Resolve the request input to a directory the pipeline can scan.

    A ``repository_url`` (public GitHub repository) is downloaded into a
    temporary directory that lives exactly as long as the pipeline and is
    deleted afterwards. A plain ``project_path`` is used from the local
    filesystem exactly as before.
    """
    if repository_url:
        try:
            repo = parse_github_url(repository_url)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        try:
            with checkout_github_repository(repo) as root:
                yield _ProjectSource(root=root, display_path=repo.canonical_url)
        except GitHubRepoNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from exc
        except GitHubSourceError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
            ) from exc
        return

    if not project_path:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Either project_path or repository_url must be provided.",
        )

    project_root = Path(project_path).expanduser().resolve()
    if not project_root.exists() or not project_root.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project path '{project_path}' does not exist or is not a directory.",
        )
    yield _ProjectSource(root=project_root, display_path=str(project_root))


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Return backend health and service metadata."""
    return HealthResponse()


@router.post(
    "/projects/analyze",
    response_model=ProjectAnalyzeResponse,
    status_code=status.HTTP_200_OK,
)
def analyze_project(request: ProjectAnalyzeRequest) -> ProjectAnalyzeResponse:
    """Scan and structurally analyze files in a project directory."""
    with _open_project_source(request.project_path, request.repository_url) as source:
        project_root = source.root

        # 1. Repository Scanner
        scanner = RepositoryScanner(project_root)
        scan_result = scanner.scan()

        # 2. File Filter
        file_filter = FileFilter(max_file_size_bytes=request.max_file_size_bytes)
        filtered_result = file_filter.filter(scan_result)

        # 3. Code Analyzer
        analyzer = CodeAnalyzer(max_read_bytes=request.max_file_size_bytes)
        analyzed_files = analyzer.analyze_files(project_root, filtered_result)

        summary = ProjectAnalyzeSummary(
            total_files=scan_result.get("total_files", 0),
            source_files=scan_result.get("source_files", 0),
            config_files=scan_result.get("config_files", 0),
            test_files=scan_result.get("test_files", 0),
            ignored_files=scan_result.get("ignored_files", 0),
            kept_files_count=len(filtered_result.get("files", [])),
            filtered_files_count=filtered_result.get("filtered_count", 0),
            analyzed_files_count=len(analyzed_files),
        )

        file_items = [
            FileAnalysisItem(
                path=f.path,
                language=f.language,
                analysis_supported=f.analysis_supported,
                line_count=f.line_count,
                imports=f.imports,
                functions=f.functions,
                classes=f.classes,
                symbols=f.symbols,
                exports=f.exports,
                analysis_error=f.analysis_error,
            )
            for f in analyzed_files
        ]

        filtered_items = [
            FilteredFileItem(
                path=str(item.get("path", "")),
                reason=str(item.get("reason", "")),
            )
            for item in filtered_result.get("filtered_files", [])
        ]

        return ProjectAnalyzeResponse(
            project_path=source.display_path,
            summary=summary,
            files=file_items,
            filtered_files=filtered_items,
        )


@router.post(
    "/context/optimize",
    response_model=ContextOptimizeResponse,
    status_code=status.HTTP_200_OK,
)
def optimize_context(request: ContextOptimizeRequest) -> ContextOptimizeResponse:
    """Execute the full ContextForge pipeline to select and compress context for an LLM."""
    with _open_project_source(request.project_path, request.repository_url) as source:
        project_root = source.root

        # Stage 1: Repository Scanner
        scanner = RepositoryScanner(project_root)
        scan_result = scanner.scan()

        # Stage 2: File Filter
        file_filter = FileFilter()
        filtered_result = file_filter.filter(scan_result)

        # Stage 3: Code Analyzer
        analyzer = CodeAnalyzer()
        file_analyses = analyzer.analyze_files(project_root, filtered_result)

        # Stage 4: Query & Relevance Analyzer
        query_analyzer = QueryAnalyzer()
        query_analysis = query_analyzer.analyze(request.query)

        scorer = RelevanceScorer()
        ranked_files = scorer.rank(query_analysis, file_analyses)

        # Stage 5: Context Selector
        selector = ContextSelector()
        selection_result = selector.select(project_root, ranked_files, request.token_budget)

        # Stage 6: Context Compressor
        compressor_options = None
        if request.compressor_options is not None:
            compressor_options = CompressorOptions(**request.compressor_options.model_dump())

        compressor = ContextCompressor(options=compressor_options)
        compression_result = compressor.compress(selection_result)

        # Stage 7: Metrics Engine
        pricing_config = None
        if request.pricing is not None:
            pricing_config = PricingConfig(
                input_price_per_1k_tokens=request.pricing.input_price_per_1k_tokens,
                currency=request.pricing.currency,
            )

        metrics_engine = MetricsEngine(pricing=pricing_config)
        optimization_metrics = metrics_engine.calculate(
            selection_result,
            compression_result,
            pricing=pricing_config,
        )

        # Format response payloads
        query_response = QueryAnalysisResponse(
            original_query=query_analysis.original_query,
            intent=query_analysis.intent,
            keywords=query_analysis.keywords,
            technical_terms=query_analysis.technical_terms,
            actions=query_analysis.actions,
            topics=query_analysis.topics,
            valid=query_analysis.valid,
        )

        selected_files = [
            SelectedFileResponse(
                path=sf.path,
                relevance_score=sf.relevance_score,
                token_count=sf.token_count,
                selection_order=sf.selection_order,
            )
            for sf in selection_result.selected_files
        ]

        excluded_files = [
            ExcludedFileResponse(
                path=ef.path,
                relevance_score=ef.relevance_score,
                token_count=ef.token_count,
                reason=ef.reason,
            )
            for ef in selection_result.excluded_files
        ]

        cost = optimization_metrics.cost
        metrics_response = MetricsResponse(
            original_tokens=optimization_metrics.original_tokens,
            optimized_tokens=optimization_metrics.optimized_tokens,
            tokens_saved=optimization_metrics.tokens_saved,
            reduction_percentage=optimization_metrics.reduction_percentage,
            compression_ratio=optimization_metrics.compression_ratio,
            original_characters=optimization_metrics.original_characters,
            optimized_characters=optimization_metrics.optimized_characters,
            characters_saved=optimization_metrics.characters_saved,
            original_lines=optimization_metrics.original_lines,
            optimized_lines=optimization_metrics.optimized_lines,
            lines_saved=optimization_metrics.lines_saved,
            estimated_original_cost=cost.estimated_original_cost if cost else None,
            estimated_optimized_cost=cost.estimated_optimized_cost if cost else None,
            estimated_cost_savings=cost.estimated_cost_savings if cost else None,
            currency=cost.currency if cost else None,
        )

        return ContextOptimizeResponse(
            project_path=source.display_path,
            query_analysis=query_response,
            selected_files=selected_files,
            excluded_files=excluded_files,
            optimized_context=compression_result.compressed_context,
            metrics=metrics_response,
            total_candidates=selection_result.total_candidate_files,
            total_selected=len(selected_files),
            total_excluded=len(excluded_files),
        )


@router.post(
    "/llm/ask",
    response_model=LLMAskResponse,
    status_code=status.HTTP_200_OK,
)
def ask_llm(request: LLMAskRequest) -> LLMAskResponse:
    """Ask the LLM a debugging question with optimized context."""
    try:
        # Initialize Featherless client (reads API key from environment)
        client = FeatherlessClient()
        response = client.ask(request.optimized_context, request.query)
        return LLMAskResponse(answer=response.answer, files_used=response.files_used)
    except ValueError as e:
        # API key not configured
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e
    except RuntimeError as e:
        # API or network error
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        ) from e
