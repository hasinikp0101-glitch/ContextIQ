import { Bot, LoaderCircle, Sparkles, TriangleAlert } from "lucide-react";
import type { LLMAskResponse } from "../api/types";
import { formatInt } from "../utils/format";

export interface DiagnosisPanelProps {
  enabled: boolean;
  optimizedTokens: number | null;
  question: string;
  asking: boolean;
  result: LLMAskResponse | null;
  error: string | null;
  onAsk: () => void;
}

export function DiagnosisPanel({
  enabled,
  optimizedTokens,
  question,
  asking,
  result,
  error,
  onAsk,
}: DiagnosisPanelProps) {
  return (
    <section className="card">
      <div className="card-header">
        <h2 className="card-title flex items-center gap-1.5">
          <Bot size={13} className="text-accent" />
          Featherless AI
        </h2>
        <span className="chip chip-accent">final stage</span>
      </div>

      <div className="card-body space-y-3">
        {error && (
          <div className="error-banner">
            <TriangleAlert size={14} className="mt-0.5 shrink-0 text-danger" />
            <p className="min-w-0 break-words">{error}</p>
          </div>
        )}

        {!enabled ? (
          <div className="flex items-center gap-3 rounded-md border border-edge bg-panel-2 px-3 py-3">
            <Sparkles size={16} className="shrink-0 text-ink-faint" />
            <p className="text-[12px] leading-relaxed text-ink-muted">
              Run <span className="font-medium text-ink">Optimize Context</span> first — the diagnosis
              is generated from the compressed context, not the whole repository.
            </p>
          </div>
        ) : !result ? (
          <>
            <p className="text-[12px] leading-relaxed text-ink-muted">
              Sends{" "}
              <span className="font-mono text-ink">
                {optimizedTokens !== null ? `${formatInt(optimizedTokens)} tokens` : "—"}
              </span>{" "}
              of optimized context plus your question to Featherless AI for a diagnosis.
            </p>
            <button type="button" className="btn btn-primary w-full" onClick={onAsk} disabled={asking}>
              {asking ? <LoaderCircle size={14} className="animate-spin" /> : <Sparkles size={14} />}
              {asking ? "Diagnosing…" : "Ask Featherless AI"}
            </button>
          </>
        ) : (
          <>
            <div>
              <p className="stat-label mb-1.5">AI diagnosis</p>
              <div className="rounded-md border border-edge bg-panel-2 px-3 py-2.5">
                <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-ink">{result.answer}</p>
              </div>
            </div>

            {result.files_used.length > 0 && (
              <div>
                <p className="stat-label mb-1.5">Files used</p>
                <div className="flex flex-wrap gap-1">
                  {result.files_used.map((file) => (
                    <span key={file} className="chip" title={file}>
                      {file}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div className="flex items-center gap-2">
              <button type="button" className="btn btn-secondary shrink-0" onClick={onAsk} disabled={asking}>
                {asking ? <LoaderCircle size={14} className="animate-spin" /> : <Sparkles size={14} />}
                Ask again
              </button>
              <span className="min-w-0 truncate text-[11px] text-ink-faint" title={question}>
                on: “{question}”
              </span>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
