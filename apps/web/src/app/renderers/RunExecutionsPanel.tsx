import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Network } from "lucide-react";
import { type JSX, type ReactNode, useMemo } from "react";
import type { ExecutionOutputsResponse } from "@/api/generated/models/ExecutionOutputsResponse";
import {
  CopyButton,
  EmptyState,
  InventoryCanvas,
  OverviewSurface,
  StatusIcon,
  statusKey,
} from "@/app/components/entity";
import { listExecutionColumns, listExecutionDetails } from "@/app/registry";
import { formatDuration } from "@/app/renderers/dashboardData";
import { RunExecutionOutputs } from "@/app/renderers/run/RunExecutionOutputs";
import { groupForStatus } from "@/app/runs/statusGroups";
import { executionJournalQueryOptions, journalRefetchInterval } from "@/app/state/entityQueries";
import type { ExecutionRecordSummary, RunSummary, WorkflowSummary } from "@/app/types";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  RunStatusBadge,
  WorkbenchAction,
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
  const duration = formatDuration(execution.startedAt, execution.finishedAt);
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

  const failedTasks =
    graph?.task_configs.filter((task) => statusKey(task.status) === "failed") ?? [];
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

  return (
    <OverviewSurface>
      <InventoryCanvas>
        <section className="space-y-3">
          <h2 className="text-body-lg font-medium text-foreground">
            Executions
            <span className="ml-2 font-mono text-micro font-normal text-muted-foreground">
              {history.length}
            </span>
          </h2>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-14">#</TableHead>
                <TableHead className="w-24">State</TableHead>
                <TableHead>Execution</TableHead>
                <TableHead className="w-24">Mode</TableHead>
                <TableHead className="w-40">Started</TableHead>
                <TableHead className="w-52">Timeline</TableHead>
                <TableHead className="w-32">Backend</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {history.map((execution, index) => {
                const active = execution.executionId === selectedExecutionId;
                const select = (): void => onSelectExecution(execution.executionId);
                return (
                  <TableRow
                    key={execution.executionId}
                    tabIndex={0}
                    aria-label={`Select execution ${execution.executionId}`}
                    aria-current={active ? "true" : undefined}
                    className={cn(
                      "cursor-pointer transition-colors hover:bg-interactive/50",
                      "focus-visible:bg-interactive/50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-ring",
                      active && "bg-muted/40",
                    )}
                    onClick={select}
                    onKeyDown={(event) => {
                      if (
                        event.target !== event.currentTarget ||
                        (event.key !== "Enter" && event.key !== " ")
                      ) {
                        return;
                      }
                      event.preventDefault();
                      select();
                    }}
                    data-state={active ? "selected" : undefined}
                  >
                    <TableCell className="font-mono text-label text-muted-foreground">
                      <span className="inline-flex items-center gap-2">
                        <StatusIcon status={execution.status} />
                        {index + 1}
                      </span>
                    </TableCell>
                    <TableCell>
                      <RunStatusBadge status={execution.status} size="sm" />
                    </TableCell>
                    <TableCell className="font-mono text-label">{execution.executionId}</TableCell>
                    <TableCell className="text-label text-muted-foreground">
                      {execution.mode}
                    </TableCell>
                    <TableCell className="text-label text-muted-foreground">
                      {formatDateTime(execution.startedAt ?? execution.createdAt)}
                    </TableCell>
                    <TableCell>
                      <AttemptBar execution={execution} window={attemptSpan} />
                    </TableCell>
                    <TableCell className="font-mono text-label text-muted-foreground">
                      {backendOf(execution)}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </section>

        {!selected ? (
          <section className="border-t border-border py-8">
            <EmptyState
              title="Select an execution"
              description="Execution details, outputs, environment, and plugin tools require an explicit physical attempt."
            />
          </section>
        ) : (
          <>
            <section className="space-y-3">
              <div className="flex items-baseline justify-between gap-2">
                <h2 className="text-body-lg font-medium text-foreground">
                  Execution #{selectedIndex + 1}
                </h2>
                <div className="flex items-center gap-1">
                  <CopyButton value={selected.executionId} label="execution ID" />
                  {workflow && onOpenWorkflow && (
                    <WorkbenchIconAction label="Open workflow definition" onClick={onOpenWorkflow}>
                      <Network className="size-3.5" />
                    </WorkbenchIconAction>
                  )}
                </div>
              </div>
              <PropertyRows
                entries={[
                  { label: "State", value: <RunStatusBadge status={selected.status} size="sm" /> },
                  { label: "Mode", value: selected.mode },
                  { label: "Created", value: formatDateTime(selected.createdAt) },
                  {
                    label: "Start",
                    value: selected.startedAt ? formatDateTime(selected.startedAt) : "—",
                  },
                  {
                    label: "End",
                    value: selected.finishedAt ? formatDateTime(selected.finishedAt) : "—",
                  },
                  { label: "Backend", value: backendOf(selected) },
                  ...(selected.basedOnExecutionId
                    ? [{ label: "Based on", value: selected.basedOnExecutionId }]
                    : []),
                  ...(selected.checkpointArtifactId
                    ? [{ label: "Checkpoint", value: selected.checkpointArtifactId }]
                    : []),
                ]}
              />
            </section>

            {row && columns.length > 0 && (
              <section className="space-y-3">
                <h2 className="text-body-lg font-medium text-foreground">Executor</h2>
                <PropertyRows
                  entries={columns.map((column) => {
                    const Cell = column.Cell;
                    return { label: column.header, value: <Cell execution={row} /> };
                  })}
                />
              </section>
            )}

            {row &&
              details.map((detail) => {
                const Detail = detail.Component;
                return (
                  <section key={detail.id} className="space-y-3">
                    <h2 className="text-body-lg font-medium text-foreground">{detail.title}</h2>
                    <Detail execution={row} runId={run.id} />
                  </section>
                );
              })}

            <section className="space-y-3">
              <h2 className="text-body-lg font-medium text-foreground">Outputs</h2>
              <RunExecutionOutputs
                outputs={outputs}
                error={logsError}
                projectId={run.projectId}
                experimentId={run.experimentId}
                runId={run.id}
                selectedExecutionId={selectedExecutionId}
                onPromoted={onPromoted}
              />
            </section>

            <section className="space-y-3">
              <h2 className="text-body-lg font-medium text-foreground">Observed workflow</h2>
              {failedTasks.length > 0 && (
                <div className="border-y border-status-failed/25 bg-status-failed-soft px-3 py-3 text-label text-status-failed-foreground">
                  <div className="flex flex-wrap items-center gap-2">
                    <AlertTriangle className="size-icon-sm" />
                    Failed at
                    {failedTasks.map((task) => (
                      <WorkbenchAction
                        key={task.id}
                        kind="ghost"
                        size="content"
                        className="font-mono underline-offset-2 hover:underline"
                        onClick={() => onInspectTask(task.id, run.id)}
                      >
                        {task.id}
                      </WorkbenchAction>
                    ))}
                  </div>
                </div>
              )}
              {graph ? (
                <div className="overflow-hidden border border-border bg-canvas">
                  <WorkflowGraph
                    ir={graph}
                    height={420}
                    onNodeClick={(taskId) => onInspectTask(taskId, run.id)}
                  />
                </div>
              ) : graphError ? (
                <WorkbenchOperationState
                  kind="error"
                  density="compact"
                  title="Could not load the observed workflow"
                  detail={graphError}
                />
              ) : graphLoading ? (
                <WorkbenchOperationState
                  kind="loading"
                  density="compact"
                  title="Loading observed workflow…"
                  skeletonRows={3}
                />
              ) : (
                <p className="py-6 text-label text-muted-foreground">
                  No observed workflow snapshot for this execution.
                </p>
              )}
            </section>
          </>
        )}
      </InventoryCanvas>
    </OverviewSurface>
  );
};
