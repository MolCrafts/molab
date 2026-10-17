/**
 * Independent comparison page — not a tab of a run or experiment.
 *
 * Opening this page with a selection is the ask to read metrics. Gathering
 * stays cheap; the scan runs here, not in the dock.
 */

import { GitCompare, RefreshCw } from "lucide-react";
import { type JSX, useEffect, useMemo, useState } from "react";
import { EmptyState, EntityPage } from "@/app/components/entity";
import type { NavigationLandingProps } from "@/app/navigation/sections";
import { WorkbenchIconAction } from "@/components/workbench";
import { cn } from "@/lib/utils";

import { CompareTable } from "./CompareTable";
import { ExpandIncompleteError, expandToRuns } from "./expandToRuns";
import { MetricDetailDialog } from "./MetricDetailDialog";
import { refKey } from "./types";
import { useCompareMetrics } from "./useCompareMetrics";
import { useCompareSet } from "./useCompareSet";

export const ComparePane = ({ snapshot }: NavigationLandingProps): JSX.Element => {
  const { entries, count } = useCompareSet();
  const metrics = useCompareMetrics();
  const [openMetric, setOpenMetric] = useState<string | null>(null);

  const expanded = useMemo(() => {
    try {
      return { selected: expandToRuns(entries, snapshot), error: null as string | null };
    } catch (error) {
      const message =
        error instanceof ExpandIncompleteError
          ? error.message
          : error instanceof Error
            ? error.message
            : "Could not expand the selection.";
      return { selected: [], error: message };
    }
  }, [entries, snapshot]);
  const { selected, error: expandError } = expanded;
  const scanMetrics = metrics.scan;

  useEffect(() => {
    if (selected.length === 0) return;
    scanMetrics(selected, (entry) => refKey(entry.ref));
  }, [selected, scanMetrics]);

  const scan = (): void => {
    scanMetrics(selected, (entry) => refKey(entry.ref));
  };

  const hasTrouble = metrics.error !== null || metrics.failures.length > 0;

  const body = (): JSX.Element => {
    if (count === 0) {
      return (
        <EmptyState icon={<GitCompare className="size-icon-lg" />} title="Selection is empty" />
      );
    }
    if (expandError) {
      return <EmptyState icon={<GitCompare className="size-icon-lg" />} title={expandError} />;
    }
    if (selected.length === 0) {
      return <EmptyState icon={<GitCompare className="size-icon-lg" />} title="No runs" />;
    }
    return (
      <CompareTable
        entries={selected}
        perRunAll={metrics.perRunAll}
        scanned={metrics.scanned}
        onOpenMetric={setOpenMetric}
      />
    );
  };

  const centered = count === 0 || expandError !== null || selected.length === 0;

  return (
    <EntityPage
      icon={GitCompare}
      title="Compare"
      meta={count > 0 ? <span>{selected.length} runs</span> : undefined}
      actions={
        <WorkbenchIconAction
          label={metrics.loading ? "Reading metrics" : "Read metrics again"}
          kind="ghost"
          onClick={scan}
          disabled={metrics.loading || selected.length === 0}
          className="text-muted-foreground hover:text-foreground"
        >
          <RefreshCw
            className={cn("size-icon-sm", metrics.loading && "mol-motion-progress-spin")}
          />
        </WorkbenchIconAction>
      }
    >
      <div
        className={cn(
          "min-h-0 flex-1",
          centered ? "flex items-center justify-center" : "flex flex-col overflow-hidden",
        )}
      >
        {body()}
      </div>
      {hasTrouble && (
        <div className="flex shrink-0 flex-wrap gap-x-4 border-border border-t px-4 py-2 text-label text-muted-foreground">
          {metrics.failures.length > 0 && (
            <span className="text-status-failed-foreground">{metrics.failures.join(", ")}</span>
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
    </EntityPage>
  );
};
