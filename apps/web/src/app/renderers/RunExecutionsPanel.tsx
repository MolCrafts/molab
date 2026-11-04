import { useQuery } from "@tanstack/react-query";
import { Network, TriangleAlert } from "lucide-react";
import { type JSX, type ReactNode, useMemo, useState } from "react";
import type { ExecutionOutputsResponse } from "@/api/generated/models/ExecutionOutputsResponse";
import {
  CopyButton,
  EmptyState,
  formatSpan,
  InventoryCanvas,
  OverviewSurface,
} from "@/app/components/entity";
import { listExecutionColumns, listExecutionDetails } from "@/app/registry";
import { formatDuration } from "@/app/renderers/dashboardData";
import {
  failedTask,
  failureHeadline,
  failureRecovery,
  preferredFailureOutput,
} from "@/app/renderers/run/executionFailure";
import { RunExecutionOutputs } from "@/app/renderers/run/RunExecutionOutputs";
import { TaskProductList } from "@/app/renderers/run/TaskProductList";
import { taskProducts } from "@/app/renderers/run/taskProducts";
import { PruneDialog } from "@/app/runs/PruneDialog";
import { groupForStatus } from "@/app/runs/statusGroups";
import { executionJournalQueryOptions, journalRefetchInterval } from "@/app/state/entityQueries";
import type { ExecutionRecordSummary, RunSummary, WorkflowSummary } from "@/app/types";
import {
  RunStatusBadge,
  WorkbenchIconAction,
  WorkbenchOperationState,
} from "@/components/workbench";
import { normalizeTaskGraph } from "@/components/workflow/flowgram-document";
import { WorkflowGraph } from "@/components/workflow/workflow-graph";
import type { ExecutionRowData } from "@/lib/contribution-types";
import { formatDateTime } from "@/lib/datetime";
import { cn } from "@/lib/utils";

const stringValue = (value: unknown): string | null =>
  typeof value === "string" && value.length > 0 ? value : null;

const instant = (value: string | null | undefined): number | null => {
  const parsed = value ? Date.parse(value) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : null;
};

/** Wall time of one attempt. In-flight work counts up to now. */
const attemptElapsed = (execution: ExecutionRecordSummary): string | null => {
  const startIso = execution.startedAt ?? execution.createdAt;
  const start = instant(startIso);
  if (start === null) return null;
  if (execution.finishedAt) return formatDuration(startIso, execution.finishedAt);
  return formatSpan((Date.now() - start) / 1000);
};

/** Shared time domain for the attempt bars — every attempt of one Run. */
interface AttemptWindow {
  from: number;
  span: number;
}

const attemptWindow = (history: ExecutionRecordSummary[]): AttemptWindow | null => {
  const now = Date.now();
  const starts = history
    .map((execution) => instant(execution.startedAt ?? execution.createdAt))
    .filter((value): value is number => value !== null);
  if (starts.length === 0) return null;
  const from = Math.min(...starts);
  const to = Math.max(
    ...history.map((execution) => instant(execution.finishedAt) ?? now),
    from + 1,
  );
  return { from, span: Math.max(1, to - from) };
};

const STATUS_FILL: Record<string, string> = {
  running: "bg-status-running",
  pending: "bg-status-queued",
  succeeded: "bg-status-completed",
  failed: "bg-status-failed",
  cancelled: "bg-status-cancelled",
};

/**
 * When this attempt ran, on the axis shared by every attempt of the Run — so
 * "did the retry get further, and was it slower" is read, not computed.
 */
const AttemptBar = ({
  execution,
  window,
}: {
  execution: ExecutionRecordSummary;
  window: AttemptWindow | null;
}): JSX.Element => {
  const duration = attemptElapsed(execution);
  const start = instant(execution.startedAt ?? execution.createdAt);
  const end = instant(execution.finishedAt) ?? Date.now();
  const group = groupForStatus(execution.status);
  const fill = (group && STATUS_FILL[group]) || "bg-muted-foreground/40";
  const left = window && start !== null ? ((start - window.from) / window.span) * 100 : 0;
  const width = window && start !== null ? Math.max(2, ((end - start) / window.span) * 100) : 0;
  return (
    <span className="flex min-w-0 items-center gap-2">
      <span aria-hidden className="relative h-3 min-w-8 flex-1 border-x border-border/60">
        {window && start !== null && (
          <span
            className={cn("absolute top-1/2 h-1.5 -translate-y-1/2 rounded-control", fill)}
            style={{ left: `${left}%`, width: `${Math.min(100 - left, width)}%` }}
          />
        )}
      </span>
      <span className="shrink-0 font-mono text-label tabular-nums text-muted-foreground">
        {duration ?? "—"}
      </span>
    </span>
  );
};

/** One attempt's fields. A two-column `<Table>` here is chrome around a `<dl>`. */
const PropertyRows = ({
  entries,
}: {
  entries: Array<{ label: string; value: ReactNode }>;
}): JSX.Element => (
  <dl className="grid gap-x-6 gap-y-2 border-y border-border py-3 sm:grid-cols-[minmax(0,10rem)_minmax(0,1fr)]">
    {entries.map((entry) => (
      <div key={entry.label} className="contents">
        <dt className="min-w-0 truncate text-label text-muted-foreground">{entry.label}</dt>
        <dd className="min-w-0 break-all font-mono text-label text-foreground">{entry.value}</dd>
      </div>
    ))}
  </dl>
);

const backendOf = (execution: ExecutionRecordSummary): string =>
  stringValue(execution.executor.backend) ?? stringValue(execution.executor.target) ?? "local";

const executionRow = (execution: ExecutionRecordSummary, runId: string): ExecutionRowData => ({
  executionId: execution.executionId,
  runId,
  status: execution.status,
  startedAt: execution.startedAt ?? execution.createdAt,
  finishedAt: execution.finishedAt,
  durationSeconds: null,
  schedulerJobId:
    stringValue(execution.executor.scheduler_job_id) ?? stringValue(execution.executor.job_id),
  backend: backendOf(execution),
  metadata: Object.fromEntries(
    Object.entries(execution.executor).map(([key, value]) => [
      key,
      typeof value === "string" ? value : JSON.stringify(value),
    ]),
  ),
});

interface RunExecutionsPanelProps {
  run: RunSummary;
  workflow?: WorkflowSummary;
  selectedExecutionId: string | null;
  onSelectExecution: (executionId: string) => void;
  onInspectTask: (taskId: string, runId: string) => void;
  onOpenWorkflow?: () => void;
  outputs: ExecutionOutputsResponse | null;
  logsError: string | null;
  onPromoted?: () => void;
}

export const RunExecutionsPanel = ({
  run,
  workflow,
  selectedExecutionId,
  onSelectExecution,
  onInspectTask,
  onOpenWorkflow,
  outputs,
  logsError,
  onPromoted,
}: RunExecutionsPanelProps): JSX.Element => {
  const history = run.executionHistory;
  const selected = history.find((item) => item.executionId === selectedExecutionId) ?? null;
  const selectedIndex = selected
    ? history.findIndex((item) => item.executionId === selected.executionId)
    : -1;
  const journal = useQuery({
    ...executionJournalQueryOptions(
      run.projectId,
      run.experimentId,
      run.id,
      selectedExecutionId ?? "",
    ),
    enabled: selectedExecutionId !== null,
    refetchInterval: journalRefetchInterval(selected?.status),
  });
  const graph = journal.data ? normalizeTaskGraph(journal.data) : null;
  const graphError = journal.error
    ? journal.error instanceof Error
      ? journal.error.message
      : "Failed to load execution workflow"
    : null;
  const graphLoading = journal.isLoading;
  const [pinned, setPinned] = useState<{ executionId: string; path: string } | null>(null);
  const pinnedPath =
    pinned && selected && pinned.executionId === selected.executionId ? pinned.path : null;
  const products = useMemo(
    () => (graph && selected ? taskProducts(graph.task_configs, selected.executionId) : []),
    [graph, selected],
  );
  const taskFailure = failedTask(graph);
  const headline = selected
    ? failureHeadline({ status: selected.status, error: selected.error, task: taskFailure })
    : null;
  const failureSelection = headline
    ? preferredFailureOutput(taskFailure?.id ?? null, outputs)
    : null;
  const recovery = headline ? failureRecovery(failureSelection) : null;

  const attemptSpan = attemptWindow(history);
  const row = selected ? executionRow(selected, run.id) : null;
  const columns = useMemo(() => listExecutionColumns(row?.backend), [row?.backend]);
  const details = useMemo(() => listExecutionDetails(row?.backend), [row?.backend]);

  if (history.length === 0) {
    return (
      <OverviewSurface>
        <InventoryCanvas>
          <EmptyState
            title="No executions"
            description="Create an execution to realize this Run definition."
          />
        </InventoryCanvas>
      </OverviewSurface>
    );
  }

  const startedLabel = selected ? formatDateTime(selected.startedAt ?? selected.createdAt) : null;
  const durationLabel = selected ? attemptElapsed(selected) : null;

  return (
    <OverviewSurface className="overflow-hidden" surfaceClassName="flex h-full min-h-0 flex-col">
      <div className="grid h-full min-h-0 grid-rows-[minmax(0,16rem)_minmax(0,1fr)] lg:grid-cols-[minmax(18rem,24rem)_minmax(0,1fr)] lg:grid-rows-1">
        <section
          aria-label="Executions"
          className="flex min-h-0 flex-col border-b border-border lg:border-r lg:border-b-0"
        >
          <h2 className="flex shrink-0 items-center gap-2 border-b border-border px-3 py-2 text-body font-medium text-foreground">
            Executions
            <span className="font-mono text-micro font-normal text-muted-foreground">
              {history.length}
            </span>
            <span className="ml-auto">
              <PruneDialog run={run} onPruned={onPromoted} />
            </span>
          </h2>
          <ul className="min-h-0 flex-1 overflow-auto">
            {history.map((execution, index) => {
              const active = execution.executionId === selectedExecutionId;
              return (
                <li key={execution.executionId} className="border-b border-border">
                  <button
                    type="button"
                    aria-label={`Select execution ${execution.executionId}`}
                    aria-current={active ? "true" : undefined}
                    className={cn(
                      "flex w-full flex-col gap-2 px-3 py-2 text-left",
                      "hover:bg-interactive/50",
                      "focus-visible:bg-interactive/50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-ring",
                      active && "bg-accent/5",
                    )}
                    onClick={() => onSelectExecution(execution.executionId)}
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="shrink-0 font-mono text-label text-muted-foreground">
                        {index + 1}
                      </span>
                      <span className="min-w-0 flex-1 truncate font-mono text-label text-foreground">
                        {execution.executionId}
                      </span>
                      <RunStatusBadge status={execution.status} size="sm" />
                    </span>
                    <span className="flex min-w-0 items-center gap-2 text-label text-muted-foreground">
                      <span className="shrink-0">{execution.mode}</span>
                      <span className="min-w-0 truncate">
                        {formatDateTime(execution.startedAt ?? execution.createdAt)}
                      </span>
                    </span>
                    <AttemptBar execution={execution} window={attemptSpan} />
                  </button>
                </li>
              );
            })}
          </ul>
        </section>

        <div className="flex h-full min-h-0 flex-col overflow-auto">
          {!selected ? (
            <div className="flex h-full items-center justify-center px-4 py-8">
              <EmptyState
                title="Select an execution"
                description="Workflow, outputs, and executor details belong to one attempt."
              />
            </div>
          ) : (
            <>
              <header className="flex shrink-0 items-start justify-between gap-3 px-4 pt-3">
                <div className="min-w-0 space-y-1">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <h2 className="font-mono text-body-lg font-medium text-foreground">
                      {selected.executionId}
                    </h2>
                    <RunStatusBadge status={selected.status} size="sm" />
                    <span className="font-mono text-label text-muted-foreground">
                      #{selectedIndex + 1}
                    </span>
                  </div>
                  <p className="text-label text-muted-foreground">
                    {selected.mode}
                    {startedLabel ? ` · started ${startedLabel}` : ""}
                    {selected.finishedAt ? ` · ended ${formatDateTime(selected.finishedAt)}` : ""}
                    {durationLabel ? ` · ${durationLabel}` : ""}
                    {selected.basedOnExecutionId ? ` · from ${selected.basedOnExecutionId}` : ""}
                    {selected.checkpointArtifactId
                      ? ` · checkpoint ${selected.checkpointArtifactId}`
                      : ""}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <CopyButton value={selected.executionId} label="execution ID" />
                  {workflow && onOpenWorkflow && (
                    <WorkbenchIconAction label="Open workflow definition" onClick={onOpenWorkflow}>
                      <Network className="size-3.5" />
                    </WorkbenchIconAction>
                  )}
                </div>
              </header>

              {headline ? (
                <p
                  role="alert"
                  className="mx-4 mt-3 flex shrink-0 items-start gap-2 border border-border px-3 py-2"
                >
                  <TriangleAlert
                    className="mt-px size-icon-sm shrink-0 text-status-failed-foreground"
                    aria-hidden
                  />
                  <span className="min-w-0 break-words text-label text-foreground">
                    <span className="font-mono">{headline}</span>
                    {recovery ? (
                      <span className="mt-1 block text-muted-foreground">{recovery}</span>
                    ) : null}
                  </span>
                </p>
              ) : null}

              <TaskProductList
                products={products}
                activePath={pinnedPath}
                onOpen={(path) => {
                  if (!selected) return;
                  setPinned({ executionId: selected.executionId, path });
                }}
              />

              <div className="grid min-h-[32rem] flex-1 grid-rows-[minmax(16rem,1fr)_minmax(16rem,1fr)] lg:min-h-[16rem] lg:grid-cols-2 lg:grid-rows-1">
                <section
                  aria-label="Workflow"
                  className="flex min-h-0 flex-col border-b border-border px-4 py-3 lg:border-r lg:border-b-0"
                >
                  <h3 className="shrink-0 pb-2 text-body-lg font-medium text-foreground">
                    Workflow
                  </h3>
                  <div className="min-h-0 flex-1">
                    {graph ? (
                      <WorkflowGraph
                        ir={graph}
                        height="100%"
                        className="h-full"
                        onNodeClick={(taskId) => onInspectTask(taskId, run.id)}
                      />
                    ) : graphError ? (
                      <WorkbenchOperationState
                        kind="error"
                        density="compact"
                        title="Could not load workflow"
                        detail={graphError}
                      />
                    ) : graphLoading ? (
                      <WorkbenchOperationState
                        kind="loading"
                        density="compact"
                        title="Loading workflow…"
                        skeletonRows={3}
                      />
                    ) : (
                      <p className="py-6 text-label text-muted-foreground">No workflow snapshot.</p>
                    )}
                  </div>
                </section>

                <section aria-label="Outputs" className="flex min-h-0 flex-col px-4 py-3">
                  <h3 className="shrink-0 pb-2 text-body-lg font-medium text-foreground">
                    Outputs
                  </h3>
                  <div className="min-h-0 flex-1">
                    <RunExecutionOutputs
                      fill
                      preferred={pinnedPath ? { kind: "file", path: pinnedPath } : failureSelection}
                      outputs={outputs}
                      error={logsError}
                      projectId={run.projectId}
                      experimentId={run.experimentId}
                      runId={run.id}
                      selectedExecutionId={selected.executionId}
                      onPromoted={onPromoted}
                    />
                  </div>
                </section>
              </div>

              {(columns.length > 0 || details.length > 0) && row ? (
                <div className="flex shrink-0 flex-col gap-6 px-4 pt-2 pb-3">
                  {columns.length > 0 && (
                    <section className="space-y-2">
                      <h3 className="text-body-lg font-medium text-foreground">Executor</h3>
                      <PropertyRows
                        entries={columns.map((column) => {
                          const Cell = column.Cell;
                          return { label: column.header, value: <Cell execution={row} /> };
                        })}
                      />
                    </section>
                  )}
                  {details.map((detail) => {
                    const Detail = detail.Component;
                    return (
                      <section key={detail.id} className="space-y-2">
                        <h3 className="text-body-lg font-medium text-foreground">{detail.title}</h3>
                        <Detail execution={row} runId={run.id} />
                      </section>
                    );
                  })}
                </div>
              ) : null}
            </>
          )}
        </div>
      </div>
    </OverviewSurface>
  );
};
