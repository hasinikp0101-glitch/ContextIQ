import { ArrowRight, Bot, FileCode2, FolderSearch, ListOrdered, MessageSquare } from "lucide-react";

const FLOW = [
  { label: "Developer question", icon: MessageSquare },
  { label: "Repository scan", icon: FolderSearch },
  { label: "Relevant files", icon: ListOrdered },
  { label: "Optimized context", icon: FileCode2 },
  { label: "AI diagnosis", icon: Bot },
] as const;

export function EmptyState({ hasScan, busy }: { hasScan: boolean; busy: boolean }) {
  return (
    <section className="card">
      <div className="card-body flex min-h-[440px] flex-col items-center justify-center gap-7 py-14 text-center">
        <div className="max-w-md space-y-2">
          <h2 className="text-[15px] font-semibold text-ink">Nothing analyzed yet</h2>
          <p className="text-[13px] leading-relaxed text-ink-muted">
            Point ContextForge at a local repository path or a public GitHub URL and
            ask a development question. We&rsquo;ll determine which files actually
            matter.
          </p>
        </div>

        <ol className="flex max-w-2xl flex-wrap items-center justify-center gap-x-1.5 gap-y-2">
          {FLOW.map((step, i) => {
            const Icon = step.icon;
            return (
              <li key={step.label} className="flex items-center gap-1.5">
                {i > 0 && <ArrowRight size={12} className="text-ink-faint" />}
                <span className="chip gap-1.5 px-2 py-1">
                  <Icon size={11} className="shrink-0 text-accent" />
                  {step.label}
                </span>
              </li>
            );
          })}
        </ol>

        {busy ? (
          <div className="w-full max-w-sm space-y-2.5">
            <p className="font-mono text-[11px] text-accent">
              Running the ContextForge pipeline — scanning, ranking, selecting, compressing…
            </p>
            <div className="h-1 overflow-hidden rounded-full bg-panel-2">
              <div className="h-full w-1/3 animate-pulse rounded-full bg-accent/60" />
            </div>
          </div>
        ) : (
          <p className="max-w-sm text-[11.5px] leading-relaxed text-ink-faint">
            {hasScan
              ? "Scan complete — add a development question and run Optimize Context to see metrics, selected files, and the compressed context."
              : "All results on this dashboard come straight from the local FastAPI pipeline — no mock data."}
          </p>
        )}
      </div>
    </section>
  );
}
