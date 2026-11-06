import type { JSX } from "react";
import { useMemo } from "react";

import { WorkbenchAction, WorkbenchOperationState } from "@/components/workbench";
import { formatRelative, formatTimestamp } from "@/lib/format-time";
import { cn } from "@/lib/utils";

import { type ActivityRun, eventsFromRuns, eventVisualFor, FEED_EMPTY_TEXT } from "./activityFeed";

interface WorkspaceActivityFeedProps {
  runs: readonly ActivityRun[];
  onSelectRun: (runId: string) => void;
  max?: number;
  eventType?: string | null;
}

export const WorkspaceActivityFeed = ({
  runs,
  onSelectRun,
  max = 20,
  eventType = null,
}: WorkspaceActivityFeedProps): JSX.Element => {
  const events = useMemo(() => eventsFromRuns(runs, eventType, max), [runs, eventType, max]);

  if (events.length === 0) {
    return <WorkbenchOperationState kind="empty" density="compact" title={FEED_EMPTY_TEXT} />;
  }

  return (
    <ol className="space-y-1">
      {events.map((event) => {
        const visual = eventVisualFor(event.type);
        const Icon = visual.icon;
        return (
          <li
            key={event.id}
            className="flex items-start gap-3 rounded-control px-2 py-2 text-label transition-colors duration-(--motion-fast) ease-standard hover:bg-interactive/50"
          >
            <span
              aria-hidden="true"
              className={cn(
                "mt-1 inline-flex size-4-lg shrink-0 items-center justify-center rounded-full",
                visual.dotClass,
              )}
            >
              <Icon className="h-2.5 w-2.5 text-background" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate font-medium text-foreground">{visual.label}</span>
                <span
                  className="shrink-0 tabular-nums text-micro text-muted-foreground"
                  title={formatTimestamp(event.created_at)}
                >
                  {formatRelative(event.created_at)}
                </span>
              </div>
              <span className="mt-1 flex flex-wrap gap-x-2 font-mono text-micro text-muted-foreground">
                {event.refs.map((ref) => (
                  <WorkbenchAction
                    kind="ghost"
                    size="content"
                    key={ref}
                    type="button"
                    className="truncate text-accent underline-offset-2 hover:underline"
                    onClick={() => onSelectRun(ref)}
                  >
                    {ref}
                  </WorkbenchAction>
                ))}
              </span>
            </div>
          </li>
        );
      })}
    </ol>
  );
};
