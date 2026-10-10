/**
 * Molq entity tab — padded dashboard canvas with executor metadata as shadcn Table.
 * Registered as a run tab contribution (value ``molq``); only matched for molq backends.
 */

import { DashboardCanvas, DashboardCard, OverviewSurface } from "@/app/components/entity";
import type { RendererProps } from "@/app/types";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const formatExecutorLabel = (key: string): string =>
  key.replace(/_/g, " ").replace(/\b\w/g, (match) => match.toUpperCase());

export const MolqRunTab = ({ selection, snapshot, executionId }: RendererProps): JSX.Element => {
  const run = snapshot.runs.find((item) => item.id === selection.objectId) ?? null;
  const execution = run?.executionHistory.find((item) => item.executionId === executionId) ?? null;
  const entries = Object.entries(execution?.executor ?? {}).sort(([a], [b]) => a.localeCompare(b));

  return (
    <OverviewSurface>
      <DashboardCanvas>
        <DashboardCard
          title="Selected execution"
          description="Submission and cluster fields from the selected execution."
        >
          {entries.length === 0 ? (
            <p className="py-4 text-label text-muted-foreground">
              {executionId ? "This execution has no Molq metadata." : "Select a Molq execution."}
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-48">Field</TableHead>
                  <TableHead>Value</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {entries.map(([key, value]) => (
                  <TableRow key={key}>
                    <TableCell className="align-top text-label text-muted-foreground">
                      {formatExecutorLabel(key)}
                    </TableCell>
                    <TableCell className="break-all font-mono text-label text-foreground">
                      {typeof value === "string" ? value : JSON.stringify(value)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </DashboardCard>
      </DashboardCanvas>
    </OverviewSurface>
  );
};
