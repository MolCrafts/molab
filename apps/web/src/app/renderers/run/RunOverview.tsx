import { DashboardCanvas, OverviewSurface } from "@/app/components/entity";
import { formatScalar } from "@/app/renderers/dashboardData";
import type { RunSummary } from "@/app/types";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { KnowledgeBacklinksCard } from "@/plugins/knowledge/KnowledgeBacklinksCard";

interface RunOverviewProps {
  run: RunSummary;
  parameters: [string, unknown][];
}

const KeyValueTable = ({ entries }: { entries: [string, unknown][] }): JSX.Element => {
  if (entries.length === 0) {
    return <p className="py-4 text-label text-muted-foreground">No parameters</p>;
  }
  return (
    <Table>
      <TableHeader><TableRow><TableHead className="w-2/5">Key</TableHead><TableHead>Value</TableHead></TableRow></TableHeader>
      <TableBody>
        {entries.map(([key, rawValue]) => {
          const value = formatScalar(rawValue);
          return (
            <TableRow key={key}>
              <TableCell className="align-top text-label text-muted-foreground">{key}</TableCell>
              <TableCell className="break-all font-mono text-label text-foreground" title={value}>{value}</TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
};

/** Run-scoped intent only. Attempt facts and outputs stay under Executions. */
export const RunOverview = ({ run, parameters }: RunOverviewProps): JSX.Element => {
  const statusRows = Object.entries(run.statusSummary.byStatus ?? {}).sort(([a], [b]) => a.localeCompare(b));
  return (
    <OverviewSurface>
      <DashboardCanvas className="max-w-4xl space-y-10">
        {run.summary && <p className="max-w-2xl text-body leading-relaxed text-muted-foreground">{run.summary}</p>}

        <section className="space-y-3">
          <h3 className="text-body-lg font-medium text-foreground">Execution summary</h3>
          <div className="flex flex-wrap gap-x-6 gap-y-2 border-y border-border py-3 font-mono text-label">
            <span><span className="text-muted-foreground">total </span>{run.statusSummary.total}</span>
            <span><span className="text-muted-foreground">active </span>{run.statusSummary.active}</span>
            {statusRows.map(([status, count]) => <span key={status}><span className="text-muted-foreground">{status} </span>{count}</span>)}
          </div>
          <p className="text-micro text-muted-foreground">
            This is an aggregate view. Select an execution to inspect physical status, environment, and outputs.
          </p>
        </section>

        <section className="space-y-3">
          <h3 className="text-body-lg font-medium text-foreground">
            Run definition
            <span className="ml-2 font-mono text-micro font-normal text-muted-foreground">{parameters.length}</span>
          </h3>
          <KeyValueTable entries={parameters} />
          <dl className="grid gap-2 border-t border-border pt-3 text-label sm:grid-cols-[10rem_1fr]">
            <dt className="text-muted-foreground">Definition hash</dt>
            <dd className="break-all font-mono">{run.definitionHash || "—"}</dd>
            <dt className="text-muted-foreground">Experiment revision</dt>
            <dd className="break-all font-mono">{run.experimentRevisionId || "—"}</dd>
          </dl>
        </section>

        <KnowledgeBacklinksCard kind="run" projectId={run.projectId}
          experimentId={run.experimentId} runId={run.id} />
      </DashboardCanvas>
    </OverviewSurface>
  );
};
