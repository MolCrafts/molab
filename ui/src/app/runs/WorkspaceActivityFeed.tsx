import type { JSX } from "react";
import {
  ACTIVITY_FALLBACK_POLL_MS,
  useFallbackInterval,
  useWorkspaceEventsQuery,
} from "@/app/state/queries";
import {
  WorkbenchAction,
  WorkbenchOperationState,
  WorkbenchRetryAction,
} from "@/components/workbench";
import { formatRelative, formatTimestamp } from "@/lib/format-time";
import { cn } from "@/lib/utils";
import {
  eventVisualFor,
  FEED_EMPTY_TEXT,
  resolveEventRef,
  type WorkspaceEventRow,
} from "./activityFeed";

interface WorkspaceActivityFeedProps {
  /** Run ids the snapshot currently knows — resolvable refs become links. */
  knownRunIds: ReadonlySet<string>;
  onSelectRun: (runId: string) => void;
  onOpenKnowledge: (path: string) => void;
  max?: number;
}

/**
 * The workspace-wide "what just happened" feed (vision-loop-12): a poll over
 * `GET /api/events` — the event spine's global read — rendered with entity
 * links resolved against the snapshot.
 */
export const WorkspaceActivityFeed = ({
  knownRunIds,
  onSelectRun,
  onOpenKnowledge,
  max = 20,
}: WorkspaceActivityFeedProps): JSX.Element => {
  // The spine publishes a change for every append, so the stream invalidates
  // this key; the interval is only a fallback for when the stream is down.
  const fallback = useFallbackInterval(ACTIVITY_FALLBACK_POLL_MS);
  const query = useWorkspaceEventsQuery(max, { refetchInterval: fallback });
  const events = (query.data ?? []) as WorkspaceEventRow[];
  const error = query.error ? String(query.error) : null;
  const loading = query.isPending;

  if (loading && events.length === 0 && !error) {
    return <WorkbenchOperationState kind="loading" density="compact" skeletonRows={3} />;
  }
  if (error && events.length === 0) {
    return (
      <WorkbenchOperationState
        kind="error"
        density="compact"
        title="Could not load activity"
        detail={error}
        action={<WorkbenchRetryAction onClick={() => void query.refetch()} />}
      />
    );
  }
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
                "mt-1 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full",
                visual.dotClass,
              )}
            >
              <Icon className="h-2.5 w-2.5 text-background" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate font-medium text-foreground">
                  {visual.label}
                  <span className="ml-2 font-normal text-muted-foreground">· {event.actor}</span>
                </span>
                <span
                  className="shrink-0 tabular-nums text-micro text-muted-foreground"
                  title={formatTimestamp(event.created_at)}
                >
                  {formatRelative(event.created_at)}
                </span>
              </div>
              <span className="mt-1 flex flex-wrap gap-x-2 font-mono text-micro text-muted-foreground">
                {event.refs.map((ref) => {
                  const resolved = resolveEventRef(ref, event.type, knownRunIds, event.payload);
                  if (resolved.kind === "run") {
                    return (
                      <WorkbenchAction
                        kind="ghost"
                        size="content"
                        key={ref}
                        type="button"
                        className="truncate text-accent underline-offset-2 hover:underline"
                        onClick={() => onSelectRun(resolved.runId)}
                      >
                        {resolved.text}
                      </WorkbenchAction>
                    );
                  }
                  if (resolved.kind === "knowledge") {
                    return (
                      <WorkbenchAction
                        kind="ghost"
                        size="content"
                        key={ref}
                        type="button"
                        className="truncate text-accent underline-offset-2 hover:underline"
                        onClick={() => onOpenKnowledge(resolved.path)}
                      >
                        {resolved.text}
                      </WorkbenchAction>
                    );
                  }
                  return (
                    <span key={ref} className="truncate">
                      {resolved.text}
                    </span>
                  );
                })}
              </span>
            </div>
          </li>
        );
      })}
    </ol>
  );
};
