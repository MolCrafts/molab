import {
  DashboardCanvas,
  OverviewSurface,
  type StatusCountRollup,
  StatusDistribution,
} from "@/app/components/entity";
import { formatScalar } from "@/app/renderers/dashboardData";
import { groupForStatus } from "@/app/runs/statusGroups";
import type { RunSummary } from "@/app/types";
import { KnowledgeBacklinksCard } from "@/plugins/knowledge/KnowledgeBacklinksCard";

interface RunOverviewProps {
  run: RunSummary;
  parameters: [string, unknown][];
}

/** Fold the attempt tally into the canonical status groups the ramp is drawn from. */
const rollupAttempts = (byStatus: Record<string, number>): StatusCountRollup => {
  const counts: StatusCountRollup = {
    total: 0,
    running: 0,
    pending: 0,
    succeeded: 0,
    failed: 0,
    cancelled: 0,
  };
  for (const [status, count] of Object.entries(byStatus)) {
    const group = groupForStatus(status);
    counts.total += count;
    if (group) counts[group] += count;
  }
  return counts;
};

/**
 * One object's fields, as a property list. A two-column `<Table>` with a header
 * row is table chrome around what is really a definition list.
 */
const PropertyGrid = ({ entries }: { entries: [string, unknown][] }): JSX.Element => {
  if (entries.length === 0) {
    return <p className="py-4 text-label text-muted-foreground">No parameters</p>;
  }
  return (
    <dl className="grid gap-x-6 gap-y-2 border-y border-border py-3 sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)]">
      {entries.map(([key, rawValue]) => {
        const value = formatScalar(rawValue);
        return (
          <div key={key} className="contents">
            <dt className="min-w-0 truncate text-label text-muted-foreground">{key}</dt>
            <dd className="min-w-0 break-all font-mono text-label text-foreground" title={value}>
              {value}
            </dd>
          </div>
        );
      })}
    </dl>
  );
};

/** Run-scoped intent only. Attempt facts and outputs stay under Executions. */
export const RunOverview = ({ run, parameters }: RunOverviewProps): JSX.Element => {
  const attempts = rollupAttempts(run.statusSummary.byStatus ?? {});
  return (
    <OverviewSurface>
      <DashboardCanvas className="max-w-4xl space-y-8">
        {run.summary && (
          <p className="max-w-2xl text-body leading-relaxed text-muted-foreground">{run.summary}</p>
        )}

        <section className="space-y-3">
          <h2 className="text-body-lg font-medium text-foreground">Attempts</h2>
          <StatusDistribution counts={attempts} />
          <p className="font-mono text-micro tabular-nums text-muted-foreground">
            {run.statusSummary.total} total · {run.statusSummary.active} active
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-body-lg font-medium text-foreground">Run definition</h2>
          <PropertyGrid entries={parameters} />
          <dl className="grid gap-x-6 gap-y-2 text-label sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)]">
            <dt className="text-muted-foreground">Definition hash</dt>
            <dd className="break-all font-mono">{run.definitionHash || "—"}</dd>
            <dt className="text-muted-foreground">Experiment revision</dt>
            <dd className="break-all font-mono">{run.experimentRevisionId || "—"}</dd>
          </dl>
        </section>

        <KnowledgeBacklinksCard
          kind="run"
          projectId={run.projectId}
          experimentId={run.experimentId}
          runId={run.id}
        />
      </DashboardCanvas>
    </OverviewSurface>
  );
};
