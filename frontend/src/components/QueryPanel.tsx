import { AlertTriangle, FolderSearch, LoaderCircle, X, Zap } from "lucide-react";
import { useState } from "react";

const EXAMPLE_QUERIES = [
  "Why is Google OAuth login failing?",
  "Where is the database connection configured?",
  "Why did the auth tests start failing?",
];

const EXAMPLE_GITHUB_REPO = "https://github.com/tsungtwu/flask-example";

const BUDGET_PRESETS = [2000, 4000, 8000, 16000];

export interface QueryPanelProps {
  repoPath: string;
  onRepoPathChange: (value: string) => void;
  question: string;
  onQuestionChange: (value: string) => void;
  tokenBudget: number;
  onTokenBudgetChange: (value: number) => void;
  onAnalyze: () => void;
  onOptimize: () => void;
  analyzing: boolean;
  optimizing: boolean;
  error: string | null;
  onErrorDismiss: () => void;
}

export function QueryPanel({
  repoPath,
  onRepoPathChange,
  question,
  onQuestionChange,
  tokenBudget,
  onTokenBudgetChange,
  onAnalyze,
  onOptimize,
  analyzing,
  optimizing,
  error,
  onErrorDismiss,
}: QueryPanelProps) {
  const [pathError, setPathError] = useState<string | null>(null);
  const [queryError, setQueryError] = useState<string | null>(null);
  const busy = analyzing || optimizing;

  const handleAnalyze = () => {
    if (!repoPath.trim()) {
      setPathError("Enter a repository path or public GitHub URL first.");
      setQueryError(null);
      return;
    }
    setPathError(null);
    setQueryError(null);
    onAnalyze();
  };

  const handleOptimize = () => {
    let invalid = false;
    if (!repoPath.trim()) {
      setPathError("Repository path or GitHub URL is required.");
      invalid = true;
    }
    if (!question.trim()) {
      setQueryError(
        "Describe what you are debugging — the pipeline ranks files by relevance to this question.",
      );
      invalid = true;
    }
    if (invalid) return;
    setPathError(null);
    setQueryError(null);
    onOptimize();
  };

  return (
    <section className="card">
      <div className="card-header">
        <h2 className="card-title">Run the pipeline</h2>
        <span className="font-mono text-[10px] text-ink-faint">POST /api/context/optimize</span>
      </div>
      <div className="card-body space-y-4">
        {error && (
          <div className="error-banner">
            <AlertTriangle size={14} className="mt-0.5 shrink-0 text-danger" />
            <p className="min-w-0 break-words">{error}</p>
            <button
              type="button"
              onClick={onErrorDismiss}
              className="ml-auto shrink-0 text-ink-faint transition-colors hover:text-ink"
              aria-label="Dismiss error"
            >
              <X size={14} />
            </button>
          </div>
        )}

        <div>
          <label htmlFor="repo-path" className="field-label">
            Repository path or GitHub URL
          </label>
          <input
            id="repo-path"
            type="text"
            className="input font-mono"
            spellCheck={false}
            autoComplete="off"
            placeholder="C:\path\to\repo  ·  https://github.com/owner/repo"
            value={repoPath}
            onChange={(e) => {
              onRepoPathChange(e.target.value);
              if (pathError) setPathError(null);
            }}
          />
          {pathError && <p className="mt-1.5 text-[11px] text-danger">{pathError}</p>}
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <span className="text-[10px] font-medium uppercase tracking-[0.06em] text-ink-faint">
              local folder or public repo
            </span>
            <button
              type="button"
              onClick={() => onRepoPathChange(EXAMPLE_GITHUB_REPO)}
              className="chip transition-colors hover:border-accent/50 hover:text-ink"
              title={EXAMPLE_GITHUB_REPO}
            >
              try: tsungtwu/flask-example
            </button>
          </div>
        </div>

        <div>
          <label htmlFor="question" className="field-label">
            Development question
          </label>
          <textarea
            id="question"
            className="input min-h-[64px] resize-y"
            spellCheck={false}
            placeholder="Why is Google OAuth login failing?"
            value={question}
            onChange={(e) => {
              onQuestionChange(e.target.value);
              if (queryError) setQueryError(null);
            }}
          />
          {queryError && <p className="mt-1.5 text-[11px] text-danger">{queryError}</p>}
          <div className="mt-2 flex flex-wrap gap-1.5">
            {EXAMPLE_QUERIES.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => onQuestionChange(q)}
                className="chip transition-colors hover:border-accent/50 hover:text-ink"
                title={q}
              >
                {q}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label htmlFor="token-budget" className="field-label">
            Token budget
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <input
              id="token-budget"
              type="number"
              min={100}
              step={100}
              className="input w-24 font-mono"
              value={Number.isFinite(tokenBudget) ? tokenBudget : ""}
              onChange={(e) => {
                const parsed = Number(e.target.value);
                onTokenBudgetChange(Number.isFinite(parsed) ? parsed : 0);
              }}
            />
            <div className="flex gap-1.5">
              {BUDGET_PRESETS.map((preset) => (
                <button
                  key={preset}
                  type="button"
                  onClick={() => onTokenBudgetChange(preset)}
                  className={`chip transition-colors ${
                    tokenBudget === preset ? "border-accent/50 bg-accent-soft text-accent" : "hover:text-ink"
                  }`}
                >
                  {preset / 1000}k
                </button>
              ))}
            </div>
          </div>
          <p className="mt-1.5 text-[11px] text-ink-faint">
            Maximum prompt size ContextForge is allowed to assemble.
          </p>
        </div>

        <div className="flex gap-2 pt-1">
          <button type="button" className="btn btn-secondary flex-1" onClick={handleAnalyze} disabled={busy}>
            {analyzing ? <LoaderCircle size={14} className="animate-spin" /> : <FolderSearch size={14} />}
            {analyzing ? "Analyzing…" : "Analyze"}
          </button>
          <button type="button" className="btn btn-primary flex-1" onClick={handleOptimize} disabled={busy}>
            {optimizing ? <LoaderCircle size={14} className="animate-spin" /> : <Zap size={14} />}
            {optimizing ? "Optimizing…" : "Optimize Context"}
          </button>
        </div>
      </div>
    </section>
  );
}
