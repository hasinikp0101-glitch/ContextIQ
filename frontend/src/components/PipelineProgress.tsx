import {
  Braces,
  Check,
  CheckCheck,
  CircleCheck,
  ListOrdered,
  LoaderCircle,
  Search,
  Shrink,
  X,
} from "lucide-react";

export type PipelineStatus = "idle" | "running" | "done" | "error";

export interface PipelineProgressProps {
  status: PipelineStatus;
  activeIndex: number;
  completedCount: number;
}

const STAGES = [
  { label: "Scanning", hint: "Walk the repository tree", icon: Search },
  { label: "Analyzing", hint: "Parse code structure", icon: Braces },
  { label: "Ranking", hint: "Score relevance to the question", icon: ListOrdered },
  { label: "Selecting", hint: "Fit files into the token budget", icon: CheckCheck },
  { label: "Compressing", hint: "Strip noise, keep signal", icon: Shrink },
  { label: "Ready", hint: "Optimized context prepared", icon: CircleCheck },
] as const;

export function PipelineProgress({ status, activeIndex, completedCount }: PipelineProgressProps) {
  return (
    <section className="card">
      <div className="card-header">
        <h2 className="card-title">Pipeline</h2>
        {status === "running" && <span className="chip chip-accent">running</span>}
        {status === "done" && <span className="chip chip-ok">complete</span>}
        {status === "error" && <span className="chip chip-danger">failed</span>}
      </div>
      <div className="card-body">
        <ol>
          {STAGES.map((stage, i) => {
            const done = status === "done" || i < completedCount;
            const active = status === "running" && i === activeIndex;
            const failed = status === "error" && i === activeIndex;
            const Icon = stage.icon;
            const boxClass = done
              ? "border-ok/40 bg-ok-soft text-ok"
              : active
                ? "border-accent/50 bg-accent-soft text-accent"
                : failed
                  ? "border-danger/40 bg-danger-soft text-danger"
                  : "border-edge bg-panel-2 text-ink-faint";
            const labelClass = done
              ? "text-ink"
              : active
                ? "text-accent"
                : failed
                  ? "text-danger"
                  : "text-ink-muted";

            return (
              <li key={stage.label} className="relative flex gap-3 pb-4 last:pb-0">
                {i < STAGES.length - 1 && (
                  <span
                    aria-hidden
                    className="absolute left-[13px] top-8 h-[calc(100%-32px)] w-px bg-edge"
                  />
                )}
                <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-md border ${boxClass}`}>
                  <Icon size={13} />
                </span>
                <div className="min-w-0 pt-0.5">
                  <p className={`text-[13px] font-medium ${labelClass}`}>{stage.label}</p>
                  <p className="text-[11px] text-ink-faint">{stage.hint}</p>
                </div>
                <span className="ml-auto shrink-0 self-start pt-1.5">
                  {active && <LoaderCircle size={13} className="animate-spin text-accent" />}
                  {done && !active && <Check size={13} className="text-ok" />}
                  {failed && <X size={13} className="text-danger" />}
                </span>
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
