import { Boxes } from "lucide-react";
import { HealthBadge } from "./HealthBadge";

export function Header() {
  return (
    <header className="sticky top-0 z-20 border-b border-edge bg-canvas/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-[1440px] items-center gap-3 px-4 sm:px-6">
        <div className="grid h-7 w-7 shrink-0 place-items-center rounded-md border border-edge-strong bg-panel-2 text-accent">
          <Boxes size={15} />
        </div>
        <div className="flex min-w-0 items-baseline gap-3">
          <span className="shrink-0 text-[15px] font-semibold tracking-tight text-ink">
            ContextForge
          </span>
          <span className="hidden truncate text-[12px] text-ink-faint sm:block">
            Give AI the context it actually needs.
          </span>
        </div>
        <div className="ml-auto shrink-0">
          <HealthBadge />
        </div>
      </div>
    </header>
  );
}
