/**
 * TypeScript mirrors of the Pydantic schemas in backend/app/api/schemas.py.
 * Field names and types must stay in sync with the backend contracts.
 */

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

// ---------------------------------------------------------------------------
// Project analysis — POST /api/projects/analyze
// ---------------------------------------------------------------------------

export interface ProjectAnalyzeRequest {
  project_path?: string | null;
  max_file_size_bytes?: number;
  repository_url?: string | null;
}

export interface FileAnalysisItem {
  path: string;
  language: string;
  analysis_supported: boolean;
  line_count: number;
  imports: string[];
  functions: string[];
  classes: string[];
  symbols: string[];
  exports: string[];
  analysis_error: string | null;
}

export interface FilteredFileItem {
  path: string;
  reason: string;
}

export interface ProjectAnalyzeSummary {
  total_files: number;
  source_files: number;
  config_files: number;
  test_files: number;
  ignored_files: number;
  kept_files_count: number;
  filtered_files_count: number;
  analyzed_files_count: number;
}

export interface ProjectAnalyzeResponse {
  project_path: string;
  summary: ProjectAnalyzeSummary;
  files: FileAnalysisItem[];
  filtered_files: FilteredFileItem[];
}

// ---------------------------------------------------------------------------
// Context optimization — POST /api/context/optimize
// ---------------------------------------------------------------------------

export interface PricingConfigRequest {
  input_price_per_1k_tokens?: number;
  currency?: string;
}

export interface CompressorOptionsRequest {
  strip_comments?: boolean;
  collapse_blank_lines?: boolean;
  strip_trailing_whitespace?: boolean;
  strip_license_headers?: boolean;
  preserve_pragmas?: boolean;
  max_consecutive_blank_lines?: number;
}

export interface ContextOptimizeRequest {
  project_path?: string | null;
  query: string;
  token_budget?: number;
  repository_url?: string | null;
  pricing?: PricingConfigRequest | null;
  compressor_options?: CompressorOptionsRequest | null;
}

export interface QueryAnalysisResponse {
  original_query: string;
  intent: string;
  keywords: string[];
  technical_terms: string[];
  actions: string[];
  topics: string[];
  valid: boolean;
}

export interface SelectedFileResponse {
  path: string;
  relevance_score: number;
  token_count: number;
  selection_order: number;
}

export interface ExcludedFileResponse {
  path: string;
  relevance_score: number;
  token_count: number | null;
  reason: string;
}

export interface MetricsResponse {
  original_tokens: number;
  optimized_tokens: number;
  tokens_saved: number;
  reduction_percentage: number;
  compression_ratio: number;
  original_characters: number;
  optimized_characters: number;
  characters_saved: number;
  original_lines: number;
  optimized_lines: number;
  lines_saved: number;
  estimated_original_cost: number | null;
  estimated_optimized_cost: number | null;
  estimated_cost_savings: number | null;
  currency: string | null;
}

export interface ContextOptimizeResponse {
  project_path: string;
  query_analysis: QueryAnalysisResponse;
  selected_files: SelectedFileResponse[];
  excluded_files: ExcludedFileResponse[];
  optimized_context: string;
  metrics: MetricsResponse;
  total_candidates: number;
  total_selected: number;
  total_excluded: number;
}

// ---------------------------------------------------------------------------
// LLM — POST /api/llm/ask
// ---------------------------------------------------------------------------

export interface LLMAskRequest {
  optimized_context: string;
  query: string;
}

export interface LLMAskResponse {
  answer: string;
  files_used: string[];
}
