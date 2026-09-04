import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { HealthResponse } from "../api/types";

export function HealthBadge() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [state, setState] = useState<"checking" | "up" | "down">("checking");

  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      try {
        const result = await api.health();
        if (!cancelled) {
          setHealth(result);
          setState("up");
        }
      } catch {
        if (!cancelled) setState("down");
      }
    };

    void check();
    const interval = window.setInterval(check, 15_000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  const connected = state === "up";
  return (
    <div className="flex items-center gap-2 rounded-md border border-edge bg-panel px-2.5 py-1.5">
      <span
        className={`h-2 w-2 rounded-full ${
          connected
            ? "bg-ok shadow-[0_0_6px_rgba(63,185,80,0.55)]"
            : state === "down"
              ? "bg-danger"
              : "bg-ink-faint"
        }`}
      />
      <span className="text-[12px] font-medium text-ink-muted">
        {connected ? "Backend connected" : state === "down" ? "Backend unavailable" : "Checking backend…"}
      </span>
      {connected && health && (
        <span className="hidden font-mono text-[11px] text-ink-faint md:inline">
          v{health.version}
        </span>
      )}
    </div>
  );
}
