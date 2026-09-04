import { useState } from "react";
import { CheckCheck, CircleSlash } from "lucide-react";
import type { ExcludedFileResponse, SelectedFileResponse } from "../api/types";
import { formatInt } from "../utils/format";

export function FileList({
  selected,
  excluded,
}: {
  selected: SelectedFileResponse[];
  excluded: ExcludedFileResponse[];
}) {
  const [tab, setTab] = useState<"selected" | "excluded">("selected");
  const sorted = [...selected].sort((a, b) => a.selection_order - b.selection_order);
  const maxTokens = Math.max(1, ...selected.map((f) => f.token_count));

  const tabClass = (active: boolean) =>
    `flex items-center gap-1.5 rounded px-2 py-1 text-[12px] font-medium transition-colors ${
      active ? "bg-panel-3 text-ink" : "text-ink-faint hover:text-ink-muted"
    }`;

  return (
    <section className="card">
      <div className="card-header">
        <div className="flex items-center gap-1">
          <button type="button" className={tabClass(tab === "selected")} onClick={() => setTab("selected")}>
            <CheckCheck size={12} className="text-ok" />
            Selected
            <span className="font-mono text-[11px] text-ink-faint">{selected.length}</span>
          </button>
          <button type="button" className={tabClass(tab === "excluded")} onClick={() => setTab("excluded")}>
            <CircleSlash size={12} />
            Excluded
            <span className="font-mono text-[11px] text-ink-faint">{excluded.length}</span>
          </button>
        </div>
        <span className="hidden font-mono text-[10px] text-ink-faint sm:block">
          {tab === "selected" ? "sorted by selection order" : "intentional noise reduction"}
        </span>
      </div>

      <div className="max-h-80 divide-y divide-edge overflow-y-auto">
        {tab === "selected" ? (
          sorted.length === 0 ? (
            <p className="px-4 py-6 text-center text-[12px] text-ink-faint">No files were selected.</p>
          ) : (
            sorted.map((file) => (
              <div key={file.path} className="px-4 py-2">
                <div className="flex items-center gap-2">
                  <span className="chip chip-accent shrink-0" title="Selection order">
                    #{file.selection_order}
                  </span>
                  <span className="min-w-0 flex-1 truncate font-mono text-[12px] text-ink" title={file.path}>
                    {file.path}
                  </span>
                  <span className="chip shrink-0" title="Relevance score">
                    score {file.relevance_score}
                  </span>
                  <span className="chip shrink-0" title="Token count">
                    {formatInt(file.token_count)} tok
                  </span>
                </div>
                <div className="mt-1.5 h-0.5 rounded-full bg-panel-2" title={`${formatInt(file.token_count)} tokens`}>
                  <div
                    className="h-full rounded-full bg-accent/50"
                    style={{ width: `${Math.max(3, (file.token_count / maxTokens) * 100)}%` }}
                  />
                </div>
              </div>
            ))
          )
        ) : excluded.length === 0 ? (
          <p className="px-4 py-6 text-center text-[12px] text-ink-faint">Nothing was excluded.</p>
        ) : (
          excluded.map((file) => (
            <div key={file.path} className="px-4 py-2">
              <div className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate font-mono text-[12px] text-ink-muted" title={file.path}>
                  {file.path}
                </span>
                <span className="chip shrink-0" title="Relevance score">
                  score {file.relevance_score}
                </span>
                <span className="chip shrink-0" title="Token count">
                  {file.token_count !== null ? `${formatInt(file.token_count)} tok` : "—"}
                </span>
              </div>
              <p className="mt-1 text-[11px] text-ink-faint">{file.reason.replaceAll("_", " ")}</p>
            </div>
          ))
        )}
      </div>

      {tab === "excluded" && excluded.length > 0 && (
        <p className="border-t border-edge px-4 py-2 text-[11px] leading-relaxed text-ink-faint">
          Repository noise — ContextForge intentionally left these files out so the token budget is
          spent on relevant code only.
        </p>
      )}
    </section>
  );
}
