import { TriangleAlert } from "lucide-react";
import type { JSX } from "react";

import {
  AttemptChain,
  CopyButton,
  DashboardCanvas,
  Figure,
  formatSpan,
  Gauge,
  OverviewSheet,
  OverviewSurface,
  STATUS_INK,
  StatusIcon,
} from "@/app/components/entity";
import { formatScalar } from "@/app/renderers/dashboardData";
import { groupForStatus } from "@/app/runs/statusGroups";
import type { RunSummary } from "@/app/types";
import { formatRelative } from "@/lib/format-time";
import { cn } from "@/lib/utils";
import { KnowledgeBacklinksCard } from "@/plugins/knowledge/KnowledgeBacklinksCard";

interface RunOverviewProps {
  run: RunSummary;
  parameters: [string, unknown][];
}

const instant = (value: string | null): number | null => {
  const parsed = value ? Date.parse(value) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : null;
};

/** The run in one sentence: what state it is in, and for how long. */
const verdict = (run: RunSummary): string => {
  const group = groupForStatus(run.status);
  const start = instant(run.startedAt);
  const end = instant(run.finishedAt);
  const span = start === null ? null : formatSpan(((end ?? Date.now()) - start) / 1000);
  switch (group) {
    case "running":
      return span ? `Running for ${span}` : "Running";
    case "pending":
      return "Queued, not started";
    case "succeeded":
      return span ? `Succeeded in ${span}` : "Succeeded";
    case "failed":
      return span ? `Failed after ${span}` : "Failed";
    case "cancelled":
      return span ? `Cancelled after ${span}` : "Cancelled";
    default:
      return run.statusSummary.total === 0 ? "Not run yet" : run.status;
  }
};

const RunLead = ({ run }: { run: RunSummary }): JSX.Element => {
  const group = groupForStatus(run.status);
  const attempts = run.statusSummary.total;
  const when = run.finishedAt ?? run.startedAt;
  return (
    <div className="min-w-0 space-y-2">
      <p className="flex min-w-0 items-center gap-3">
        <StatusIcon status={run.status} className="size-icon-lg" />
        <span
          className={cn(
            "min-w-0 text-display font-semibold tracking-tight",
            group === "failed" || group === "running" ? STATUS_INK[group] : "text-foreground",
          )}
        >
          {verdict(run)}
        </span>
      </p>
      <p className="pl-8 text-label text-muted-foreground">
        <Figure>{attempts}</Figure> {attempts === 1 ? "attempt" : "attempts"}
        {when ? ` · ${run.finishedAt ? "finished" : "started"} ${formatRelative(when)}` : ""}
      </p>
    </div>
  );
};

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

/** Run-scoped intent and its attempts. Attempt outputs stay under Executions. */
export const RunOverview = ({ run, parameters }: RunOverviewProps): JSX.Element => {
  const attempts = run.executionHistory;
  const failed = groupForStatus(run.status) === "failed";
  return (
    <OverviewSurface>
      <DashboardCanvas>
        <OverviewSheet
          lead={<RunLead run={run} />}
          main={
            <>
              {attempts.length > 0 ? (
                <Gauge
                  title="Attempts"
                  readout={
                    attempts.length > 1 ? "each rule is wall-clock, to the longest" : undefined
                  }
                >
                  <AttemptChain attempts={attempts} />
                </Gauge>
              ) : null}
              <Gauge
                title="Parameters"
                readout={
                  parameters.length > 0 ? (
                    <>
                      <Figure>{parameters.length}</Figure>{" "}
                      {parameters.length === 1 ? "value" : "values"}
                    </>
                  ) : undefined
                }
              >
                <PropertyGrid entries={parameters} />
              </Gauge>
            </>
          }
          margin={
            <>
              {failed && run.errorMessage ? (
                <Gauge title="Error">
                  <p className="flex items-start gap-2">
                    <TriangleAlert
                      className="mt-px size-icon-sm shrink-0 text-status-failed-foreground"
                      aria-hidden
                    />
                    <span className="min-w-0 break-words font-mono text-label text-foreground">
                      {run.errorMessage}
                    </span>
                  </p>
                </Gauge>
              ) : null}
              {run.definitionHash || run.experimentRevisionId ? (
                <Gauge title="Identity">
                  <dl className="space-y-3">
                    {run.definitionHash ? (
                      <IdentityLine label="Definition hash" value={run.definitionHash} />
                    ) : null}
                    {run.experimentRevisionId ? (
                      <IdentityLine label="Experiment revision" value={run.experimentRevisionId} />
                    ) : null}
                  </dl>
                </Gauge>
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
