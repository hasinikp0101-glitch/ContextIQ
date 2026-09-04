import { formatInt, ratioNote } from "../utils/format";
import type { ContextOptimizeResponse } from "../api/types";

function Stat({ label, value, tone = "text-ink" }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-edge bg-panel px-4 py-3">
      <p className="stat-label">{label}</p>
      <p className={`mt-1 font-mono text-[19px] font-semibold leading-6 tabular-nums ${tone}`}>
        {value}
      </p>
    </div>
  );
}

export function MetricsDashboard({ data }: { data: ContextOptimizeResponse }) {
  const m = data.metrics;
  const optimizedShare =
    m.original_tokens > 0 ? Math.min(100, (m.optimized_tokens / m.original_tokens) * 100) : 0;
  const savedShare = Math.max(0, 100 - optimizedShare);
  const note = ratioNote(m.compression_ratio);

  return (
    <section aria-label="Optimization metrics" className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <div className="col-span-2 rounded-lg border border-ok/25 bg-ok-soft/40 px-4 py-3.5">
        <div className="flex items-baseline justify-between gap-2">
          <p className="stat-label text-ok">Tokens saved</p>
          {note && <span className="font-mono text-[11px] text-ok/80">{note}</span>}
        </div>
        <p className="mt-1 font-mono text-[30px] font-semibold leading-8 tabular-nums text-ok">
          {formatInt(m.tokens_saved)}
        </p>
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-panel-2" title={`${m.reduction_percentage}% of original tokens removed`}>
          <div className="h-full rounded-full bg-ok/70" style={{ width: `${Math.max(2, savedShare)}%` }} />
        </div>
        <div className="mt-1.5 flex flex-wrap justify-between gap-x-3 font-mono text-[10.5px] text-ink-faint">
          <span>original {formatInt(m.original_tokens)}</span>
          <span className="text-ok">{m.reduction_percentage}% reduction</span>
          <span>optimized {formatInt(m.optimized_tokens)}</span>
        </div>
      </div>

      <Stat label="Files analyzed" value={formatInt(data.total_candidates)} />
      <Stat label="Relevant files" value={formatInt(data.total_selected)} tone="text-ok" />
      <Stat label="Excluded files" value={formatInt(data.total_excluded)} tone="text-ink-muted" />
      <Stat label="Original tokens" value={formatInt(m.original_tokens)} />
      <Stat label="Optimized tokens" value={formatInt(m.optimized_tokens)} tone="text-accent" />
      <Stat label="Compression ratio" value={`${m.compression_ratio}×`} />
    </section>
  );
}
