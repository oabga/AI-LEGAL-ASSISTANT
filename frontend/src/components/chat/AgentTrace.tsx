import { useState } from "react";
import { AlertTriangle, Check, ChevronDown, CircleDashed, X } from "lucide-react";

import type { AgentTraceStep, ProgressStatus } from "@/lib/types";
import { cn, formatDuration } from "@/lib/utils";

const STATUS_ICONS: Record<ProgressStatus, typeof Check> = {
  started: CircleDashed,
  running: CircleDashed,
  completed: Check,
  warning: AlertTriangle,
  error: X,
};

const STATUS_COLORS: Record<ProgressStatus, string> = {
  started: "text-muted",
  running: "text-brand",
  completed: "text-ok",
  warning: "text-warn",
  error: "text-danger",
};

/** Dòng thời gian các bước agent đã chạy, thu gọn được. */
export function AgentTrace({
  steps,
  running,
  defaultOpen = false,
}: {
  steps: AgentTraceStep[];
  running?: boolean;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  if (!steps.length) return null;

  const current = steps[steps.length - 1];

  return (
    <div className="rounded-xl border border-line-soft bg-surface/60">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-muted hover:text-ink"
      >
        <ChevronDown
          className={cn("size-3.5 shrink-0 transition-transform", !open && "-rotate-90")}
          aria-hidden
        />
        <span className="font-medium">Quá trình xử lý</span>
        <span className="text-muted-2">({steps.length} bước)</span>
        {running && (
          <span className="ml-auto flex items-center gap-1.5 text-brand">
            <span className="size-1.5 animate-trace-pulse rounded-full bg-brand" />
            {current.title}
          </span>
        )}
      </button>

      {open && (
        <ol className="space-y-2.5 border-t border-line-soft px-3 py-3">
          {steps.map((step, index) => {
            const Icon = STATUS_ICONS[step.status];
            const isActive = running && index === steps.length - 1;
            return (
              <li key={`${step.stage}-${index}`} className="flex gap-2.5 text-xs">
                <Icon
                  className={cn(
                    "mt-0.5 size-3.5 shrink-0",
                    STATUS_COLORS[step.status],
                    isActive && "animate-trace-pulse",
                  )}
                  aria-hidden
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-2">
                    <span className="font-medium text-ink">{step.title}</span>
                    {step.elapsedMs != null && (
                      <span className="text-muted-2">{formatDuration(step.elapsedMs)}</span>
                    )}
                  </div>
                  <p className="mt-0.5 text-muted">{step.detail}</p>

                  {!!step.topResults?.length && (
                    <ul className="mt-1.5 space-y-1">
                      {step.topResults.slice(0, 5).map((result, position) => (
                        <li
                          key={`${result.law_id}-${result.article}-${position}`}
                          className="flex items-baseline gap-1.5 text-muted-2"
                        >
                          <span className="text-muted-2">#{result.rank ?? position + 1}</span>
                          <span className="min-w-0 flex-1 truncate text-muted">
                            {result.article} — {result.article_title || result.law_name}
                          </span>
                          {result.score != null && (
                            <span className="tabular-nums">{result.score.toFixed(3)}</span>
                          )}
                          {result.passed_threshold === false && (
                            <span className="text-warn">loại</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
