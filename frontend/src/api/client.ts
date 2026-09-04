import type {
  ContextOptimizeRequest,
  ContextOptimizeResponse,
  HealthResponse,
  LLMAskRequest,
  LLMAskResponse,
  ProjectAnalyzeRequest,
  ProjectAnalyzeResponse,
} from "./types";

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/+$/, "");

/** HTTP failure from the ContextForge API, carrying a status and developer-readable detail. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

interface FastAPIValidationItem {
  loc?: (string | number)[];
  msg?: string;
}

function extractDetail(body: unknown, fallback: string): string {
  if (body !== null && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string" && detail.trim().length > 0) {
      return detail;
    }
    // FastAPI validation errors arrive as an array of {loc, msg} items.
    if (Array.isArray(detail)) {
      const parts = (detail as FastAPIValidationItem[]).map((item) => {
        const loc = item.loc?.join(".");
        return loc ? `${loc}: ${item.msg ?? "invalid"}` : (item.msg ?? "invalid");
      });
      if (parts.length > 0) return parts.join("; ");
    }
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError(
      0,
      `Cannot reach the backend at ${API_BASE_URL}. Make sure the FastAPI server is running (uvicorn main:app --port 8000).`,
    );
  }

  const text = await response.text();
  let body: unknown = null;
  if (text.length > 0) {
    try {
      body = JSON.parse(text);
    } catch {
      throw new ApiError(
        response.status,
        `Malformed response from ${path} (HTTP ${response.status}): expected JSON but received non-JSON content.`,
      );
    }
  }

  if (!response.ok) {
    const fallback = `Request to ${path} failed with HTTP ${response.status} ${response.statusText}.`;
    throw new ApiError(response.status, extractDetail(body, fallback));
  }

  return body as T;
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),

  analyzeProject: (payload: ProjectAnalyzeRequest) =>
    request<ProjectAnalyzeResponse>("/api/projects/analyze", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  optimizeContext: (payload: ContextOptimizeRequest) =>
    request<ContextOptimizeResponse>("/api/context/optimize", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  askLLM: (payload: LLMAskRequest) =>
    request<LLMAskResponse>("/api/llm/ask", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
