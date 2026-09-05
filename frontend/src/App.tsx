import { useEffect, useRef, useState } from "react";
import { api } from "./api/client";
import type {
  ContextOptimizeResponse,
  LLMAskResponse,
  ProjectAnalyzeResponse,
} from "./api/types";
import { describeActionError, describeLLMError } from "./utils/errors";
import { Header } from "./components/Header";
import { QueryPanel } from "./components/QueryPanel";
import { PipelineProgress } from "./components/PipelineProgress";
import type { PipelineStatus } from "./components/PipelineProgress";
import { QueryAnalysis } from "./components/QueryAnalysis";
import { ScanSummary } from "./components/ScanSummary";
import { MetricsDashboard } from "./components/MetricsDashboard";
import { FileList } from "./components/FileList";
import { ContextViewer } from "./components/ContextViewer";
import { DiagnosisPanel } from "./components/DiagnosisPanel";
import { EmptyState } from "./components/EmptyState";

const PIPELINE_STAGE_COUNT = 6;
const LAST_SELECTING_STAGE = 4; // index of "Compressing"; "Ready" lights up on success

const GITHUB_URL_PATTERN = /^https:\/\/github\.com\//i;

/**
 * The backend accepts either a local path or a public GitHub URL (never both).
 * GitHub URLs are sent as repository_url so the server downloads the repo;
 * everything else stays a local project_path.
 */
function projectSourceFields(
  repoPath: string,
): { project_path: string } | { repository_url: string } {
  const value = repoPath.trim();
  return GITHUB_URL_PATTERN.test(value)
    ? { repository_url: value }
    : { project_path: value };
}

interface PipelineState {
  status: PipelineStatus;
  activeIndex: number;
  completedCount: number;
}

const IDLE_PIPELINE: PipelineState = { status: "idle", activeIndex: 0, completedCount: 0 };

export function App() {
  const [repoPath, setRepoPath] = useState("");
  const [question, setQuestion] = useState("");
  const [tokenBudget, setTokenBudget] = useState(4000);

  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeResult, setAnalyzeResult] = useState<ProjectAnalyzeResponse | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [optimizing, setOptimizing] = useState(false);
  const [optimizeResult, setOptimizeResult] = useState<ContextOptimizeResponse | null>(null);
  const [lastQuery, setLastQuery] = useState("");

  const [asking, setAsking] = useState(false);
  const [diagnosis, setDiagnosis] = useState<LLMAskResponse | null>(null);
  const [diagnosisError, setDiagnosisError] = useState<string | null>(null);

  const [pipeline, setPipeline] = useState<PipelineState>(IDLE_PIPELINE);
  const stageTimer = useRef<number | null>(null);
  const stageInterval = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (stageTimer.current !== null) window.clearTimeout(stageTimer.current);
      if (stageInterval.current !== null) window.clearInterval(stageInterval.current);
    };
  }, []);

  const clearTimers = () => {
    if (stageTimer.current !== null) {
      window.clearTimeout(stageTimer.current);
      stageTimer.current = null;
    }
    if (stageInterval.current !== null) {
      window.clearInterval(stageInterval.current);
      stageInterval.current = null;
    }
  };

  const runAnalyze = async () => {
    setActionError(null);
    setAnalyzing(true);
    setPipeline({ status: "running", activeIndex: 0, completedCount: 0 });
    stageTimer.current = window.setTimeout(
      () => setPipeline((p) => (p.status === "running" && p.activeIndex === 0 ? { ...p, activeIndex: 1 } : p)),
      700,
    );

    try {
      const result = await api.analyzeProject(projectSourceFields(repoPath));
      setAnalyzeResult(result);
      setPipeline((p) =>
        p.status === "done" ? p : { status: "idle", activeIndex: 0, completedCount: 2 },
      );
    } catch (err) {
      setActionError(describeActionError(err));
      setPipeline({ status: "error", activeIndex: 0, completedCount: 0 });
    } finally {
      if (stageTimer.current !== null) {
        window.clearTimeout(stageTimer.current);
        stageTimer.current = null;
      }
      setAnalyzing(false);
    }
  };

  const runOptimize = async () => {
    clearTimers();
    setActionError(null);
    setDiagnosis(null);
    setDiagnosisError(null);
    setOptimizeResult(null);
    setOptimizing(true);
    setPipeline({ status: "running", activeIndex: 0, completedCount: 0 });
    stageInterval.current = window.setInterval(
      () =>
        setPipeline((p) =>
          p.status === "running" && p.activeIndex < LAST_SELECTING_STAGE
            ? { ...p, activeIndex: p.activeIndex + 1 }
            : p,
        ),
      700,
    );

    try {
      const result = await api.optimizeContext({
        ...projectSourceFields(repoPath),
        query: question.trim(),
        token_budget: tokenBudget > 0 ? tokenBudget : 4000,
      });
      setOptimizeResult(result);
      setLastQuery(question.trim());
      setPipeline({ status: "done", activeIndex: 0, completedCount: PIPELINE_STAGE_COUNT });
    } catch (err) {
      setActionError(describeActionError(err));
      setPipeline((p) => ({
        status: "error",
        activeIndex: Math.min(p.activeIndex, LAST_SELECTING_STAGE),
        completedCount: 0,
      }));
    } finally {
      if (stageInterval.current !== null) {
        window.clearInterval(stageInterval.current);
        stageInterval.current = null;
      }
      setOptimizing(false);
    }
  };

  const askLLM = async () => {
    if (!optimizeResult) return;
    setAsking(true);
    setDiagnosisError(null);
    try {
      const result = await api.askLLM({
        optimized_context: optimizeResult.optimized_context,
        query: lastQuery || question.trim(),
      });
      setDiagnosis(result);
    } catch (err) {
      setDiagnosisError(describeLLMError(err));
    } finally {
      setAsking(false);
    }
  };

  return (
    <div className="min-h-screen">
      <Header />

      <main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6">
        <div className="grid items-start gap-5 lg:grid-cols-[380px_minmax(0,1fr)] xl:grid-cols-[400px_minmax(0,1fr)]">
          <div className="space-y-5">
            <QueryPanel
              repoPath={repoPath}
              onRepoPathChange={setRepoPath}
              question={question}
              onQuestionChange={setQuestion}
              tokenBudget={tokenBudget}
              onTokenBudgetChange={setTokenBudget}
              onAnalyze={() => void runAnalyze()}
              onOptimize={() => void runOptimize()}
              analyzing={analyzing}
              optimizing={optimizing}
              error={actionError}
              onErrorDismiss={() => setActionError(null)}
            />
            <PipelineProgress
              status={pipeline.status}
              activeIndex={pipeline.activeIndex}
              completedCount={pipeline.completedCount}
            />
            <QueryAnalysis analysis={optimizeResult?.query_analysis ?? null} />
            <ScanSummary analysis={analyzeResult} />
          </div>

          <div className="space-y-5">
            {optimizeResult ? (
              <>
                <MetricsDashboard data={optimizeResult} />
                <FileList
                  selected={optimizeResult.selected_files}
                  excluded={optimizeResult.excluded_files}
                />
                <ContextViewer
                  context={optimizeResult.optimized_context}
                  optimizedTokens={optimizeResult.metrics.optimized_tokens}
                />
                <DiagnosisPanel
                  enabled
                  optimizedTokens={optimizeResult.metrics.optimized_tokens}
                  question={lastQuery || question}
                  asking={asking}
                  result={diagnosis}
                  error={diagnosisError}
                  onAsk={() => void askLLM()}
                />
              </>
            ) : (
              <EmptyState hasScan={analyzeResult !== null} busy={optimizing} />
            )}
          </div>
        </div>

        <footer className="mt-8 border-t border-edge pt-4">
          <p className="text-[11px] text-ink-faint">
            ContextForge · every metric, file list, and diagnosis on this page is live output from the
            local FastAPI pipeline — nothing is mocked.
          </p>
        </footer>
      </main>
    </div>
  );
}
