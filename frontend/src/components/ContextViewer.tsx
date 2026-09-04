import { useMemo, useState } from "react";
import { Check, Copy, FileCode2 } from "lucide-react";
import { formatInt, parseContextBlocks } from "../utils/format";

export function ContextViewer({ context, optimizedTokens }: { context: string; optimizedTokens: number }) {
  const blocks = useMemo(() => parseContextBlocks(context), [context]);
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(context);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard access denied — leave the button state untouched.
    }
  };

  return (
    <section className="card overflow-hidden">
      <div className="card-header">
        <h2 className="card-title">Optimized context</h2>
        <div className="flex items-center gap-1.5">
          <span className="chip chip-accent" title="Token count from the backend metrics engine">
            {formatInt(optimizedTokens)} tokens
          </span>
          <span className="chip" title="File boundaries detected in the compressed context">
            {blocks.length} {blocks.length === 1 ? "file" : "files"}
          </span>
          <button
            type="button"
            onClick={copy}
            className="grid h-6 w-6 place-items-center rounded border border-edge-strong bg-panel-2 text-ink-muted transition-colors hover:text-ink"
            aria-label="Copy optimized context"
            title="Copy raw optimized context"
          >
            {copied ? <Check size={12} className="text-ok" /> : <Copy size={12} />}
          </button>
        </div>
      </div>

      <div className="max-h-[420px] overflow-y-auto bg-deep">
        {blocks.length === 0 ? (
          <p className="px-4 py-6 font-mono text-[12px] text-ink-faint">(empty context)</p>
        ) : (
          blocks.map((block, i) => (
            <div key={block.path ?? `preamble-${i}`}>
              <div className="sticky top-0 z-10 flex items-center gap-2 border-y border-edge bg-panel-2 px-3 py-1.5">
                <FileCode2 size={12} className="shrink-0 text-accent" />
                <span
                  className="min-w-0 truncate font-mono text-[11px] text-ink-muted"
                  title={block.path ?? undefined}
                >
                  {block.path ?? "context"}
                </span>
                <span className="ml-auto shrink-0 font-mono text-[10px] text-ink-faint">
                  {block.content ? block.content.split("\n").length : 0} lines
                </span>
              </div>
              <pre className="overflow-x-auto px-3 py-2 font-mono text-[11.5px] leading-[1.6] text-ink-muted">
                {block.content || "(empty)"}
              </pre>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
