/**
 * Comparing the staged runs — a tab of Runs, not a place of its own.
 *
 * The runs being compared come from the Runs table, and the Comparison panel
 * that holds them is docked in the same column the table's explorer occupies,
 * so the charts belong beside them rather than behind a separate destination
 * the selection has to survive a navigation to reach.
 *
 * The pane is one thing: a matrix of the ticked runs, parameters and metrics
 * down the side, one column per run, rows that differ marked. Clicking a
 * metric row opens its chart, where the choices that only matter for a single
 * measurement — how to combine replicas, what to colour by — have somewhere to
 * live. Metrics are read on request; parameters need no read at all.
 */

import { GitCompare, RefreshCw } from "lucide-react";
import { type JSX, useState } from "react";

import { EmptyState } from "@/app/components/entity";
import { WorkbenchIconAction } from "@/components/workbench";
import { cn } from "@/lib/utils";

import { CompareTable } from "./CompareTable";
import { MetricDetailDialog } from "./MetricDetailDialog";
import { refKey } from "./types";
import { useCompareMetrics } from "./useCompareMetrics";
import { useCompareSet } from "./useCompareSet";

export const ComparePane = (): JSX.Element => {
  const { selected, count } = useCompareSet();
  const metrics = useCompareMetrics();
  const [openMetric, setOpenMetric] = useState<string | null>(null);

  // Grouping is chosen inside the dialog, so the read only needs a stable
  // per-run key; the dialog re-labels the loaded series without a second read.
  const scan = (): void => {
    metrics.scan(selected, (entry) => refKey(entry.ref));
  };

  if (count === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <EmptyState
          icon={<GitCompare className="h-6 w-6" />}
          title="The comparison is empty"
          description="Tick runs in the Jobs tab to stage them. The Comparison panel is docked at the foot of the left panel and follows you across projects and workspaces."
        />
      </div>
    );
  }

  if (selected.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <EmptyState
          icon={<GitCompare className="h-6 w-6" />}
          title="Nothing ticked"
          description={`${count} runs are staged. Tick the ones to compare in the Comparison panel at the foot of the left panel.`}
        />
      </div>
    );
  }

  const hasTrouble =
    metrics.error !== null || metrics.failures.length > 0 || metrics.unexecuted.length > 0;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-2 pb-2">
        <span className="text-label text-muted-foreground">
          {selected.length} of {count} staged runs
        </span>
        <WorkbenchIconAction
          label={metrics.loading ? "Reading metrics" : "Read the selected runs' metrics"}
          kind="ghost"
          onClick={scan}
          disabled={metrics.loading}
          className="text-muted-foreground hover:text-foreground"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", metrics.loading && "mol-motion-progress-spin")} />
        </WorkbenchIconAction>
      </div>

      <div className="min-h-0 flex-1">
        <CompareTable
          entries={selected}
          perRunAll={metrics.perRunAll}
          scanned={metrics.scanned}
          onOpenMetric={setOpenMetric}
        />
      </div>

      {hasTrouble && (
        <div className="flex shrink-0 flex-wrap gap-x-4 border-border border-t px-1 py-2 text-label text-muted-foreground">
          {metrics.unexecuted.length > 0 && (
            <span>{metrics.unexecuted.length} runs have no execution yet</span>
          )}
          {metrics.failures.length > 0 && (
            <span className="text-status-failed-foreground">
              Could not read: {metrics.failures.join(", ")}
            </span>
          )}
          {metrics.error && <span className="text-status-failed-foreground">{metrics.error}</span>}
        </div>
      )}

      <MetricDetailDialog
        metricKey={openMetric}
        entries={selected}
        perRunAll={metrics.perRunAll}
        onClose={() => setOpenMetric(null)}
      />
    </div>
  );
};
