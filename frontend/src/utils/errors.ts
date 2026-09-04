import { ApiError } from "../api/client";

/** Human-readable message for failed analyze/optimize requests. */
export function describeActionError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 0) return err.message;
    const detail = err.message.endsWith(".") ? err.message : `${err.message}.`;
    return `${detail} (HTTP ${err.status})`;
  }
  if (err instanceof Error) return err.message;
  return `Unexpected error: ${String(err)}`;
}

/** Human-readable message for failed /api/llm/ask requests, with fix hints. */
export function describeLLMError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 0) return err.message;
    if (err.status === 503) {
      return `${err.message} (HTTP 503) — set FEATHERLESS_API_KEY in backend/.env and restart the FastAPI server to enable AI diagnosis.`;
    }
    if (err.status === 502) {
      return `${err.message} (HTTP 502) — the model backend rejected or dropped the request. Try again in a moment.`;
    }
    const detail = err.message.endsWith(".") ? err.message : `${err.message}.`;
    return `${detail} (HTTP ${err.status})`;
  }
  if (err instanceof Error) return err.message;
  return `Unexpected error: ${String(err)}`;
}
