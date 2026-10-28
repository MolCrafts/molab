import { TriangleAlert } from "lucide-react";
import type { JSX } from "react";

import {
  CopyButton,
  DashboardCanvas,
  formatSpan,
  InventoryCanvas,
  OverviewSheet,
  OverviewSurface,
  type StatusCounts,
  StatusLedger,
} from "@/app/components/entity";
import { formatDuration, formatScalar } from "@/app/renderers/dashboardData";
import { executionErrorText, isFailureStatus } from "@/app/renderers/run/executionFailure";
import { groupForStatus } from "@/app/runs/statusGroups";
import type { ExecutionRecordSummary, RunSummary } from "@/app/types";
import { RunStatusBadge } from "@/components/workbench";
import { formatDateTime } from "@/lib/datetime";
import { KnowledgeBacklinksCard } from "@/plugins/knowledge/KnowledgeBacklinksCard";

/** The run's parameter list. Overview does not host it. */
export const RunParameters = ({ parameters }: { parameters: [string, unknown][] }): JSX.Element => (
  <OverviewSurface>
    <InventoryCanvas>
      <PropertyGrid entries={parameters} />
    </InventoryCanvas>
  </OverviewSurface>
);

/**
 * One object's fields, as a property list. A two-column `<Table>` with a header
 * row is table chrome around what is really a definition list.
 */
const PropertyGrid = ({ entries }: { entries: [string, unknown][] }): JSX.Element => {
  if (entries.length === 0) {
    return <p className="text-label text-muted-foreground">No parameters</p>;
  }
  return (
    <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)]">
      {entries.map(([key, rawValue]) => {
        const value = formatScalar(rawValue);
        return (
          <div key={key} className="contents">
            <dt className="min-w-0 truncate font-mono text-label text-muted-foreground">{key}</dt>
            <dd className="min-w-0 break-all font-mono text-body text-foreground" title={value}>
              {value}
            </dd>
          </div>
        );
      })}
    </dl>
  );
};

const executionCounts = (history: readonly ExecutionRecordSummary[]): StatusCounts => {
  const counts: StatusCounts = {
    total: history.length,
    running: 0,
    pending: 0,
    succeeded: 0,
    failed: 0,
    cancelled: 0,
  };
  for (const execution of history) {
    const group = groupForStatus(execution.status);
    if (group) counts[group] += 1;
  }
  return counts;
};

/** Wall time of one attempt. In-flight work counts up to now. */
const attemptElapsed = (execution: ExecutionRecordSummary): string | null => {
  const startIso = execution.startedAt ?? execution.createdAt;
  const start = Date.parse(startIso);
  if (!Number.isFinite(start)) return null;
  if (execution.finishedAt) return formatDuration(startIso, execution.finishedAt);
  return formatSpan((Date.now() - start) / 1000);
};

const IdentityLine = ({ label, value }: { label: string; value: string }): JSX.Element => (
  <div className="min-w-0">
    <dt className="text-label text-muted-foreground">{label}</dt>
    <dd className="flex min-w-0 items-center gap-1">
      <span className="min-w-0 truncate font-mono text-label text-foreground" title={value}>
        {value}
      </span>
      <CopyButton value={value} label={label} />
    </dd>
  </div>
);

const AttemptRow = ({
  execution,
  index,
  onOpenExecution,
}: {
  execution: ExecutionRecordSummary;
  index: number;
  onOpenExecution?: (executionId: string) => void;
}): JSX.Element => {
  const duration = attemptElapsed(execution);
  const errorText = isFailureStatus(execution.status) ? executionErrorText(execution.error) : null;
  const body = (
    <span className="flex min-w-0 items-center gap-3">
      <span className="w-6 shrink-0 font-mono text-label text-muted-foreground">{index + 1}</span>
      <span className="w-16 shrink-0 truncate font-mono text-label text-foreground">
        {execution.executionId}
      </span>
      <RunStatusBadge status={execution.status} size="sm" />
      <span className="min-w-0 flex-1 truncate text-label text-muted-foreground">
        {execution.mode}
        {" · "}
        {formatDateTime(execution.startedAt ?? execution.createdAt)}
      </span>
      {duration ? (
        <span className="shrink-0 font-mono text-label tabular-nums text-foreground">
          {duration}
        </span>
      ) : null}
    </span>
  );
  const className =
    "flex w-full min-w-0 flex-col gap-1 px-1 py-2 text-left hover:bg-interactive/50 focus-visible:bg-interactive/50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-ring";
  const row = (
    <>
      {body}
      {errorText ? (
        <span className="truncate pl-9 font-mono text-label text-foreground" title={errorText}>
          {errorText}
        </span>
      ) : null}
    </>
  );
  return (
    <li className="border-b border-border last:border-b-0">
      {onOpenExecution ? (
        <button
          type="button"
          className={className}
          onClick={() => onOpenExecution(execution.executionId)}
        >
          {row}
        </button>
      ) : (
        <div className={className}>{row}</div>
      )}
    </li>
  );
};

/** How this run's attempts turned out. Parameters stay on their tab. */
export const RunOverview = ({
  run,
  onOpenExecution,
}: {
  run: RunSummary;
  onOpenExecution?: (executionId: string) => void;
}): JSX.Element => {
  const history = run.executionHistory;
  const counts = executionCounts(history);
  return (
    <OverviewSurface>
      <DashboardCanvas>
        <p className="text-label text-muted-foreground">
          <span className="tabular-nums text-foreground">{history.length}</span>{" "}
          {history.length === 1 ? "execution" : "executions"}
        </p>
        <OverviewSheet
          lead={
            history.length > 1 ? (
              <StatusLedger counts={counts} unit={["execution", "executions"]} />
            ) : history.length === 0 ? (
              <p className="text-body text-foreground">Not run yet</p>
            ) : undefined
          }
          main={
            <>
              {run.errorMessage ? (
                <p className="flex items-start gap-2 border border-border px-3 py-2">
                  <TriangleAlert
                    className="mt-px size-icon-sm shrink-0 text-status-failed-foreground"
                    aria-hidden
                  />
                  <span className="min-w-0 break-words font-mono text-label text-foreground">
                    {run.errorMessage}
                  </span>
                </p>
              ) : null}
              {history.length > 0 ? (
                <ul aria-label="Executions">
                  {history.map((execution, index) => (
                    <AttemptRow
                      key={execution.executionId}
                      execution={execution}
                      index={index}
                      onOpenExecution={onOpenExecution}
                    />
                  ))}
                </ul>
              ) : null}
              {run.definitionHash || run.experimentRevisionId ? (
                <section className="min-w-0 space-y-2 border-t border-border pt-3">
                  <h2 className="text-body-lg font-medium text-foreground">Definition</h2>
                  <dl className="space-y-3">
                    {run.definitionHash ? (
                      <IdentityLine label="Definition hash" value={run.definitionHash} />
                    ) : null}
                    {run.experimentRevisionId ? (
                      <IdentityLine label="Experiment revision" value={run.experimentRevisionId} />
                    ) : null}
                  </dl>
                </section>
              ) : null}
              <KnowledgeBacklinksCard
                kind="run"
                projectId={run.projectId}
                experimentId={run.experimentId}
                runId={run.id}
              />
            </>
          }
        />
      </DashboardCanvas>
    </OverviewSurface>
  );
};
