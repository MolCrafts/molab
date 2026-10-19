import { AlertCircle, ArrowUpRight, RefreshCw } from "lucide-react";
import type { JSX } from "react";
import { Link } from "react-router-dom";

import type {
  DashboardAttentionItem,
  DashboardAttentionOverflow,
} from "@/app/dashboard/dashboardModel";
import { WorkbenchIconAction } from "@/components/workbench";
import { cn } from "@/lib/utils";

const countedProblems = (label: string): string =>
  `${label} ${label === "View 1 more" ? "workspace problem" : "workspace problems"}`;

interface DashboardAttentionProps {
  items: readonly DashboardAttentionItem[];
  overflow: DashboardAttentionOverflow | null;
  retrying: boolean;
  onRetry: () => void;
}

/**
 * Operational blockers for the dashboard inventory.
 * One region, not a card per workspace. Failed runs are a separate list.
 */
export const DashboardAttention = ({
  items,
  overflow,
  retrying,
  onRetry,
}: DashboardAttentionProps): JSX.Element | null => {
  if (items.length === 0) return null;

  const criticalList = items.some((item) => item.tone === "critical");

  return (
    <section
      aria-label="Workspace problems"
      aria-live="assertive"
      className="border-b border-border"
    >
      <ul>
        {items.map((item) => {
          const critical = item.tone === "critical";
          return (
            <li
              key={item.id}
              className={cn(
                "flex min-w-0 flex-wrap items-start gap-x-3 gap-y-2 px-6 py-2",
                critical ? "bg-status-failed-soft" : "bg-status-warning-soft",
              )}
            >
              <AlertCircle
                className={cn(
                  "mt-1 size-icon-sm shrink-0",
                  critical ? "text-status-failed-foreground" : "text-status-warning-foreground",
                )}
                aria-hidden
              />
              <div className="min-w-0 flex-1 basis-48">
                <p
                  className={cn(
                    "break-words text-body font-medium",
                    critical ? "text-status-failed-foreground" : "text-status-warning-foreground",
                  )}
                >
                  {item.title}
                </p>
                <p
                  className={cn(
                    "break-words text-label",
                    critical
                      ? "text-status-failed-foreground/90"
                      : "text-status-warning-foreground/90",
                  )}
                >
                  {item.detail}
                </p>
              </div>
              {item.retry === "runs" ? (
                <WorkbenchIconAction label={item.actionLabel} onClick={onRetry} disabled={retrying}>
                  <RefreshCw aria-hidden />
                </WorkbenchIconAction>
              ) : item.href ? (
                <WorkbenchIconAction label={item.actionLabel} asChild>
                  <Link to={item.href}>
                    <ArrowUpRight aria-hidden />
                  </Link>
                </WorkbenchIconAction>
              ) : null}
            </li>
          );
        })}
      </ul>
      {overflow ? (
        <p
          className={cn(
            "px-6 py-2 text-label",
            criticalList
              ? "bg-status-failed-soft text-status-failed-foreground"
              : "bg-status-warning-soft text-status-warning-foreground",
          )}
        >
          {overflow.href ? (
            <Link
              to={overflow.href}
              className="rounded-control underline-offset-2 outline-none hover:underline focus-visible:ring-1 focus-visible:ring-ring"
            >
              {countedProblems(overflow.label)}
            </Link>
          ) : (
            countedProblems(overflow.label)
          )}
        </p>
      ) : null}
    </section>
  );
};
