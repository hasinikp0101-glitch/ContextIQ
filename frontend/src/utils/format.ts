export function formatInt(value: number): string {
  return value.toLocaleString("en-US");
}

export function truncateMiddle(text: string, max = 40): string {
  if (text.length <= max) return text;
  const head = Math.ceil((max - 1) / 2);
  const tail = max - 1 - head;
  return `${text.slice(0, head)}…${text.slice(-tail)}`;
}

/**
 * The backend defines compression_ratio = optimized_tokens / original_tokens,
 * so anything below 1 means the context shrank.
 */
export function ratioNote(ratio: number): string | null {
  if (!Number.isFinite(ratio) || ratio <= 0) return null;
  if (ratio < 0.999) return `${(1 / ratio).toFixed(1)}× smaller`;
  if (ratio > 1.001) return `expanded ${((ratio - 1) * 100).toFixed(1)}%`;
  return null;
}

/**
 * The compressor assembles the optimized context as blocks separated by
 * `===== FILE: <path> =====` header lines (see backend/app/compressor).
 * Split on those markers so the viewer can render real file boundaries.
 */
const FILE_HEADER = /^===== FILE: (.+?) =====$/gm;

export interface ContextBlock {
  path: string | null;
  content: string;
}

export function parseContextBlocks(context: string): ContextBlock[] {
  const matches = [...context.matchAll(FILE_HEADER)];
  if (matches.length === 0) {
    return context.trim().length > 0 ? [{ path: null, content: context.trim() }] : [];
  }

  const blocks: ContextBlock[] = [];

  const first = matches[0];
  if (first && first.index !== undefined && first.index > 0) {
    const preamble = context.slice(0, first.index).trim();
    if (preamble) blocks.push({ path: null, content: preamble });
  }

  matches.forEach((match, i) => {
    const next = matches[i + 1];
    const start = (match.index ?? 0) + match[0].length;
    const end = next?.index ?? context.length;
    const content = context.slice(start, end).replace(/^\n+/, "").replace(/\s+$/, "");
    blocks.push({ path: match[1] ?? "unknown", content });
  });

  return blocks;
}
