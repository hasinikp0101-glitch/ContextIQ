import { FolderSearch } from "lucide-react";
import type { ProjectAnalyzeResponse } from "../api/types";
import { formatInt, truncateMiddle } from "../utils/format";

export function ScanSummary({ analysis }: { analysis: ProjectAnalyzeResponse | null }) {
  if (!analysis) return null;

  const s = analysis.summary;
  const stats: Array<[label: string, value: number]> = [
    ["Total files", s.total_files],
    ["Source", s.source_files],
    ["Config", s.config_files],
    ["Test", s.test_files],
    ["Ignored", s.ignored_files],
    ["Kept", s.kept_files_count],
    ["Filtered out", s.filtered_files_count],
    ["Analyzed", s.analyzed_files_count],
  ];

  return (
    <section className="card">
      <div className="card-header">
        <h2 className="card-title flex items-center gap-1.5">
          <FolderSearch size={12} className="text-accent" />
          Repository scan
        </h2>
        <span className="font-mono text-[10px] text-ink-faint" title={analysis.project_path}>
          {truncateMiddle(analysis.project_path, 30)}
        </span>
      </div>
      <div className="card-body">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5">
          {stats.map(([label, value]) => (
            <div key={label}>
              <dt className="stat-label">{label}</dt>
              <dd className="mt-0.5 font-mono text-[15px] font-semibold tabular-nums text-ink">
                {formatInt(value)}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}
