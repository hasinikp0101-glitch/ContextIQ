import { ScanSearch } from "lucide-react";
import type { QueryAnalysisResponse } from "../api/types";

function ChipRow({ label, values }: { label: string; values: string[] }) {
  return (
    <div>
      <p className="stat-label mb-1">{label}</p>
      {values.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {values.slice(0, 12).map((value) => (
            <span key={value} className="chip" title={value}>
              {value}
            </span>
          ))}
        </div>
      ) : (
        <p className="text-[11px] text-ink-faint">none detected</p>
      )}
    </div>
  );
}

export function QueryAnalysis({ analysis }: { analysis: QueryAnalysisResponse | null }) {
  if (!analysis) return null;

  return (
    <section className="card">
      <div className="card-header">
        <h2 className="card-title flex items-center gap-1.5">
          <ScanSearch size={12} className="text-accent" />
          Query analysis
        </h2>
        <span className="chip chip-accent" title="Detected developer intent">
          {analysis.intent}
        </span>
      </div>
      <div className="card-body space-y-3">
        {!analysis.valid && (
          <div className="rounded-md border border-warn/40 bg-warn-soft px-3 py-2 text-[11px] leading-relaxed text-ink">
            The query did not parse cleanly — ranking may be less precise.
          </div>
        )}
        <ChipRow label="Keywords" values={analysis.keywords} />
        <ChipRow label="Technical terms" values={analysis.technical_terms} />
        <ChipRow label="Actions" values={analysis.actions} />
        <ChipRow label="Topics" values={analysis.topics} />
      </div>
    </section>
  );
}
